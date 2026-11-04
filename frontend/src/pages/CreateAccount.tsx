import { useState } from 'react'
import { api } from '../lib/api'
import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import logo from '../assets/logo-icon.svg'

function CreateAccount() {
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError('')
    setPending(true)
    try {
      if (data.get('password') !== data.get('confirmPassword')) throw new Error('Passwords must match.')
      await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ first_name: data.get('firstName'), last_name: data.get('lastName'), email: data.get('email'), password: data.get('password') }) })
      navigate('/dashboard')
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

        <h2 className="auth-page-title">Create Account</h2>

        {error && <p role="alert">{error}</p>}
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
            minLength={8}
            maxLength={128}
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
            minLength={8}
            maxLength={128}
            required
          />

          <button className="button" type="submit" disabled={pending}>
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
