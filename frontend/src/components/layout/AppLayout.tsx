import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import Header from './Header'

function AppLayout() {
  const [user, setUser] = useState<{ is_guest: boolean } | null>(null)
  const [session, setSession] = useState<'loading' | 'authenticated' | 'anonymous' | 'error'>('loading')
  useEffect(() => {
    let active = true
    api<{ is_guest: boolean }>('/api/auth/me').then(
      user => { if (active) { setUser(user); setSession('authenticated') } },
      error => { if (active) setSession(error instanceof ApiError && error.status === 401 ? 'anonymous' : 'error') },
    )
    return () => { active = false }
  }, [])
  if (session === 'loading') return <main className="page"><p role="status">Checking your session…</p></main>
  if (session === 'anonymous') return <Navigate to="/login" replace />
  if (session === 'error') return <main className="page"><p role="alert">Unable to check your session. Check that the backend is running and refresh this page.</p></main>
  return <><Header /><main className="page"><Outlet context={{ isGuest: user?.is_guest === true }} /></main></>
}
export default AppLayout
