import {
  Banknote,
  Bell,
  Building2,
  Cpu,
  FileSearch,
  FolderKanban,
  LayoutDashboard,
  Network,
  ScanFace,
  ScrollText,
  Settings,
  type LucideIcon,
} from 'lucide-react';
import { P, type Permission } from '@/lib/permissions';

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  permission?: Permission;
  // Shown but not clickable until the page exists (keeps the roadmap visible without dead links).
  planned?: boolean;
}

export const navSections: { title: string; items: NavItem[] }[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', to: '/app', icon: LayoutDashboard, permission: P.dashboardRead },
      { label: 'Fraud alerts', to: '/app/alerts', icon: Bell, permission: P.alertsRead },
    ],
  },
  {
    title: 'Detection',
    items: [
      { label: 'Applications', to: '/app/applications', icon: FileSearch, permission: P.applicationsRead },
      { label: 'Identity verification', to: '/app/verification', icon: ScanFace, permission: P.verificationsRead },
      { label: 'Fraud network', to: '/app/network', icon: Network, permission: P.networkRead },
      { label: 'Disbursements', to: '/app/disbursements', icon: Banknote, permission: P.disbursementsRead },
      { label: 'Detection engine', to: '/app/engine', icon: Cpu, permission: P.dashboardRead },
    ],
  },
  {
    title: 'Response',
    items: [{ label: 'Investigations', to: '/app/cases', icon: FolderKanban, permission: P.casesRead, planned: true }],
  },
  {
    title: 'Governance',
    items: [
      { label: 'Audit center', to: '/app/audit', icon: ScrollText, permission: P.auditRead, planned: true },
      { label: 'Institutions & users', to: '/app/institutions', icon: Building2, permission: P.usersRead, planned: true },
      { label: 'Settings', to: '/app/settings', icon: Settings, planned: true },
    ],
  },
];
