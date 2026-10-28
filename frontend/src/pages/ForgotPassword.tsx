import { useState } from 'react'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function ForgotPassword() {

  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError('')
    setPending(true)
    try {
      const result = await api<{ message: string; delivery: string }>('/api/auth/password-reset', { method: 'POST', body: JSON.stringify({ email: data.get('email') }) })
      setMessage(result.message + (result.delivery === 'local' ? ' For local testing, open the reset email in backend/data/mail_outbox/.' : ' Check your inbox.'))
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Request failed. Please try again.')
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

        <h2 className="auth-page-title">Forgot your password?</h2>

        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
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

          <button className="button" type="submit" disabled={pending}>
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
