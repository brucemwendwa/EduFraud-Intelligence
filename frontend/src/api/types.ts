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
export type StudentInvitation = S['StudentInvitationOut'];
export type StudentInvitationCreate = S['StudentInvitationCreate'];
export type StudentActivationRequest = S['StudentActivationRequest'];
export type StudentProfile = S['StudentProfileOut'];
export type StudentProfileUpdate = S['StudentProfileUpdate'];
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

export type CaseRow = S['CaseRow'];
export type CaseDetail = S['CaseDetail'];
export type CaseSummary = S['CaseSummary'];
export type CaseEvidence = S['CaseEvidenceOut'];
export type CaseDecision = S['CaseDecisionOut'];
export type CaseDecisionIn = S['CaseDecisionIn'];
export type CaseEvidenceCreate = S['CaseEvidenceCreate'];
export type Assignee = S['AssigneeOut'];
export type AccountRow = S['AccountRow'];
export type AccountDetail = S['AccountDetail'];
export type AccountSummary = S['AccountSummary'];
export type CardOut = S['CardOut'];
export type CardDetail = S['CardDetail'];
export type CardSummary = S['CardSummaryOut'];
export type DeviceOut = S['DeviceOut'];
export type SecurityEventRow = S['SecurityEventRow'];
export type SecuritySummary = S['SecuritySummary'];
export type TransactionRow = S['TransactionRow'];
export type TransactionDetail = S['TransactionDetail'];
export type TransactionSummary = S['TransactionSummary'];
export type Indicator = S['IndicatorOut'];
export type VerificationRequestRow = S['VerificationRequestRow'];
export type VerificationRequestDetail = S['VerificationRequestDetail'];
export type VerificationRequestSummary = S['VerificationRequestSummary'];
export type VerificationOptions = S['VerificationOptions'];
export type DashboardOverview = S['DashboardOverview'];
export type ActivityItem = S['ActivityItem'];
export type ScenarioInfo = S['ScenarioInfo'];
export type AccountScenarioCheck = S['AccountScenarioCheck'];
export type SimulationResult = S['SimulationResult'];
export type SystemSettings = S['SystemSettings'];
export type AlertNote = S['AlertNoteOut'];
export type RelatedRecord = S['RelatedRecord'];
