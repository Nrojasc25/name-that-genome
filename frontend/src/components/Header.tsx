import { NavLink } from 'react-router-dom'
import './Header.css'

function Header() {

  return (
    <header className="header">
      <img className="header-logo" src="/src/assets/logo.svg" alt="Name That Genome logo" />

      <nav className="header-nav">
        <NavLink to="/dashboard">Dashboard</NavLink>
        <NavLink to="/history">History</NavLink>
        <NavLink to="/about">About Us</NavLink>
        <NavLink to="/login">Log out</NavLink>        
      </nav>
    </header>
  )
}

export default Header