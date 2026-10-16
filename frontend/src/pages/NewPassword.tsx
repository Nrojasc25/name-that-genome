import { Link } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function NewPassword() {
  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // TODO: Verify the reset token and persist the new password through the backend.
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <img className="login-logo" src={logo} alt="" />
          <h1 className="login-brand-title">Name That Genome</h1>
        </div>

        <h2 className="auth-page-title">New Password</h2>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="new-password">New password</label>
          <input
            className="input"
            id="new-password"
            name="newPassword"
            type="password"
            placeholder="New password"
            autoComplete="new-password"
            required
          />

          <label htmlFor="confirm-password">Confirm new password</label>
          <input
            className="input"
            id="confirm-password"
            name="confirmPassword"
            type="password"
            placeholder="Confirm new password"
            autoComplete="new-password"
            required
          />

          <button className="button" type="submit">
            Reset Password
          </button>
        </form>

        <Link className="hyperlink auth-secondary-link" to="/login">
          Back to Login
        </Link>
      </Card>
    </main>
  )
}

export default NewPassword
