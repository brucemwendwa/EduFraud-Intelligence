# EduShield AI interview demonstration

Use synthetic data only. Hosted URL: **not available yet**; see [DEPLOYMENT.md](DEPLOYMENT.md). Host the demo with `ENV=demo` and
`DEMO_MODE=true` in its own project, then run `python -m app.seed` once.

| Person | Sign in as | Shows |
|---|---|---|
| Student | `student@northbridge.demo` | Student portal |
| Financial aid officer | `officer@northbridge.demo` | Review queue and decisions |
| Fraud investigator | `investigator@northbridge.demo` | Risk and investigations |
| Institution administrator | `inst.admin@northbridge.demo` | Users and operations |
| Another institution | `investigator@lakeshore.demo` | Tenant isolation |

Password for all demo accounts: `EduShield!Demo2026`. It is published and synthetic: never reuse it.

## The story

**The problem.** Aid fraud spreads across stolen identities, shared devices and accounts that collect refunds for many "students".
Each application can look normal alone, so one-at-a-time review misses the pattern, while blunt automation can harm real students.

**The approach.** One system handles the aid workflow and explains why something looks unusual, and a person makes every decision.

## Walkthrough, about 12 minutes

1. **Student (3 min).** Sign in and show the dashboard from real records. Create an application, save a draft, then submit.
   Say that students never see fraud scores or which staff role acted on their file.
2. **Staff queue (2 min).** Sign in as the officer. Show the live pipeline, then open the submitted application from Awaiting review.
3. **Explainable risk (2 min).** Show each signal with its points and evidence, the versions used, and the limitations list. Say
   plainly: this is a prioritisation aid and there is no accuracy claim.
4. **Human decision (2 min).** Request more information. Point out the internal note kept apart from the student message.
   Return as the student, see the request, respond and resubmit. Then record the decision as staff.
5. **Accountability (1 min).** Open the application's History tab, then Audit logs as the administrator. Run the integrity check.
6. **Operations (1 min).** Show Operations, and how live services are distinguished from simulated or unconfigured ones.
7. **Isolation (1 min).** Sign in as the Lakeshore investigator: Northbridge's records are not visible.

Evidence upload needs storage and a scanner, so include it only on an environment where Operations shows both as healthy.

## What is real

| Capability | State |
|---|---|
| Application lifecycle, permissions, tenant isolation, audit trail | Real, tested on PostgreSQL |
| Background jobs with Redis and Celery | Real, tested locally |
| ClamAV scanning | Real daemon tested locally with the official `daily` signatures |
| Risk rules, graph analysis and anomaly model | Real code on synthetic data, no performance claim |
| AWS S3 storage | Built; tested only against an emulator |
| Email through Resend | Built; no real message delivered |
| Sentry error monitoring | Built; no live project |
| Identity verification and biometrics | **Simulated. Never present as real.** |
| Payment provider and card controls | **Simulated sandbox. Never present as real.** |
| Student, institution and payment records | **Synthetic** |
| External fraud databases, government identity systems, SIS | **Not connected** |

## Architecture

A React client and FastAPI service ship in one container and share one origin. PostgreSQL holds records, Redis carries jobs and
shared limits, and a Celery worker runs scans, scoring and email. Evidence goes to private S3 storage and is released only after
ClamAV returns a clean result.

## Security model

- Sessions are `HttpOnly`, `Secure`, `SameSite=Strict` cookies, revoked on the server at sign-out.
- Every API route checks an explicit permission, and a test fails if a new route is left open.
- Institution scoping applies to every query. Out-of-scope records return 404.
- Identifiers are stored only as keyed tokens, and names are encrypted and masked until a reason is given.
- Evidence stays quarantined until scanned. Downloads are short-lived, version-bound and authorized per request.
- The audit trail is hash-chained, and database triggers refuse changes.

## How risk scoring works

Versioned rules, graph links and a capped anomaly model each emit signals with weights and evidence. They combine into a 0 to 100
score, and each signal shows its share. Each assessment stores its versions, training population and an input hash, and the score
can be recomputed from its stored signals. Income, age and other demographics are excluded. Scores order the work. They never approve,
deny or hold anything.

## Disclose these limitations

- There is no hosted environment yet, and S3 and email are unproven against real providers.
- Accuracy is unknown: nothing has been evaluated on real, labelled data.
- It is not production ready. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
