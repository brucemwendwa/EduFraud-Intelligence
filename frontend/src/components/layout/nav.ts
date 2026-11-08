import {
  Activity,
  ArrowLeftRight,
  Banknote,
  Bell,
  Building2,
  Cpu,
  CreditCard,
  FileSearch,
  FolderKanban,
  LayoutDashboard,
  Network,
  ScanFace,
  ScrollText,
  Settings,
  Smartphone,
  WalletCards,
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
    items: [{ label: 'Dashboard', to: '/app', icon: LayoutDashboard, permission: P.dashboardRead }],
  },
  {
    title: 'Student financial aid',
    items: [
      { label: 'Student accounts', to: '/app/accounts', icon: WalletCards, permission: P.accountsRead },
      { label: 'Student ID cards', to: '/app/cards', icon: CreditCard, permission: P.accountsRead },
      { label: 'Aid allocations', to: '/app/disbursements', icon: Banknote, permission: P.disbursementsRead },
      { label: 'Transaction intelligence', to: '/app/transactions', icon: ArrowLeftRight, permission: P.transactionsRead },
      { label: 'Aid applications', to: '/app/applications', icon: FileSearch, permission: P.applicationsRead },
    ],
  },
  {
    title: 'Security & intelligence',
    items: [
      { label: 'AI fraud detection', to: '/app/engine', icon: Cpu, permission: P.dashboardRead },
      { label: 'Device & access', to: '/app/access', icon: Smartphone, permission: P.securityRead },
      { label: 'Identity verification', to: '/app/verification', icon: ScanFace, permission: P.verificationsRead },
      { label: 'Fraud network', to: '/app/network', icon: Network, permission: P.networkRead },
    ],
  },
  {
    title: 'Investigations',
    items: [
      { label: 'Security alerts', to: '/app/alerts', icon: Bell, permission: P.alertsRead },
      { label: 'Investigation cases', to: '/app/cases', icon: FolderKanban, permission: P.casesRead },
    ],
  },
  {
    title: 'Administration',
    items: [
      { label: 'Institutions & users', to: '/app/institutions', icon: Building2, permission: P.usersRead },
      { label: 'Audit logs', to: '/app/audit', icon: ScrollText, permission: P.auditRead },
      { label: 'Operations', to: '/app/operations', icon: Activity, permission: P.operationsRead },
      { label: 'System settings', to: '/app/settings', icon: Settings, permission: P.dashboardRead },
    ],
  },
];
