/** Permission keys — must stay in sync with backend `app/core/permissions.py`. */
export const P = {
  dashboardRead: 'dashboard:read',
  applicationsRead: 'applications:read',
  applicationsReview: 'applications:review',
  applicationsAssess: 'applications:assess',
  piiReveal: 'pii:reveal',
  disbursementsRead: 'disbursements:read',
  disbursementsHold: 'disbursements:hold',
  verificationsRead: 'verifications:read',
  verificationsInitiate: 'verifications:initiate',
  alertsRead: 'alerts:read',
  alertsTriage: 'alerts:triage',
  networkRead: 'network:read',
  casesRead: 'cases:read',
  casesCreate: 'cases:create',
  casesUpdate: 'cases:update',
  casesAssign: 'cases:assign',
  casesResolve: 'cases:resolve',
  auditRead: 'audit:read',
  usersRead: 'users:read',
  usersManage: 'users:manage',
  orgsManage: 'organizations:manage',
  detectionRun: 'detection:run',
} as const;

export type Permission = (typeof P)[keyof typeof P];
