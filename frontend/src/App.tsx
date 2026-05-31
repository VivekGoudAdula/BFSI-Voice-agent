import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './layouts/AdminLayout'
import { DashboardPage } from './pages/DashboardPage'
import { CustomersPage } from './pages/CustomersPage'
import { CampaignsPage } from './pages/CampaignsPage'
import { AgentsPage } from './pages/AgentsPage'
import { LiveCallsPage } from './pages/LiveCallsPage'
import { CallHistoryPage } from './pages/CallHistoryPage'
import { EscalationsPage } from './pages/EscalationsPage'
import { CompliancePage } from './pages/CompliancePage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { SettingsPage } from './pages/SettingsPage'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="live-calls" element={<LiveCallsPage />} />
          <Route path="call-history" element={<CallHistoryPage />} />
          <Route path="escalations" element={<EscalationsPage />} />
          <Route path="compliance" element={<CompliancePage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
