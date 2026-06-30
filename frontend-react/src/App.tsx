import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import Layout from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import HomePage from './pages/HomePage'
import UploadPage from './pages/UploadPage'
import ChatPage from './pages/ChatPage'
import FairnessPage from './pages/FairnessPage'
import MLPage from './pages/MLPage'
import ReportsPage from './pages/ReportsPage'
import MonitoringPage from './pages/MonitoringPage'
import SettingsPage from './pages/SettingsPage'
import SearchPage from './pages/SearchPage'
import AdvancedFairnessPage from './pages/AdvancedFairnessPage'
import CasesPage from './pages/CasesPage'
import CompliancePage from './pages/CompliancePage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

// Wrap every page with ErrorBoundary so crashes show a message instead of blank
function Page({ component: Component }: { component: React.ComponentType }) {
  return (
    <ErrorBoundary>
      <Component />
    </ErrorBoundary>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<ErrorBoundary><LoginPage /></ErrorBoundary>} />
      <Route path="/register" element={<ErrorBoundary><RegisterPage /></ErrorBoundary>} />
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route index element={<Page component={HomePage} />} />
        <Route path="upload" element={<Page component={UploadPage} />} />
        <Route path="chat" element={<Page component={ChatPage} />} />
        <Route path="search" element={<Page component={SearchPage} />} />
        <Route path="fairness" element={<Page component={FairnessPage} />} />
        <Route path="fairness/advanced" element={<Page component={AdvancedFairnessPage} />} />
        <Route path="cases" element={<Page component={CasesPage} />} />
        <Route path="compliance" element={<Page component={CompliancePage} />} />
        <Route path="ml" element={<Page component={MLPage} />} />
        <Route path="reports" element={<Page component={ReportsPage} />} />
        <Route path="monitoring" element={<Page component={MonitoringPage} />} />
        <Route path="settings" element={<Page component={SettingsPage} />} />
      </Route>
    </Routes>
  )
}
