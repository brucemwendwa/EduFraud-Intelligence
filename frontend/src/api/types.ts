/**
 * Frontend view of the API contract. Every type aliases the OpenAPI-generated
 * `schema.d.ts` (regenerate with `make openapi`), so a backend schema change
 * surfaces here as a type error instead of a runtime bug.
 */
import type { components } from './schema';

type S = components['schemas'];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type OrganizationRef = S['OrgRef'];
export type Me = S['Me'];
export type DemoAccount = S['DemoAccount'];
export type Organization = S['OrganizationStats'];
export type UserRow = S['UserOut'];
export type UserCreate = S['UserCreate'];
export type UserUpdate = S['UserUpdate'];
export type Role = S['RoleOut'];
export type AuditEvent = S['AuditEventOut'];
export type AuditSummary = S['AuditSummary'];
export type ChainVerification = S['ChainVerificationOut'];

export type StudentRef = S['StudentRef'];
export type IdentityToken = S['IdentityTokenOut'];
export type ApplicationRow = S['ApplicationRow'];
export type ApplicationDetail = S['ApplicationDetail'];
export type RelatedGroup = S['RelatedGroup'];
export type ReviewUpdate = S['ReviewUpdate'];
export type RevealResponse = S['RevealResponse'];
export type Enrollment = S['EnrollmentOut'];
export type DisbursementRow = S['DisbursementRow'];
export type DisbursementDetail = S['DisbursementDetail'];
export type DisbursementSummary = S['DisbursementSummary'];
export type VerificationRow = S['VerificationRow'];
export type StudentDetail = S['StudentDetail'];

export type FraudSignal = S['FraudSignalOut'];
export type RiskAssessment = S['RiskAssessmentOut'];
export type AssessmentHistoryItem = S['AssessmentHistoryItem'];
export type AlertRow = S['AlertRow'];
export type AlertDetail = S['AlertDetail'];
export type AlertSummary = S['AlertSummary'];
export type AlertTriage = S['AlertTriage'];
export type DetectionRun = S['DetectionRunOut'];
export type DetectionStatus = S['DetectionStatus'];
export type ScenarioCheck = S['ScenarioCheck'];

export type Verification = S['VerificationOut'];
export type VerificationStats = S['VerificationStats'];
export type ProviderInfo = S['ProviderInfo'];
export type BiometricVerificationIn = S['BiometricVerificationIn'];
export type AlternativeVerificationIn = S['AlternativeVerificationIn'];

export type NetworkCluster = S['NetworkCluster'];
export type NetworkGraph = S['NetworkGraph'];
export type NetworkNode = S['NetworkNode'];
export type NetworkEdge = S['NetworkEdge'];
