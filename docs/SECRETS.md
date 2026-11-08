# Configuration and secret inventory

Set values in the hosting provider's variables store. Never put them in the repository, a chat or a ticket. A test fails if a
setting exists in the code but not here.

Web, worker and scheduler need the same values unless a row says otherwise.

## Secrets

| Variable | Source | Rotation |
|---|---|---|
| `JWT_SECRET` | Generate: 48 random bytes | Safe at any time. Signs everyone out. |
| `TOKENIZATION_KEY` | Generate: 48 random bytes | **Do not rotate** without re-tokenizing identity records: duplicate matching depends on it. |
| `DATA_ENCRYPTION_KEY` | Generate: Fernet key | **Do not rotate** without re-encrypting student names. Losing it loses those names. |
| `PROVIDER_WEBHOOK_SECRET` | Generate: 32 random bytes | Coordinate with the event sender. |
| `DATABASE_URL` | Provided by the database service | Contains a password; rotate at the database. |
| `CELERY_BROKER_URL` | Provided by Redis | Contains a password. |
| `RATE_LIMIT_REDIS_URL` | Optional; provided by Redis | Contains a password. Defaults to the broker. |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | AWS IAM user limited to the bucket | Create a new key, deploy, then delete the old one. |
| `SMTP_PASSWORD` | Resend API key with sending access only | Create a new key, deploy, then revoke the old one. |
| `SENTRY_DSN` | Optional; Sentry project | Regenerate in Sentry. |

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                               # JWT_SECRET, TOKENIZATION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # DATA_ENCRYPTION_KEY
```

Back up `TOKENIZATION_KEY` and `DATA_ENCRYPTION_KEY` separately from the database. A database restore is useless without them.

## Environment

| Variable | Staging | Production |
|---|---|---|
| `ENV` | `demo` | `production` |
| `DEMO_MODE` | `true` | `false` |
| `CORS_ORIGINS` | The staging origin | The exact production origin |
| `PUBLIC_URL` | `https://<staging host>` | `https://<production host>` |
| `STUDENT_ACTIVATION_BASE_URL` | `https://<staging host>/activate` | `https://<production host>/activate` |
| `FRONTEND_DIST` | Set by the image | Set by the image |

`CLIENT_IP_HEADER` names a header the platform itself sets to the caller's address, for sign-in limits and audit records. Use
`X-Real-IP` on Railway, on the web service only. Leave it unset anywhere a client could send that header directly, and confirm it
with `scripts/verify_deployment.py --check-rate-limit`, which forges these headers.

## Storage, scanning and email

| Variable | Value |
|---|---|
| `S3_BUCKET_NAME`, `S3_REGION` | The private bucket |
| `S3_ENDPOINT_URL` | Unset for AWS |
| `S3_USE_TLS`, `S3_ADDRESSING_STYLE` | `true`, `auto` |
| `S3_PRESIGNED_URL_TTL_SECONDS` | `300` or lower |
| `DOCUMENT_SCANNER_PROVIDER` | `clamav` |
| `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_TIMEOUT_SECONDS` | The private hostname, `3310`, `90` |
| `DOCUMENT_MAX_UPLOAD_BYTES` | Default 10 MB; must stay below clamd's `StreamMaxLength` |
| `DOCUMENT_SCAN_MAX_ATTEMPTS`, `DOCUMENT_SCAN_LEASE_SECONDS`, `DOCUMENT_SCAN_RETRY_BASE_SECONDS` | Defaults |
| `EMAIL_PROVIDER`, `EMAIL_FROM` | `smtp`, an address on the verified domain |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` | `smtp.resend.com`, `587`, `resend` |

## Defaults that rarely change

| Variable | Default |
|---|---|
| `APP_NAME`, `APP_VERSION` | Set in code |
| `JWT_ALGORITHM`, `SESSION_COOKIE_NAME` | `HS256`, `edushield_session` |
| `ACCESS_TOKEN_TTL_MINUTES` | `60` |
| `LOGIN_MAX_ATTEMPTS`, `LOCKOUT_MINUTES` | `5`, `15` |
| `STUDENT_INVITATION_TTL_HOURS`, `PASSWORD_RESET_TTL_MINUTES` | `72`, `30` |
| `ACCOUNT_RISK_WEIGHTS` | Unset |
