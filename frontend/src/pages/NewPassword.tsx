import { useState } from 'react'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function NewPassword() {
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError('')
    setPending(true)
    try {
      const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
      if (!token) throw new Error('Open the reset link from your email, or request a new link.')
      if (data.get('newPassword') !== data.get('confirmPassword')) throw new Error('Passwords must match.')
      await api('/api/auth/password-reset/confirm', { method: 'POST', body: JSON.stringify({ token, password: data.get('newPassword') }) })
      window.history.replaceState(null, '', window.location.pathname)
      setMessage('Password updated. You can now log in with your new password.')
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

        <h2 className="auth-page-title">New Password</h2>

        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="new-password">New password</label>
          <input
            className="input"
            id="new-password"
            name="newPassword"
            type="password"
            placeholder="New password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
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
            minLength={8}
            maxLength={128}
            required
          />

          <button className="button" type="submit" disabled={pending || !!message}>
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
