"""Versioned prediction contracts; legacy snapshots are read without filling missing scores."""

import math
from typing import Annotated, Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ml.labels import CLASS_ORDER, VariantClass


Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class ShapFeature(BaseModel):
    feature: str
    value: str | float | bool | None
    contribution: float = Field(allow_inf_nan=False)
    members: list[dict] | None = None


class ShapExplanation(BaseModel):
    base_value: float = Field(allow_inf_nan=False)
    explained_value: float = Field(allow_inf_nan=False)
    output_space: Literal["probability", "log_odds", "raw_score"]
    output_target: VariantClass
    features: list[ShapFeature]
    display_features: list[ShapFeature] | None = None
    model_version: str | None = None
    background_version: str | None = None


class LegacyShapExplanation(ShapExplanation):
    output_target: Literal["pathogenic"] = "pathogenic"


class LegacyPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    model_name: str
    model_version: str
    decision: Literal["benign", "pathogenic", "uncertain"]
    pathogenic_probability: Score
    probability_kind: Literal["calibrated", "uncalibrated"]
    explanation: LegacyShapExplanation | None = None


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2]
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    annotation_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    decision: VariantClass
    class_scores: dict[VariantClass, Score]
    probability_kind: Literal["calibrated", "uncalibrated"]
    confidence_status: Literal["not_assessed", "low", "standard"]
    explanation: ShapExplanation | None = None

    release_status: Literal["research_candidate_rejected"] | None = None
    explanation_status: Literal["available", "failed", "not_assessed"] = "not_assessed"
    source_record_id: str | None = None
    normalized_variant_key: str | None = None

    @model_validator(mode="after")
    def valid_distribution(self) -> Self:
        if set(self.class_scores) != set(CLASS_ORDER):
            raise ValueError("class_scores must contain exactly the five canonical classes")
        if not math.isclose(sum(self.class_scores.values()), 1.0, rel_tol=0, abs_tol=1e-6):
            raise ValueError("class_scores must sum to one within 1e-6")
        # Python max keeps the first class in canonical order on an exact tie.
        winner = max(CLASS_ORDER, key=self.class_scores.__getitem__)
        if self.decision != winner:
            raise ValueError("decision must select the highest score; ties use canonical class order")
        if self.explanation_status == 'available':
            if self.explanation is None or self.explanation.output_target != self.decision:
                raise ValueError('Available explanation must target the selected class')
            explanation = self.explanation
            for features in [explanation.features, explanation.display_features]:
                if features is not None and not math.isclose(explanation.base_value + sum(f.contribution for f in features), explanation.explained_value, abs_tol=1e-4, rel_tol=0):
                    raise ValueError('Explanation contributions must reconstruct the output')
        if self.explanation_status == 'failed' and self.explanation is not None:
            raise ValueError('A failed explanation must be null')
        return self


StoredPrediction = Prediction | LegacyPrediction
