import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import AboutUs from './pages/AboutUs'
import History from './pages/History'
import Results from './pages/Results'
import AppLayout from './components/layout/AppLayout'
import ForgotPassword from './pages/ForgotPassword'
import NewPassword from './pages/NewPassword'
import CreateAccount from './pages/CreateAccount'
import './styles/shared.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/forgot-password/new-password" element={<NewPassword />} />
        <Route path="/create-account" element={<CreateAccount />} />
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/about" element={<AboutUs />} />
          <Route path="/history" element={<History />} />
          <Route path="/results" element={<Results />} />
        </Route>

        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App