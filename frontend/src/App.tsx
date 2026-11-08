import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { StudentShell } from '@/components/layout/StudentShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { NotFoundPage } from '@/features/common/NotFoundPage';
import { LandingPage } from '@/features/landing/LandingPage';
import { Spinner } from '@/components/ui/Spinner';
import { RequireAuth, RequireStaff, RequireStudent } from '@/lib/auth';

const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));
const ApplicationsPage = lazy(() => import('@/features/applications/ApplicationsPage'));
const ApplicationDetailPage = lazy(() => import('@/features/applications/ApplicationDetailPage'));
const DisbursementsPage = lazy(() => import('@/features/disbursements/DisbursementsPage'));
const AlertsPage = lazy(() => import('@/features/alerts/AlertsPage'));
const EnginePage = lazy(() => import('@/features/engine/EnginePage'));
const VerificationPage = lazy(() => import('@/features/verification/VerificationPage'));
const NetworkPage = lazy(() => import('@/features/network/NetworkPage'));
const CasesPage = lazy(() => import('@/features/cases/CasesPage'));
const CaseWorkspacePage = lazy(() => import('@/features/cases/CaseWorkspacePage'));
const StudentDashboardPage = lazy(() => import('@/features/student/StudentDashboardPage'));
const StudentApplicationsPage = lazy(() => import('@/features/student/StudentApplicationsPage'));
const StudentApplicationPage = lazy(() => import('@/features/student/StudentApplicationPage'));
const StudentProfilePage = lazy(() => import('@/features/student/StudentProfilePage'));
const ActivationPage = lazy(() => import('@/features/student/ActivationPage'));
const StaffActivationPage = lazy(() => import('@/features/admin/StaffActivationPage'));
const AdministrationPage = lazy(() => import('@/features/admin/AdministrationPage'));
const ForgotPasswordPage = lazy(() => import('@/features/auth/ForgotPasswordPage'));
const ResetPasswordPage = lazy(() => import('@/features/auth/ResetPasswordPage'));
const AccountsPage = lazy(() => import('@/features/accounts/AccountsPage'));
const AccountDetailPage = lazy(() => import('@/features/accounts/AccountDetailPage'));
const CardsPage = lazy(() => import('@/features/cards/CardsPage'));
const TransactionsPage = lazy(() => import('@/features/transactions/TransactionsPage'));
const AccessPage = lazy(() => import('@/features/access/AccessPage'));
const AuditPage = lazy(() => import('@/features/audit/AuditPage'));
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage'));
const OperationsPage = lazy(() => import('@/features/operations/OperationsPage'));

export function App() {
  return (
    <Suspense fallback={<div className="flex min-h-dvh items-center justify-center text-navy-700"><Spinner className="size-6" label="Loading page" /></div>}>
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/activate" element={<ActivationPage />} />
      <Route path="/activate-staff" element={<StaffActivationPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<RequireStudent />}>
          <Route path="/student" element={<StudentShell />}>
            <Route index element={<StudentDashboardPage />} />
            <Route path="applications" element={<StudentApplicationsPage />} />
            <Route path="applications/:id" element={<StudentApplicationPage />} />
            <Route path="profile" element={<StudentProfilePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
        <Route element={<RequireStaff />}>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="applications/:id" element={<ApplicationDetailPage />} />
            <Route path="disbursements" element={<DisbursementsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="engine" element={<EnginePage />} />
            <Route path="verification" element={<VerificationPage />} />
            <Route path="network" element={<NetworkPage />} />
            <Route path="cases" element={<CasesPage />} />
            <Route path="cases/:id" element={<CaseWorkspacePage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="accounts/:id" element={<AccountDetailPage />} />
            <Route path="cards" element={<CardsPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="access" element={<AccessPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="operations" element={<OperationsPage />} />
            <Route path="institutions" element={<AdministrationPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    </Suspense>
  );
}
