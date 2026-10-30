/**
 * Frontend view of the API contract. Hand-written until the OpenAPI export exists;
 * from Phase 4 on these alias the generated `schema.d.ts` types.
 */
export interface OrganizationRef {
  id: string;
  name: string;
  slug: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: { key: string; name: string };
  organization: OrganizationRef | null;
  is_platform_admin: boolean;
  permissions: string[];
  accessible_organizations: OrganizationRef[];
}

export interface DemoAccount {
  email: string;
  full_name: string;
  role_key: string;
  role_name: string;
  organization_name: string | null;
}
