import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Outlet,
  Route,
  RouterProvider,
} from 'react-router-dom';
import './index.css';
import Layout from './components/Layout';
import NexusSessionRoot from './components/NexusSessionRoot';
import Dashboard from './pages/NexusDashboard';
import AiActiveView from './pages/AiActiveView';
import HandoffsView from './pages/HandoffsView';
import ProspectsPage from './pages/ProspectsPage';
import StudentPipelinePage from './pages/StudentPipelinePage';
import OfflineLeadsPage from './pages/OfflineLeadsPage';
import ArchiveView from './pages/ArchiveView';
import UsersView from './pages/UsersView';
import Analytics from './pages/Analytics';
import Agents from './pages/Agents';
import AccessControl from './pages/AccessControl';
import CounsellingDashboard from './pages/CounsellingDashboard';
import BookAppointmentPage from './pages/BookAppointmentPage';
import MyBookings from './pages/MyBookings';
import MyBookingSessionPage from './pages/MyBookingSessionPage';
import MyProfile from './pages/MyProfile';
import AppSettings from './pages/AppSettings';
import ReportsLayout from './pages/ReportsLayout';
import MetaLeadsReportPage from './pages/MetaLeadsReportPage';
import ExceptionReportPage from './pages/ExceptionReportPage';
import QuarantinePage from './pages/QuarantinePage';
import SecurityAuditDashboard from './pages/SecurityAuditDashboard';
import AuditLogsPage from './pages/AuditLogsPage';
import AdminCommandCenter from './pages/AdminCommandCenter';
import MessagingHub from './pages/MessagingHub';
import AcademiaHubShell from './pages/academia/AcademiaHubShell';
import AcademiaHubHome from './pages/academia/AcademiaHubHome';
import GeographySectionPage from './pages/academia/GeographySectionPage';
import InstitutionsSectionPage from './pages/academia/InstitutionsSectionPage';
import FrameworkSectionPage from './pages/academia/FrameworkSectionPage';
import AcademiaEntityPage from './components/academia/AcademiaEntityPage';
import GeographyCitiesPage from './components/academia/GeographyCitiesPage';
import FrameworkProgramsPage from './components/academia/FrameworkProgramsPage';
import FrameworkCoursesPage from './components/academia/FrameworkCoursesPage';
import FrameworkDegreesPage from './components/academia/FrameworkDegreesPage';
import FrameworkLevelsPage from './components/academia/FrameworkLevelsPage';
import FrameworkHierarchySummaryPage from './components/academia/FrameworkHierarchySummaryPage';
import InstitutionsManagePage from './components/academia/InstitutionsManagePage';
import InstitutionsCollegesManagePage from './components/academia/InstitutionsCollegesManagePage';
import InstitutionIntakeManagePage from './components/academia/intakes/InstitutionIntakeManagePage';
import InstitutionWizardPage from './components/academia/wizard/InstitutionWizardPage';
import InstitutionHistoryPage from './components/academia/wizard/InstitutionHistoryPage';
import NexusIntelShell from './pages/nexus-intel/NexusIntelShell';
import KnowledgeHubPage from './pages/nexus-intel/KnowledgeHubPage';
import AiAssistantPage from './pages/nexus-intel/AiAssistantPage';
import WorkflowsPage from './pages/nexus-intel/WorkflowsPage';
import AcademyPage from './pages/nexus-intel/AcademyPage';
import ControlsPage from './pages/nexus-intel/ControlsPage';
import AdminPage from './pages/nexus-intel/AdminPage';
import FlowxShell from './pages/flowx/FlowxShell';
import FlowxOpsDashboardPage from './pages/flowx/FlowxOpsDashboardPage';
import FlowxCountryHubPage from './pages/flowx/FlowxCountryHubPage';
import FlowxCountriesPage from './pages/flowx/FlowxCountriesPage';
import FlowxCountryDetailPage from './pages/flowx/FlowxCountryDetailPage';
import FlowxMasterWorkflowPage from './pages/flowx/FlowxMasterWorkflowPage';
import FlowxJourneysPage from './pages/flowx/FlowxJourneysPage';
import FlowxAddApplicationPage from './pages/flowx/FlowxAddApplicationPage';
import FlowxJourneyDetailPage from './pages/flowx/FlowxJourneyDetailPage';
import FlowxStudentApplicationsPage from './pages/flowx/FlowxStudentApplicationsPage';
import FlowxBoardPage from './pages/flowx/FlowxBoardPage';
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute';
import GlobalExceptionCapture from './components/GlobalExceptionCapture';
import { ConfirmationProvider } from './context/ConfirmationContext';
import {
  UnsavedChangesNavigationGuard,
  UnsavedChangesProvider,
} from './context/UnsavedChangesContext';

function AppRoot() {
  return (
    <NexusSessionRoot>
      <UnsavedChangesProvider>
        <GlobalExceptionCapture />
        <UnsavedChangesNavigationGuard />
        <Outlet />
      </UnsavedChangesProvider>
    </NexusSessionRoot>
  );
}

const router = createBrowserRouter(
  createRoutesFromElements(
    <Route element={<AppRoot />}>
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
        <Route path="students/:pipelineSlug" element={<StudentPipelinePage />} />
        <Route path="students/:pipelineSlug/:leadId" element={<StudentPipelinePage />} />
        <Route path="offline-leads" element={<OfflineLeadsPage />} />
        <Route path="archive" element={<ArchiveView />} />
        <Route path="users" element={<UsersView />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="agents" element={<Agents />} />
        <Route path="counselling" element={<CounsellingDashboard />} />
        <Route path="book-appointment" element={<BookAppointmentPage />} />
        <Route path="command-center" element={<AdminCommandCenter />} />
        <Route path="messaging-hub" element={<MessagingHub />} />
        <Route path="my-bookings" element={<MyBookings />}>
          <Route path="session" element={<MyBookingSessionPage />} />
          <Route path="session/:bookingId" element={<MyBookingSessionPage />} />
        </Route>
        <Route path="my-profile" element={<MyProfile />} />
        <Route path="settings" element={<AppSettings />} />
        <Route path="reports" element={<ReportsLayout />}>
          <Route index element={<Navigate to="meta-leads" replace />} />
          <Route path="meta-leads" element={<MetaLeadsReportPage />} />
          <Route path="exceptions" element={<ExceptionReportPage />} />
          <Route path="audit-logs" element={<AuditLogsPage />} />
        </Route>
        <Route path="audit-logs" element={<Navigate to="/reports/audit-logs" replace />} />
        <Route path="quarantine" element={<QuarantinePage />} />
        <Route path="security-audit" element={<SecurityAuditDashboard />} />
        <Route path="access-control" element={<AccessControl />} />
        <Route path="academia" element={<AcademiaHubShell />}>
          <Route index element={<AcademiaHubHome />} />
          <Route path="institutions/:institutionId/history" element={<InstitutionHistoryPage />} />
          <Route path="institutions/new" element={<InstitutionWizardPage />} />
          <Route path="institutions/edit/:institutionId" element={<InstitutionWizardPage />} />
          <Route path="institutions/wizard/:draftId" element={<InstitutionWizardPage />} />
          <Route path="institutions" element={<InstitutionsSectionPage />}>
            <Route index element={<InstitutionsManagePage embedded />} />
            <Route path="colleges" element={<InstitutionsCollegesManagePage />} />
            <Route path="calendars" element={<Navigate to="/academia/institutions/colleges" replace />} />
            <Route path=":institutionId/intakes" element={<InstitutionIntakeManagePage />} />
          </Route>
          <Route path="geography" element={<GeographySectionPage />}>
            <Route index element={<Navigate to="countries" replace />} />
            <Route
              path="countries"
              element={
                <AcademiaEntityPage sectionKey="geography" entityKey="countries" embedded />
              }
            />
            <Route
              path="countries/:recordId"
              element={
                <AcademiaEntityPage sectionKey="geography" entityKey="countries" embedded />
              }
            />
            <Route
              path="states"
              element={<AcademiaEntityPage sectionKey="geography" entityKey="states" embedded />}
            />
            <Route
              path="states/:recordId"
              element={<AcademiaEntityPage sectionKey="geography" entityKey="states" embedded />}
            />
            <Route path="cities" element={<GeographyCitiesPage embedded />} />
            <Route path="cities/:recordId" element={<GeographyCitiesPage embedded />} />
          </Route>
          <Route path="framework" element={<FrameworkSectionPage />}>
            <Route index element={<Navigate to="summary" replace />} />
            <Route path="summary" element={<FrameworkHierarchySummaryPage embedded />} />
            <Route path="levels" element={<FrameworkLevelsPage embedded />} />
            <Route path="programs" element={<FrameworkDegreesPage embedded />} />
            <Route path="majors" element={<FrameworkProgramsPage embedded />} />
            <Route path="degrees" element={<Navigate to="../programs" replace />} />
            <Route path="courses" element={<FrameworkCoursesPage embedded />} />
          </Route>
          <Route path=":section/:entity" element={<AcademiaEntityPage />} />
          <Route path=":section/:entity/:recordId" element={<AcademiaEntityPage />} />
        </Route>
        <Route path="nexus-intel" element={<NexusIntelShell />}>
          <Route index element={<Navigate to="knowledge" replace />} />
          <Route path="knowledge" element={<KnowledgeHubPage />} />
          <Route path="ai-assistant" element={<AiAssistantPage />} />
          <Route path="flowx" element={<Navigate to="/flowx" replace />} />
          <Route path="flowx/:studentId" element={<Navigate to="/flowx" replace />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="academy" element={<AcademyPage />} />
          <Route path="controls" element={<ControlsPage />} />
          <Route path="admin" element={<AdminPage />} />
        </Route>
        <Route path="flowx" element={<FlowxShell />}>
          <Route index element={<Navigate to="ops" replace />} />
          <Route path="ops" element={<FlowxOpsDashboardPage />} />
          <Route path="ops/:countryCode" element={<FlowxCountryHubPage />} />
          <Route path="countries" element={<FlowxCountriesPage />} />
          <Route path="master" element={<FlowxMasterWorkflowPage />} />
          <Route path="countries/:countryCode" element={<FlowxCountryDetailPage />} />
          <Route path="journeys" element={<FlowxJourneysPage />} />
          <Route path="journeys/new" element={<FlowxAddApplicationPage />} />
          <Route path="journeys/student/:leadId" element={<FlowxStudentApplicationsPage />} />
          <Route path="journeys/:enrollmentId" element={<FlowxJourneyDetailPage />} />
          <Route path="board" element={<FlowxBoardPage />} />
        </Route>
      </Route>

      {/* Other Protected Routes wrapped in Legacy Layout */}
      <Route element={<Layout />}>
        <Route path="/clients" element={<div>Clients Management</div>} />
        <Route path="/notes" element={<div>Notes & Records</div>} />
      </Route>
    </Route>
  )
);

function App() {
  return (
    <ConfirmationProvider>
      <RouterProvider router={router} />
    </ConfirmationProvider>
  );
}

export default App;
