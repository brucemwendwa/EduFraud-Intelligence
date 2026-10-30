# EduShield AI Handover

Status snapshot: 2026-10-30. This document reflects the repository after the Phase 9 investigation-workspace commit
(branch `phase9-cases`, based on `59b36db`).

## Repository and Git status

- Working tree: clean at the time of the handover audit.
- Branch: `main`, tracking `origin/main`; both point to `d1cc3b4`.
- Remote: `https://github.com/brucemwendwa/EduFraud-Intelligence.git`.
- Do not rewrite history, force-push, or discard work in a future dirty tree.

## Completed and tested

The following has implementation and automated coverage unless stated otherwise:

- FastAPI/React foundation, SQLite local workflow, Alembic migration, deterministic synthetic seed data, and documented OpenAPI contract.
- Authentication, hardened cookie and bearer-token flows, login rate limiting/account lockout, five roles, explicit permissions, tenant isolation, encrypted names, tokenized identifiers, and PII-reveal audit events.
- Append-only hash-chained audit records with SQLite and PostgreSQL immutability triggers; list, summary, and integrity-verification APIs.
- Explainable application and disbursement risk scoring: versioned rules, graph analysis, synthetic-only Isolation Forest contribution, stored signals/evidence, and human-review recommendations.
- Fraud alerts, application reviews, disbursement hold/release controls, fraud-network graph explorer, and detection-run/scenario-validation APIs.
- Consent-gated identity-verification workflow with a clearly labelled deterministic simulated biometric provider and officer-led alternatives.
- Frontend pages for sign-in, applications/details, alerts, disbursements, verification, network exploration, and detection-engine transparency.
- Investigation cases end to end: open from an alert or application (supporting records snapshotted as evidence),
  assignment with notifications, append-only notes, evidence attachment scoped to the institution, a case timeline
  from the audit trail, and justified human decisions (escalate, resolve with outcome, reopen, close) recorded with
  investigator and timestamp. Findings stay distinct (suspicious activity, suspected fraud, confirmed fraud, not
  substantiated); confirmed fraud requires evidence and a fuller justification. Workspace UI and alert/application
  handoff buttons are built, with backend tests and a Playwright browser test of the full workflow.

Verified in this checkout:

- Backend test suite: 109 tests collected and the declared `make test` check completed successfully.
- Frontend Vitest suite: 3 files / 9 tests passed.
- `make lint`, frontend TypeScript checking, and frontend production build completed successfully.

## Partially implemented

- Audit centre: audit APIs exist and are permission-checked, but there is no frontend audit-centre page.
- Dashboard: current page is a working role-aware launcher for operational modules, not portfolio analytics.
- Institutions/users: APIs exist; administration screens are not built.
- Background jobs: inline detection works locally. Celery configuration exists but Redis/Celery deployment has not been validated.
- Production database: migrations target PostgreSQL but all demonstrated/tested runs use SQLite.

## Not implemented

- Dashboard analytics, audit-centre UI, institution/user admin UI, settings, notifications, and global search.
- Browser end-to-end tests beyond the investigation workflow (`frontend/e2e/case-workflow.spec.ts`).
- Container image/Compose or other deployable infrastructure.
- SIS, financial-aid-system, Federal Student Aid, and commercial identity-verification integrations.
- Real biometric processing, trained fraud models, real-data validation, fairness monitoring, and student portal/appeal workflow.

## Known issues and limitations

- Biometrics are a deterministic simulation only: no camera, image, template, facial-recognition, or liveness model is present.
- Rule weights and anomaly behavior are synthetic-data only; no accuracy, precision, recall, false-positive, or fairness claim is valid.
- The in-process rate limiter is not suitable for a multi-instance deployment.
- Dashboard and several sidebar entries intentionally state that they are planned; do not present them as available functionality.
- There is no current evidence of failed tests. Test coverage does not include the verification wizard or a full browser workflow.

## Database and migration status

- Alembic revision `0001_initial_schema` creates the core tables and audit-chain protections; revision `0003`
  (`0003_case_decisions.py`, down-revision `0001`) adds `case_decisions` and `investigation_cases.finding`. Other
  in-flight branches add their own revisions off `0001`; whichever merges second must re-point its down-revision.
- Apply migrations locally with `make migrate`.
- Load/reset only synthetic demo data with `make seed`. This command drops and recreates demonstration tables, including audit records; never use it against real data.
- A production PostgreSQL migration/app startup test remains required before deployment.

## Environment and local development

Copy `.env.example` to `backend/.env` only when overrides are needed. Required production configuration:

- `ENV=production`
- `DATABASE_URL`: PostgreSQL URL (SQLite is rejected in production)
- `JWT_SECRET`: unique non-development secret
- `TOKENIZATION_KEY`: unique HMAC secret
- `DATA_ENCRYPTION_KEY`: Fernet key; required in production
- `CORS_ORIGINS`: exact browser origins
- Optional `CELERY_BROKER_URL`: Redis broker for asynchronous detection
- Optional `ACCESS_TOKEN_TTL_MINUTES` and `DEMO_MODE=false`

Local flow:

```bash
make install
make migrate
make seed
make dev
```

Run checks with `make test`, `make lint`, `cd frontend && npm run typecheck`, and `make build`.

## Deployment guidance

There is no deployment configuration yet. Before public deployment:

1. Provide a container/build and process definition for API and frontend.
2. Provision PostgreSQL, run `alembic upgrade head`, and validate migrations, health checks, authentication, tenant isolation, and audit immutability against it.
3. Configure production secrets outside the repository; set exact CORS origins and disable demo mode.
4. Use Redis/shared infrastructure for rate limiting and Celery if running multiple API instances.
5. Run an end-to-end browser test against the deployed application with synthetic data only.

## Security and decision-making requirements

- Keep authorization and organization scoping on every new endpoint and query.
- Audit sensitive actions, including denied actions where the existing patterns do so.
- Validate all input with Pydantic and keep PII masked by default.
- Do not store biometric media/templates or introduce live biometric processing without legal, privacy, vendor, and bias review.
- Risk scores are prioritization aids only. They must never independently label a student fraudulent, deny aid, or hold a payment; a human must make each consequential decision.

## Exact next steps

1. Build the audit centre from the existing audit APIs, then replace the dashboard launcher with scoped operational analytics.
2. Add institution/user administration UI.
3. Extend browser E2E coverage to alert triage, the verification consent/alternative flow and disbursement hold/release.
4. Add production deployment infrastructure and validate it end to end on PostgreSQL before submission.
