"""Account and variant analysis endpoints."""

from contextlib import asynccontextmanager
from email.message import EmailMessage
import hashlib
import hmac
import os
import secrets
import smtplib
import sqlite3
import ssl
import time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from . import app_database as store
from .database import find_variant, get_variant


FRONTEND_URL = os.environ.get("NTG_FRONTEND_URL", "http://localhost:5173").rstrip("/")
FRONTEND_ORIGINS = [FRONTEND_URL]
if FRONTEND_URL == "http://localhost:5173":
    FRONTEND_ORIGINS.append("http://127.0.0.1:5173")
COOKIE_NAME = "ntg_session"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.initialize_database()
    yield


app = FastAPI(title="Name That Genome API", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def website_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = [*FRONTEND_ORIGINS, str(request.base_url).rstrip("/")]
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in allowed:
        return JSONResponse({"detail": "Request must come from this website."}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegisterInput(LoginInput):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class EmailInput(BaseModel):
    email: EmailStr


class ResetInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class VariantInput(BaseModel):
    variant: str = Field(min_length=1, max_length=200, examples=["576"])


class UserResponse(BaseModel):
    id: str
    email: str | None
    first_name: str
    last_name: str
    is_guest: bool


class ShapFeature(BaseModel):
    feature: str
    value: str | float | bool | None
    contribution: float = Field(allow_inf_nan=False)


class ShapExplanation(BaseModel):
    base_value: float = Field(allow_inf_nan=False)
    explained_value: float = Field(allow_inf_nan=False)
    output_space: Literal["probability", "log_odds", "raw_score"]
    output_target: Literal["pathogenic"] = "pathogenic"
    features: list[ShapFeature]


class Prediction(BaseModel):
    model_name: str
    model_version: str
    decision: Literal["benign", "pathogenic", "uncertain"]
    pathogenic_probability: float = Field(ge=0, le=1)
    probability_kind: Literal["calibrated", "uncalibrated"]
    explanation: ShapExplanation | None = None


class AnalysisResponse(BaseModel):
    id: str
    created_at: int
    input: str
    variant: dict
    prediction_status: Literal["not_available", "available"]
    prediction: Prediction | None


class HistoryResponse(BaseModel):
    items: list[AnalysisResponse]
    total: int
    limit: int
    offset: int


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return f"{salt}:{digest}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user = store.get_session_user(token_hash(token)) if token else None
    if user is None:
        raise HTTPException(401, "Please log in or continue as a guest.")
    return user


User = Annotated[dict, Depends(current_user)]


def start_session(request: Request, response: Response, user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    lifetime = 86400 if user["is_guest"] else 7 * 86400
    old_token = request.cookies.get(COOKIE_NAME)
    store.create_session(token_hash(token), user["id"], int(time.time()) + lifetime,
                         token_hash(old_token) if old_token else None)
    response.set_cookie(COOKIE_NAME, token, max_age=lifetime, httponly=True,
                        samesite="lax", secure=os.environ.get("NTG_SECURE_COOKIES") == "1")
    return user


@app.post("/api/auth/register", response_model=UserResponse, status_code=201)
def register(body: RegisterInput, request: Request, response: Response):
    first, last = body.first_name.strip(), body.last_name.strip()
    if not first or not last:
        raise HTTPException(422, "Enter both your first and last name.")
    try:
        user = store.create_user(str(body.email).casefold(), first, last, hash_password(body.password))
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "An account with this email already exists.") from error
    return start_session(request, response, user)


@app.post("/api/auth/login", response_model=UserResponse)
def login(body: LoginInput, request: Request, response: Response):
    user = store.find_user(str(body.email).casefold())
    saved_hash = user["password_hash"] if user else None
    salt = saved_hash.split(":")[0] if saved_hash else "0" * 32
    attempted_hash = hash_password(body.password, salt)
    if not saved_hash or not hmac.compare_digest(saved_hash, attempted_hash):
        raise HTTPException(401, "Incorrect email or password.")
    return start_session(request, response, store.public_user(user))


@app.post("/api/auth/guest", response_model=UserResponse, status_code=201)
def guest(request: Request, response: Response):
    user = store.create_user(None, "Guest", "", None, guest=True)
    return start_session(request, response, user)


@app.get("/api/auth/me", response_model=UserResponse)
def me(user: User):
    return user


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        store.delete_session(token_hash(token))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME)
    return response


def send_reset_message(email: str, link: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your Name That Genome password"
    message["From"] = os.environ.get("NTG_SMTP_FROM", "no-reply@name-that-genome.local")
    message["To"] = email
    message.set_content(f"Open this link to reset your password. It expires in 30 minutes.\n\n{link}\n")
    host = os.environ.get("NTG_SMTP_HOST")
    if not host:
        outbox = store.DATABASE_PATH.parent / "mail_outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / f"{secrets.token_hex(12)}.eml").write_bytes(message.as_bytes())
        return
    with smtplib.SMTP(host, int(os.environ.get("NTG_SMTP_PORT", "587")), timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if os.environ.get("NTG_SMTP_USER"):
            smtp.login(os.environ["NTG_SMTP_USER"], os.environ["NTG_SMTP_PASSWORD"])
        smtp.send_message(message)


@app.post("/api/auth/password-reset")
def request_reset(body: EmailInput):
    user = store.find_user(str(body.email).casefold())
    if user:
        token = secrets.token_urlsafe(32)
        store.create_reset(user["id"], token_hash(token), int(time.time()) + 30 * 60)
        link = f"{FRONTEND_URL}/forgot-password/new-password#token={token}"
        try:
            send_reset_message(str(body.email), link)
        except (OSError, smtplib.SMTPException) as error:
            raise HTTPException(503, "The reset message could not be delivered. Try again later.") from error
    return {"message": "If an account exists for that email, a reset link has been created.",
            "delivery": "email" if os.environ.get("NTG_SMTP_HOST") else "local"}


@app.post("/api/auth/password-reset/confirm")
def confirm_reset(body: ResetInput, response: Response):
    if not store.reset_password(token_hash(body.token), hash_password(body.password)):
        raise HTTPException(400, "This reset link is invalid or expired. Request a new one.")
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Password updated. Please log in with your new password."}


@app.post("/variants/lookup")
def lookup_variant(body: VariantInput) -> dict:
    try:
        variant = find_variant(body.variant)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503, detail="The variant database is not available."
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found in this dataset.")

    return variant


def predict_variant(record: dict) -> Prediction | None:
    """Model hook; returns None until inference is implemented."""
    return None


@app.post("/api/analyses", response_model=AnalysisResponse, status_code=201)
def analyze(body: VariantInput, user: User):
    variant = lookup_variant(body)
    if not variant["source_records"]:
        raise HTTPException(404, "No source record is available for this variant.")
    prediction = predict_variant(variant["source_records"][0])
    return store.save_analysis(user["id"], {
        "input": body.variant.strip(),
        "variant": variant,
        "prediction_status": "available" if prediction is not None else "not_available",
        "prediction": prediction.model_dump(mode="json") if prediction is not None else None,
    })


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def read_analysis(analysis_id: str, user: User):
    result = store.get_analysis(user["id"], analysis_id)
    if result is None:
        raise HTTPException(404, "Analysis not found.")
    return result


@app.get("/api/history", response_model=HistoryResponse)
def history(user: User, limit: Annotated[int, Query(ge=1, le=100)] = 20,
            offset: Annotated[int, Query(ge=0)] = 0):
    return store.list_analyses(user["id"], limit, offset)


@app.get("/variants/clinvar/{variation_id}")
def read_variant(
    variation_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
) -> dict:
    try:
        variant = get_variant(variation_id)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503, detail="The variant database is not available."
        ) from error

    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found in this dataset.")

    return variant
