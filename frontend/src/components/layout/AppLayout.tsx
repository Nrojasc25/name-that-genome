import { Outlet } from 'react-router-dom'
import Header from './Header'

function AppLayout() {
  return (
    <>
      <Header />
      <main className="page">
        <Outlet />
      </main>
    </>
  )
}

export default AppLayout
