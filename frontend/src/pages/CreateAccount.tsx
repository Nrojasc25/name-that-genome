import { Link } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function CreateAccount() {
  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // TODO: Send the account details to the backend and securely persist the account.
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <img className="login-logo" src={logo} alt="" />
          <h1 className="login-brand-title">Name That Genome</h1>
        </div>

        <h2 className="auth-page-title">Create Account</h2>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="first-name">Name</label>
          <input
            className="input"
            id="first-name"
            name="firstName"
            type="text"
            placeholder="Name"
            autoComplete="given-name"
            required
          />

          <label htmlFor="last-name">Last name</label>
          <input
            className="input"
            id="last-name"
            name="lastName"
            type="text"
            placeholder="Last name"
            autoComplete="family-name"
            required
          />

          <label htmlFor="account-email">Email</label>
          <input
            className="input"
            id="account-email"
            name="email"
            type="email"
            placeholder="Email"
            autoComplete="email"
            required
          />

          <label htmlFor="account-password">Password</label>
          <input
            className="input"
            id="account-password"
            name="password"
            type="password"
            placeholder="Password"
            autoComplete="new-password"
            required
          />

          <label htmlFor="confirm-account-password">Confirm password</label>
          <input
            className="input"
            id="confirm-account-password"
            name="confirmPassword"
            type="password"
            placeholder="Confirm password"
            autoComplete="new-password"
            required
          />

          <button className="button" type="submit">
            Create Account
          </button>
        </form>

        <Link className="hyperlink auth-secondary-link" to="/login">
          Back to Login
        </Link>
      </Card>
    </main>
  )
}

export default CreateAccount
