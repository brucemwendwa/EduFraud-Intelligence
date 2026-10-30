# EduShield AI

**Protecting Student Financial Aid Through Intelligence.**

EduShield AI is a fraud-intelligence prototype for U.S. college financial aid offices. It scores financial aid
applications and disbursements for signs of identity impersonation, duplicate identities, refund diversion and
coordinated fraud rings, explains every score, and hands each high-risk case to a person to decide.

It is **decision support, not an automated judge**: the software never denies aid, holds a payment, or labels a
student as fraudulent on its own.

> **Prototype status — Moringa Hackathon 2026 submission.** Everything runs on synthetic data for three
> fictional institutions. Biometric identity checks are **simulated**. See [What works today](#what-works-today),
> the [AI disclosure](docs/AI_DISCLOSURE.md) and the [Human impact and trust statement](docs/HUMAN_IMPACT_AND_TRUST.md).
> EduShield AI is not affiliated with, endorsed by or connected to Federal Student Aid or the U.S. Department of
> Education.

---

## Contents

- [The problem](#the-problem)
- [People First, AI Second](#people-first-ai-second)
- [What works today](#what-works-today)
- [Architecture and technology](#architecture-and-technology)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Demo accounts](#demo-accounts)
- [A five-minute walkthrough](#a-five-minute-walkthrough)
- [How fraud detection works](#how-fraud-detection-works)
- [Identity verification (simulated)](#identity-verification-simulated)
- [API](#api)
- [Running the tests](#running-the-tests)
- [Security and privacy](#security-and-privacy)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## The problem

Financial aid fraud rarely looks like one obviously bad application any more. Schemes spread across stolen or
synthetic identities, shared devices and payment accounts that collect refunds for many "students" at once. A
legitimate student's account can be taken over and their refund redirected. Each record, reviewed on its own, can
look normal, so manual one-at-a-time verification misses the pattern.

Financial aid staff need to see those connections early, understand *why* something looks wrong, and act before
money moves, without treating every student who shares an address with a sibling as a suspect.

## People First, AI Second

EduShield AI is built around one rule: **the AI surfaces and explains; people decide.**

- **No automated adverse action.** Scores produce *recommendations* ("human review required before
  disbursement"). Only an authorized person can hold a disbursement or record a review decision.
- **Every score is explained.** Each assessment lists its signals, how many points each contributed, the method
  that produced it, the rule and model versions, and a timestamp.
- **Benign patterns are protected.** Siblings sharing a household, students in a residence hall, campus kiosks and
  verified bank changes carry near-zero weight. Only combinations of strong signals escalate.
- **No demographic inputs.** No signal uses income, Student Aid Index, dependency status, age or demographics.
- **Students always have another way.** Biometric checks run only with consent; anyone can be verified in person,
  by officer video call or by mailed code instead.
- **Every sensitive action is accountable.** Logins, reviews, holds, verifications, name reveals and permission
  denials are written to a tamper-evident audit trail.

The full reasoning is in [docs/HUMAN_IMPACT_AND_TRUST.md](docs/HUMAN_IMPACT_AND_TRUST.md).

## What works today

| Capability | Status | Notes |
|---|---|---|
| Rule-based fraud detection (17 versioned rules) | **Operational** | Identity, application, enrollment, disbursement and verification-outcome signals |
| Explainable risk scoring (0–100, four levels) | **Operational** | Per-signal points, method, versions and timestamp stored on every assessment |
| Anomaly detection (Isolation Forest) | **Operational, synthetic-trained** | Capped influence; trained on synthetic data only; no accuracy claimed |
| Graph analysis of linked applications (NetworkX) | **Operational** | Cluster membership feeds the risk score; no graph explorer UI yet |
| Alerts for high and critical risk, with human triage | **Operational** | Acknowledge, dismiss, reopen |
| Application review, disbursement hold and release | **Operational** | Human-only actions, permission-checked and audited |
| Identity verification workflow | **Operational workflow, simulated biometrics** | Consent enforced; officer-led alternatives; outcomes re-score the application |
| Document, face, liveness and presentation-attack checks | **Simulated** | Deterministic simulated provider; no camera, images or real biometrics |
| Authentication, 5 roles, tenant isolation, PII masking | **Operational** | Enforced by the API and covered by automated tests |
| Tamper-evident audit trail (hash chain + DB triggers) | **Operational (API)** | Integrity check at `GET /api/v1/audit/verify`; audit center UI planned |
| Student, application and payment data | **Synthetic** | Generated; no real students, FSA or FAFSA data |
| Dashboard analytics, investigation cases, fraud network explorer, audit center, institution and user admin screens, settings | **Planned** | Shown as "Planned" in the app; not built |
| Commercial identity-verification vendor, SIS / aid-system integrations, trained ML models | **Planned** | See [Roadmap](#roadmap) |

## Architecture and technology

```
                 ┌────────────────────────────────────────────────────────────┐
 Browser ───────►│ React 19 + TypeScript (Vite)   localhost:5173               │
                 │  /api requests proxied to the API (same-origin cookie)      │
                 └───────────────┬────────────────────────────────────────────┘
                                 │ JSON over HTTP, httpOnly session cookie
                 ┌───────────────▼────────────────────────────────────────────┐
                 │ FastAPI  /api/v1   localhost:8000                           │
                 │  auth · RBAC · tenant scoping · rate limit · audit          │
                 │  ┌─────────────────────┐   ┌─────────────────────────────┐  │
                 │  │ Detection engine    │   │ Identity verification       │  │
                 │  │ rules + graph +     │◄──│ provider interface          │  │
                 │  │ isolation forest    │   │ → SimulatedBiometricProvider│  │
                 │  └─────────┬───────────┘   └─────────────────────────────┘  │
                 │            │ jobs: inline by default, Celery if configured  │
                 └────────────┼───────────────────────────────────────────────┘
                              ▼
                 SQLite (default, local)  ·  PostgreSQL (production target)
```

| Layer | Technology |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, pydantic-settings, Uvicorn |
| Data | SQLAlchemy 2, Alembic migrations; SQLite by default, PostgreSQL via `psycopg` |
| Detection | Versioned rules, scikit-learn `IsolationForest`, NetworkX graph clustering |
| Security | argon2id password hashing, JWT in an httpOnly `SameSite=Strict` cookie, HMAC-SHA256 identity tokenization, Fernet field encryption |
| Background jobs | Inline by default; Celery + Redis when `CELERY_BROKER_URL` is set |
| Web client | React 19, TypeScript 5.9, Vite 8, Tailwind CSS v4, React Router 7, TanStack Query 5, Radix UI primitives, Lucide icons |
| Quality | pytest, ruff, Vitest, Testing Library, ESLint, `tsc` |

## Repository structure

```
.
├── Makefile                 # install, migrate, seed, dev, test, lint, build
├── .env.example             # every setting, with development placeholders
├── scripts/
│   ├── dev.sh               # migrate, then run API (:8000) and web client (:5173) together
│   └── export_openapi.py    # writes docs/openapi.json
├── docs/
│   ├── AI_DISCLOSURE.md
│   ├── HUMAN_IMPACT_AND_TRUST.md
│   └── openapi.json         # exported API contract
├── backend/
│   ├── pyproject.toml
│   ├── alembic/             # migrations (including audit-immutability triggers)
│   ├── app/
│   │   ├── api/v1/          # routers: auth, organizations, users, applications, students,
│   │   │                    #          disbursements, verifications, alerts, detection, audit
│   │   ├── biometrics/      # provider interface + simulated provider
│   │   ├── core/            # config, security, tokenization, crypto, logging, middleware, rate limit
│   │   ├── db/              # engine, session, portable column types
│   │   ├── detection/       # engine, rules/, anomaly model, graph analysis, signal catalog, versions
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── seed/            # deterministic synthetic data generator
│   │   ├── services/        # business logic (alerts, audit, verification, records, …)
│   │   └── workers/         # Celery app and inline job fallback
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── api/             # generated OpenAPI types
        ├── components/      # layout shell and shared UI
        ├── features/        # landing, auth, dashboard, alerts, applications,
        │                    # disbursements, engine, verification
        └── lib/             # API client, auth context, permissions, formatting
```

## Getting started

### Prerequisites

- **Python 3.12** or newer
- **Node.js 24** and npm (tested with Node.js 24.14.0 and npm 11.13.0)
- `make` and `bash` (Linux or macOS; on Windows use WSL)

No database server, Redis or Docker is needed for a local run: the default database is a SQLite file and
background jobs run inline.

### 1. Install

```bash
git clone https://github.com/brucemwendwa/EduFraud-Intelligence.git
cd EduFraud-Intelligence
make install          # creates backend/.venv and installs frontend/node_modules
```

### 2. Configure (optional)

The defaults work for local development. To change a setting, copy the example file into the backend directory,
where the API reads it from:

```bash
cp .env.example backend/.env
```

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `development` | `development`, `test` or `production`. Production refuses to start with development secrets or SQLite. |
| `DEMO_MODE` | `true` | Enables demo-account quick login on the sign-in page. Set to `false` outside demonstrations. |
| `DATABASE_URL` | `sqlite:///./var/edushield.db` | SQLAlchemy URL. PostgreSQL example: `postgresql+psycopg://user:pass@localhost:5432/edushield` |
| `CELERY_BROKER_URL` | empty | Leave empty to run detection jobs inline; set a Redis URL to use Celery. |
| `JWT_SECRET` | development placeholder | Signs session tokens. **Must** be changed in production. |
| `TOKENIZATION_KEY` | development placeholder | Key for HMAC-SHA256 pseudonyms of identity attributes. **Must** be changed in production. |
| `DATA_ENCRYPTION_KEY` | empty (derived development key) | Fernet key for revealable PII. **Required** in production. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins. |
| `ACCESS_TOKEN_TTL_MINUTES` | `60` | Session length (5–1440). |

Generate real secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # JWT_SECRET, TOKENIZATION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"     # DATA_ENCRYPTION_KEY
```

### 3. Create the database and load demo data

```bash
make migrate          # alembic upgrade head
make seed             # python -m app.seed --reset: synthetic institutions, users and records
```

`make seed` **drops and recreates every table**, including the audit trail, then loads a deterministic synthetic
dataset: 3 fictional institutions, 8 demo accounts and about 480 aid applications with enrollments,
disbursements and verification history. About 30 applications belong to planted fraud scenarios and
legitimate look-alike "control" cases. To seed without wiping anything, run `cd backend && .venv/bin/python -m app.seed` (no `--reset`): it adds
missing roles, institutions and demo accounts, and loads the synthetic dataset only if there are no applications yet.

### 4. Run

```bash
make dev              # applies migrations, then starts the API and the web client together
```

Or run them in two terminals with `make backend` and `make frontend`.

| What | URL |
|---|---|
| Web client | http://localhost:5173 |
| API | http://localhost:8000/api/v1 |
| Interactive API docs (Swagger UI) | http://localhost:8000/api/docs |
| Health / readiness | http://localhost:8000/api/health · http://localhost:8000/api/ready |

## Demo accounts

Demo accounts exist only after `make seed`, and the sign-in page offers one-click buttons for them while
`DEMO_MODE=true`. Every demo account uses the published password **`EduShield!Demo2026`**. These are synthetic
accounts for a demonstration; never reuse the password anywhere real.

| Email | Person (fictional) | Role | Institution |
|---|---|---|---|
| `admin@edushield.demo` | Jordan Ellis | Platform Administrator | All institutions |
| `inst.admin@northbridge.demo` | Priya Raman | Institution Administrator | Northbridge State University |
| `investigator@northbridge.demo` | Marcus Bell | Fraud Investigator | Northbridge State University |
| `analyst@northbridge.demo` | Dana Whitfield | Fraud Investigator | Northbridge State University |
| `officer@northbridge.demo` | Elena Torres | Financial Aid Officer | Northbridge State University |
| `auditor@northbridge.demo` | Samuel Okafor | Read-only Auditor | Northbridge State University |
| `investigator@lakeshore.demo` | Hannah Kim | Fraud Investigator | Lakeshore Community College |
| `officer@pinecrest.demo` | Luis Ortega | Financial Aid Officer | Pinecrest Technical Institute |

What each role can do:

| Role | Can |
|---|---|
| Platform Administrator | Everything, across all institutions |
| Institution Administrator | Everything within one institution, including users and the audit trail |
| Fraud Investigator | Read records in scope (not the audit trail); review applications, re-run assessments, reveal names (with a reason), hold disbursements, run verifications, triage alerts, start detection runs |
| Financial Aid Officer | Read records in scope; review applications, reveal names (with a reason), hold disbursements, run verifications, triage alerts; cannot re-run assessments or start detection runs |
| Read-only Auditor | Read records and the audit trail; cannot change data or reveal names |

API clients can also authenticate with a bearer token from `POST /api/v1/auth/token` (OAuth2 password flow,
used by the Swagger UI "Authorize" button). Five failed sign-ins lock an account for 15 minutes.

## A five-minute walkthrough

1. Sign in as **`investigator@northbridge.demo`**.
2. Open **Fraud alerts**. The critical alert **"Possible identity impersonation"** concerns a student whose refund
   destination was changed. The person who asked for the change then failed step-up verification: the face did
   not match and a screen-replay attack was detected.
3. Open the application. The risk panel shows the score, every contributing signal with its points, the
   explanation, the method and the rule and model versions. The student's name is masked; **Reveal** asks for a
   reason and records it in the audit trail.
4. Choose **Verify identity**, pick a trigger and a synthetic test sample such as *Printed photo of the student*, and
   run it. The simulated provider reports each stage, the application is re-scored, and the recommended next step
   is shown.
5. Open **Detection engine**. It lists every rule and its weight, the anomaly model card, and a live
   **scenario coverage** check confirming that each planted scenario fires its expected signals and that legitimate
   controls stay below high.
6. Sign in as **`auditor@northbridge.demo`**: the same records are visible, names stay masked, and actions that change
   data are refused.
7. Sign in as **`investigator@lakeshore.demo`**: Northbridge's records are invisible. Each institution sees only its own
   data.

## How fraud detection works

```
 records ─► rules (17) ─┐
            graph ──────┼─► signals ─► noisy-OR score 0–100 ─► level ─► recommendation
            anomaly ────┘   (points,                            │       (no automatic action)
                             evidence,                          ▼
                             versions)                  high/critical ─► alert ─► person reviews,
                                                                          holds or clears, audited
```

1. **Signals.** Each rule inspects tokenized identity attributes, devices, network addresses, enrollment,
   disbursements and verification outcomes, and emits a signal with a weight and evidence. Examples:
   `SSN_IDENTITY_CONFLICT` (one SSN token behind different names or dates of birth), `DEVICE_BURST`
   (three or more applications from one device within 72 hours), `DESTINATION_SHARED` (one refund destination
   paying several students), `AMOUNT_OUTLIER`, `NO_ATTENDANCE`, `FACE_MISMATCH`, `PRESENTATION_ATTACK`. The full
   catalog with weights is in `backend/app/detection/catalog.py` and on the Detection engine page.
2. **Graph analysis.** Applications linked by shared identity tokens, devices or payment destinations form a graph.
   Members of a linked cluster of four or more applications receive a `NETWORK_CLUSTER` signal.
3. **Anomaly model.** An Isolation Forest flags the most unusual 4% of applications by behavioural features. Its
   influence is capped (weight 0.30), so it can raise attention but cannot make a record critical on its own. Each
   flag lists the features that drove it (occlusion attribution).
4. **Score.** Signals combine with a noisy-OR: `score = 100 × (1 − Π(1 − wᵢ))`. Each signal's share of the score is
   stored as its points.
5. **Level and recommendation.** Low below 30, medium 30–59, high 60–79, critical 80 and above. Each level maps to a
   recommendation, from "No action needed" to "Hold pending disbursements and open an investigation. No adverse
   action may be taken without human review."
6. **Alert.** High and critical assessments open or upgrade an alert. A person acknowledges, dismisses or reopens it.
   A dismissed alert is not re-raised unless the risk grows.
7. **Human action.** Review decisions (in review, cleared, escalated, optionally putting the application on hold),
   disbursement holds and releases are human actions, permission-checked and audited.

Every assessment is stamped with `rules-2026.10.1`, `iforest-0.1.0-synthetic` and `graph-2026.10.1`, so results
can be reproduced. A detection run over all records can be started from the Detection engine page or with
`POST /api/v1/detection/runs`.

## Identity verification (simulated)

When the risk calls for it, or when something sensitive happens (a payment-destination change, account recovery, a
new-device sign-in, before a disbursement, or a risk review), staff can request **step-up verification**.

- **Provider interface.** `backend/app/biometrics/provider.py` defines a vendor-neutral protocol. A real deployment
  would implement it for an authorized commercial identity-verification vendor.
- **Simulated provider.** This prototype ships `SimulatedBiometricProvider`, labelled as a simulation in the API
  (`provider_mode: "simulation"` and a "SIMULATED PROVIDER" disclaimer) and in the UI. It uses **no camera, no images and no
  biometric templates**. The operator chooses a synthetic test sample, and the provider derives repeatable scores
  for four stages: document check, face match, liveness, and presentation-attack detection.

| Synthetic test sample | Expected outcome |
|---|---|
| Enrolled student | Pass |
| Different person (impostor) | Fail: face mismatch |
| Impostor replaying a video | Fail: mismatch and presentation attack |
| Printed photo of the student | Fail: presentation attack |
| Altered identity document | Fail: suspicious document |
| Unreadable document (glare) | Inconclusive: manual review |

- **Thresholds (simulation).** Face match ≥ 0.80 passes and < 0.50 is a mismatch; liveness ≥ 0.70 passes.
- **Consent.** Biometric checks run only for students who consented. Otherwise the API refuses with
  `409 biometric_consent_required`, records the refusal in the audit trail, and staff use an alternative:
  **in-person ID check, officer video call or mailed code**, recorded with mandatory notes.
- **Effect.** The outcome is stored as scores and reason codes only, the application is re-scored immediately, a
  failure raises or upgrades the alert, and the response recommends a next step (for example, "Do not apply the
  requested payment-destination change"). A failed check never denies aid by itself.

## API

All endpoints are under `/api/v1`, documented interactively at `/api/docs` and exported to
[`docs/openapi.json`](docs/openapi.json). Requests are scoped to the caller's institution; records from other
institutions return `404`. Browser requests that change data must send the `X-EduShield-Client` header (CSRF
defence); the web client does this automatically.

| Area | Endpoints |
|---|---|
| System | `GET /api/health`, `GET /api/ready` |
| Auth | `POST /auth/login`, `POST /auth/token`, `POST /auth/logout`, `GET /auth/me`, `GET /auth/demo-accounts` (demo mode), `POST /auth/change-password` |
| Institutions and users | `GET/POST /organizations`, `PATCH /organizations/{id}`, `GET /roles`, `GET/POST /users`, `PATCH /users/{id}` |
| Applications | `GET /applications` (search, filter, sort, paginate), `GET /applications/{id}`, `PATCH /applications/{id}/review`, `POST /applications/{id}/assess` |
| Students | `POST /students/{id}/reveal` (justification required, audited) |
| Disbursements | `GET /disbursements`, `GET /disbursements/summary`, `GET /disbursements/{id}`, `POST /disbursements/{id}/hold`, `POST /disbursements/{id}/release` |
| Verifications | `GET /verifications/provider`, `GET /verifications`, `GET /verifications/stats`, `GET /verifications/{id}`, `POST /verifications`, `POST /verifications/alternative` |
| Alerts | `GET /alerts`, `GET /alerts/summary`, `GET /alerts/{id}`, `PATCH /alerts/{id}` |
| Detection | `GET /detection/status`, `POST /detection/runs`, `GET /detection/runs/{id}`, `GET /detection/scenario-validation` |
| Audit | `GET /audit/events`, `GET /audit/summary`, `GET /audit/verify` |

Example with a bearer token:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/token \
  -d 'username=investigator@northbridge.demo&password=EduShield!Demo2026' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8000/api/v1/alerts?page_size=5'
```

## Running the tests

```bash
make test             # backend (pytest) + frontend (Vitest)
make backend-test     # pytest: auth, RBAC and tenancy, audit chain, records, detection, verification
make frontend-test    # Vitest component tests
make lint             # ruff + ESLint
cd frontend && npm run typecheck   # TypeScript
make build            # production build of the web client (frontend/dist)
```

Backend tests run against real Alembic migrations on throwaway SQLite files, so they need no running services.

## Security and privacy

- **No raw identifiers stored.** SSNs, full dates of birth, contact details, devices and network addresses are
  stored only as keyed HMAC-SHA256 tokens (birth year is kept for context). Payment destinations keep only a token
  and a two-digit display label. Synthetic SSNs use area number `000`, which is never issued, and are discarded
  after tokenization.
- **Names encrypted and masked.** Student names are Fernet-encrypted and shown masked; revealing one needs the
  `pii:reveal` permission and a written reason, and is audited.
- **No biometric data.** Only scores, outcomes and reason codes are kept; the schema has no image or template
  columns, and a test checks for it.
- **Access control.** Five roles with explicit permissions, enforced by the API on every request; institution
  isolation enforced in queries; cross-institution matches reveal only that a match exists.
- **Sessions.** argon2id password hashes, httpOnly `SameSite=Strict` session cookie, CSRF header check, login rate
  limiting and account lockout, password change revokes sessions.
- **Audit trail.** Append-only, SHA-256 hash-chained; database triggers block updates and deletes; integrity is
  verifiable through the API.
- **Logs.** Structured JSON with redaction of passwords, tokens, SSN-shaped and bearer values; request bodies and
  query strings are not logged.
- **Production guards.** With `ENV=production` the API refuses to start with development secrets, without a data
  encryption key, or on SQLite.

## Known limitations

- **Simulated biometrics.** No real document, face, liveness or presentation-attack processing exists. The
  provider interface is ready for a vendor; none is integrated.
- **Synthetic data only.** The anomaly model and rule weights are tuned on synthetic data. **No accuracy, precision or
  recall is claimed**; the scenario coverage check proves only that planted scenarios fire their expected signals.
- **PostgreSQL not verified.** The code and migrations are written for PostgreSQL, but every test and demo so far
  has run on SQLite.
- **No container setup.** There are no Dockerfiles or compose files yet.
- **Screens not built yet:** dashboard analytics (the dashboard currently links to the working modules),
  investigation case management, the fraud network explorer, the audit center, institution and user
  administration, settings, global search and notifications. Their sidebar entries are marked "Planned". The
  institution, user and audit **APIs** exist.
- **Test coverage gaps.** There is no automated end-to-end browser test (the `make e2e` target has no tests yet), and
  the verification wizard has no component test; it has been exercised manually.
- **Single-process rate limiting.** The login limiter is in-process; a multi-instance deployment would need a shared
  store such as Redis.
- **Development secrets.** `.env.example` and the defaults contain development placeholders, and the demo password is
  published. Both are refused or must be changed for production.

## Roadmap

1. **Finish the investigator experience:** investigation cases (evidence, notes, timeline, assignment, resolution),
   the fraud network explorer, dashboard analytics, the audit center and institution, user and settings screens.
2. **Production readiness:** verified PostgreSQL deployment, container images, an end-to-end test suite, and
   Redis-backed rate limiting and job queues.
3. **Real identity verification:** integrate an authorized commercial identity-verification vendor through the
   existing provider interface, with an institutional contract, a privacy review and student-facing consent flows.
4. **Data integrations:** connections to student information and aid-management systems, only with institutional
   authorization and legal approval.
5. **Machine learning, carefully:** evaluate any trained model on real, labelled, consented data with fairness
   testing across student groups before it is allowed to influence scores, and keep human review mandatory.

See [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) for exactly what is AI, what is rules, what is simulated and what
is planned.
