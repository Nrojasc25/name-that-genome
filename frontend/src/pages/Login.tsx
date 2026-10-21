import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function Login() {
  const navigate = useNavigate()

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    navigate('/dashboard')
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <img className="login-logo" src={logo} alt="" />
          <h1 className="login-brand-title">Name That Genome</h1>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            className="input"
            id="email"
            name="email"
            type="email"
            placeholder="Email"
            autoComplete="email"
            required
          />

          <label htmlFor="password">Password</label>
          <input
            className="input"
            id="password"
            name="password"
            type="password"
            placeholder="Password"
            autoComplete="current-password"
            required
          />

          <button
            className="hyperlink login-skip-link"
            type="button"
            onClick={() => navigate('/dashboard')}
          >
            Skip
          </button>
          <button className="button" type="submit">
            Login
          </button>
        </form>

        <Link className="hyperlink" to="/forgot-password">
          Forgot your password?
        </Link>
        <Link className="hyperlink auth-secondary-link" to="/create-account">
          Create Account
        </Link>
      </Card>
    </main>
  )
}

export default Login