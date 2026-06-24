import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './index.css';
import Layout from './components/Layout';
import NexusSessionRoot from './components/NexusSessionRoot';
import Dashboard from './pages/NexusDashboard';
import AiActiveView from './pages/AiActiveView'; 
import HandoffsView from './pages/HandoffsView';
import ProspectsPage from './pages/ProspectsPage';
import ArchiveView from './pages/ArchiveView';
import UsersView from './pages/UsersView';
import Analytics from './pages/Analytics';
import Agents from './pages/Agents';
import AccessControl from './pages/AccessControl';
import CounsellingDashboard from './pages/CounsellingDashboard';
import MyBookings from './pages/MyBookings';
import MyProfile from './pages/MyProfile';
import AppSettings from './pages/AppSettings';
import ReportsPage from './pages/ReportsPage';
import QuarantinePage from './pages/QuarantinePage';
import SecurityAuditDashboard from './pages/SecurityAuditDashboard';
import AdminCommandCenter from './pages/AdminCommandCenter';
import MessagingHub from './pages/MessagingHub';
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute'; 

function App() {
  return (
    <BrowserRouter>
      <NexusSessionRoot>
        <Routes>
        <Route path="/login" element={<Login />} />

        {/* Handle legacy /dashboard path by redirecting to root */}
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        
        {/* Main Intelligence Dashboard & AI Streams */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        >
          <Route path="ai-active" element={<AiActiveView />} />
          <Route path="handoffs" element={<HandoffsView />} />
          <Route path="prospects" element={<ProspectsPage />} />
          <Route path="prospects/:leadId" element={<ProspectsPage />} />
          <Route path="archive" element={<ArchiveView />} />
          <Route path="users" element={<UsersView />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="agents" element={<Agents />} />
          <Route path="counselling" element={<CounsellingDashboard />} />
          <Route path="command-center" element={<AdminCommandCenter />} />
          <Route path="messaging-hub" element={<MessagingHub />} />
          <Route path="my-bookings" element={<MyBookings />} />
          <Route path="my-profile" element={<MyProfile />} />
          <Route path="settings" element={<AppSettings />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="quarantine" element={<QuarantinePage />} />
          <Route path="security-audit" element={<SecurityAuditDashboard />} />
          <Route path="access-control" element={<AccessControl />} />
        </Route>

        {/* Other Protected Routes wrapped in Legacy Layout */}
        <Route element={<Layout />}>
          <Route path="/clients" element={<div>Clients Management</div>} />
          <Route path="/notes" element={<div>Notes & Records</div>} />
        </Route>
        </Routes>
      </NexusSessionRoot>
    </BrowserRouter>
  );
}

export default App;