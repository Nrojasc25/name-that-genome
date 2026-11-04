import { useState } from 'react'
import { api } from '../../lib/api'
import { NavLink, useNavigate } from 'react-router-dom'
import './Header.css'

function Header() {
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function logout() {
    setPending(true)
    setError('')
    try {
      await api('/api/auth/logout', { method: 'POST' })
      navigate('/login', { replace: true })
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to log out.')
    } finally {
      setPending(false)
    }
  }
  return (
    <header className="header">
      <img className="header-logo" src="/src/assets/logo.svg" alt="Name That Genome logo" />

      <nav className="header-nav">
        <NavLink to="/dashboard">Dashboard</NavLink>
        <NavLink to="/history">History</NavLink>
        <NavLink to="/about">About Us</NavLink>
        <button className="hyperlink" onClick={logout} disabled={pending}>{pending ? 'Logging out…' : 'Log out'}</button>
        {error && <p role="alert">{error}</p>}
      </nav>
    </header>
  )
}

export default Header