# Production readiness

Status as of 9 November 2026, with the repository at or after `686fcde`. **EduShield AI is not production ready.** No hosted environment exists yet, and several controls
depend on accounts and institutional decisions listed below. Update this file with evidence as each item closes.

Status key: **Verified** was tested on real local services. **Needs hosting** is built, but must be proven on the real environment.
**Needs provider** requires an external account. **Needs decision** requires an institutional or legal owner.

| Area | Status | Evidence or gap | Owner action |
|---|---|---|---|
| Hosted environment | Needs hosting | None exists. `scripts/verify_deployment.py` is ready. | Approve a host and grant access |
| TLS | Needs hosting | Terminated by the platform. The verifier checks HTTPS and redirects. | Provide a domain |
| Session cookies | Verified | `Secure`, `HttpOnly`, `SameSite=Strict`, `/api` path in `ENV=demo` and `production`. | Re-run the verifier when hosted |
| Sign-out and session invalidation | Verified | A copied cookie is refused after sign-out, in a browser test. | None |
| CORS and CSRF | Verified | Foreign origins and missing client headers are refused. | Set the exact origin when hosted |
| Rate limiting | Verified locally | Limit held at 20 across two API instances on real Redis, and against forged client headers. | Run `--check-rate-limit` on staging to prove the platform header cannot be spoofed |
| Account recovery | Verified, email unproven | Single-use hashed links; no account disclosure. Delivery needs Resend. | Configure Resend |
| Secrets | Needs hosting | Refuses development values. None in the repository. | Generate them and store in the host's secret store; rotate on staff change |
| Database | Verified locally | All 14 migrations on PostgreSQL 16, no model drift. | Provision a managed instance |
| Backups | Needs provider | Procedure proven locally only. Host backups not configured. | Enable daily backups and point-in-time recovery |
| Restore testing | Verified locally | `pg_restore` matched row counts, kept the audit triggers and the audit chain verified. | Rehearse on the host each quarter |
| Migration rollback | Verified locally | 0011 to 0014 ran down and up with data. Older downgrades can fail on data that no longer fits. | Back up first; prefer a forward fix after real data exists |
| Redis availability | Needs hosting | Sign-in limits and uploads survive an outage; jobs wait for recovery. | Use a managed instance with persistence |
| Worker and scheduler | Needs hosting | Run as separate processes locally. Operations reports a stopped scheduler as down within 3 minutes. | Keep one scheduler; alert on restarts |
| Storage encryption and privacy | Needs provider | Adapter checked against an emulator only. Policies are in `deploy/aws`. | Create the bucket; pass `scripts/verify_s3.py` |
| Storage retention | Needs decision | Replaced versions expire after 30 days in `lifecycle.json`, a placeholder. | Set retention to the records schedule |
| Malware scanning | Needs hosting | Real clamd with the official `daily` set and the staging limits. Outage and recovery proven. `main` set not yet loaded. | Deploy the private service |
| Email deliverability | Needs provider | Real STARTTLS, certificate and login exchange passed against a local server. No message delivered to a real inbox. | Verify a domain with Resend; run `scripts/verify_email.py` |
| Error monitoring | Needs provider | Scrubbing proven against the real SDK locally. | Create a Sentry project and set `SENTRY_DSN` |
| Logging | Verified locally | JSON, request IDs, redaction. | Set retention on the host |
| Operational alerts | Needs hosting | Signals exist on Operations; nothing pages anyone. | Alert on `/api/ready`, restarts and new errors |
| Tenant isolation | Verified | Backend and browser tests. | None |
| Audit trail | Verified | Append-only triggers and hash chain, on PostgreSQL. | Export to separate storage for real use |
| Accessibility | Verified | Automated WCAG A/AA, keyboard and responsive checks on the main screens. | Add testing with assistive-technology users |
| Demo-data isolation | Verified | `ENV=production` refuses demo mode, and demo accounts cannot sign in without it. | Keep separate projects and databases |
| Risk model validity | Needs decision | No real-world performance is established. The evaluation framework refuses ungoverned data. | Governed evaluation, including fairness across student groups, before relying on scores |
| Privacy and retention policy | Needs decision | Not written. Student records in the US are likely subject to FERPA. | Institutional counsel to define policy, a data processing agreement and retention |
| Incident response | Needs decision | Technical steps below; no named owners. | Assign owners and a contact path |
| Penetration test | Needs decision | Not done. | Commission an independent test before real data |

## How each result was obtained

| Kind | What it covers | Examples |
|---|---|---|
| Unit | Logic in isolation | Permissions, lifecycle rules, scanner replies, score recomputation |
| Mocked integration | Real API and database, with a stand-in for an outside service | Storage adapter stand-in, recorded email, fake Redis |
| Local infrastructure | Real services on one machine | PostgreSQL 16, Redis, Celery worker and Beat, ClamAV with the `daily` set, STARTTLS mail exchange, browser journeys. S3 here is an emulator. |
| Real hosted integration | The deployed environment and real providers | **None yet** |

## Incident response, technical steps

1. **Contain.** Deactivate affected accounts on the Institutions and users page, which ends their sessions immediately.
2. **Preserve.** Export the audit trail and logs. Run the integrity check on the Audit logs page.
3. **Rotate.** Changing `JWT_SECRET` signs everyone out. Rotate S3 and SMTP keys in their consoles. Never rotate `TOKENIZATION_KEY` or
   `DATA_ENCRYPTION_KEY` without a re-encryption plan, because existing records depend on them.
4. **Recover.** Restore the latest verified backup into a new database and verify the audit chain before switching over.
5. **Notify.** Follow the institution's breach notification procedure.

## Readiness verdict

| Level | Verdict | What is missing |
|---|---|---|
| Interview demonstration | Ready locally, with disclosures. Not yet hosted. | A hosted URL for evidence upload |
| Controlled pilot | Not ready | Hosted environment, real S3 and email, backups, privacy agreement and a penetration test |
| Production | Not ready | All of the above, plus governed risk evaluation, retention policy, on-call and audited operations |
