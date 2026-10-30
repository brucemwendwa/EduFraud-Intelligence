import { lazy } from 'react';
import { Route, Routes } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { NotFoundPage } from '@/features/common/NotFoundPage';
import { LandingPage } from '@/features/landing/LandingPage';
import { RequireAuth } from '@/lib/auth';

const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));
const ApplicationsPage = lazy(() => import('@/features/applications/ApplicationsPage'));
const ApplicationDetailPage = lazy(() => import('@/features/applications/ApplicationDetailPage'));
const DisbursementsPage = lazy(() => import('@/features/disbursements/DisbursementsPage'));
const AlertsPage = lazy(() => import('@/features/alerts/AlertsPage'));
const EnginePage = lazy(() => import('@/features/engine/EnginePage'));
const VerificationPage = lazy(() => import('@/features/verification/VerificationPage'));
const NetworkPage = lazy(() => import('@/features/network/NetworkPage'));

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/app" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="applications/:id" element={<ApplicationDetailPage />} />
          <Route path="disbursements" element={<DisbursementsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="engine" element={<EnginePage />} />
          <Route path="verification" element={<VerificationPage />} />
          <Route path="network" element={<NetworkPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
