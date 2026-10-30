# EduShield AI Handover

Status snapshot: 2026-10-30. This document reflects the repository at commit `d1cc3b4` on `main`.

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

Verified in this checkout:

- Backend test suite: 109 tests collected and the declared `make test` check completed successfully.
- Frontend Vitest suite: 3 files / 9 tests passed.
- `make lint`, frontend TypeScript checking, and frontend production build completed successfully.

## Partially implemented

- Investigation cases: the tenant-scoped backend now supports opening a case from an alert/application, assignment, updates, append-only notes/evidence, resolution, alerts linked to a case, audit events, and permission checks. The investigator frontend route/UI is still pending.
- Audit centre: audit APIs exist and are permission-checked, but there is no frontend audit-centre page.
- Dashboard: current page is a working role-aware launcher for operational modules, not portfolio analytics.
- Institutions/users: APIs exist; administration screens are not built.
- Background jobs: inline detection works locally. Celery configuration exists but Redis/Celery deployment has not been validated.
- Production database: migrations target PostgreSQL but all demonstrated/tested runs use SQLite.

## Not implemented

- Investigation workspace frontend and alert-to-case handoff UI.
- Dashboard analytics, audit-centre UI, institution/user admin UI, settings, notifications, and global search.
- Browser end-to-end tests (the Makefile target exists but no Playwright tests are present).
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

- Alembic revision `0001_initial_schema` is the only migration and creates all current tables, including cases, notifications, alerts, verification, and audit-chain protections.
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

1. Add the investigator case UI and alert-to-case handoff; keep the existing backend tenant isolation, permission checks, and audit events intact.
2. Add frontend tests for the case workflow and expand backend coverage for assignment/update edge cases.
3. Build the audit centre from the existing audit APIs, then replace the dashboard launcher with scoped operational analytics.
4. Add institution/user administration UI only after the investigative path is complete.
5. Add browser E2E coverage for login, alert triage, case workflow, verification consent/alternative flow, and disbursement hold/release.
6. Add production deployment infrastructure and validate it end to end on PostgreSQL before submission.
