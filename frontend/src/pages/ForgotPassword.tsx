import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function ForgotPassword() {
  const navigate = useNavigate()

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // TODO: Verify that the email belongs to an account and complete the reset-token confirmation.
    navigate('/forgot-password/new-password')
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <img className="login-logo" src={logo} alt="" />
          <h1 className="login-brand-title">Name That Genome</h1>
        </div>

        <h2 className="auth-page-title">Forgot your password?</h2>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="reset-email">Email</label>
          <input
            className="input"
            id="reset-email"
            name="email"
            type="email"
            placeholder="Email"
            autoComplete="email"
            required
          />

          <button className="button" type="submit">
            Continue
          </button>
        </form>

        <Link className="hyperlink auth-secondary-link" to="/login">
          Back to Login
        </Link>
      </Card>
    </main>
  )
}

export default ForgotPassword
