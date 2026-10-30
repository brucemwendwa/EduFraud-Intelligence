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
