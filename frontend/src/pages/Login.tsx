import { useState } from 'react'
import { api } from '../lib/api'
import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function Login() {
  const navigate = useNavigate()

  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError('')
    setPending(true)
    try {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: data.get('email'), password: data.get('password') }) })
      navigate('/dashboard')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Request failed. Please try again.')
    } finally {
      setPending(false)
    }
  }

  async function continueAsGuest() {
    setError('')
    setPending(true)
    try {
      await api('/api/auth/guest', { method: 'POST' })
      navigate('/dashboard')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to start guest session.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="login-page">
      <Card className="login-card">
        <div className="login-brand">
          <img className="login-logo" src={logo} alt="" />
          <h1 className="login-brand-title">Name That Genome</h1>
        </div>

        {error && <p role="alert">{error}</p>}
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
            onClick={continueAsGuest}
            disabled={pending}
          >
            Continue as guest
          </button>
          <button className="button" type="submit" disabled={pending}>
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