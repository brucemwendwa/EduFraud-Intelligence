import { database, defineRailway, image, preserve, project, redis, service } from "railway/iac";

/**
 * Staging: synthetic data only, in a project of its own.
 * Secrets are never written here. preserve() keeps values set through Railway's variables.
 */
const GB = 1024 ** 3;
const limit = (gigabytes: number) => ({ limitOverride: { containers: { memoryBytes: gigabytes * GB } } });

export default defineRailway(() => {
  // Pinned to the major version the migrations and browser journeys were tested on.
  const db = database("postgres", "postgres", {
    image: "ghcr.io/railwayapp-templates/postgres-ssl:16",
    output: "DATABASE_URL",
    defaultMountPath: "/var/lib/postgresql/data",
  });
  const cache = redis("redis");

  // Private only: never add a domain or TCP proxy here. clamd's port has no authentication.
  const clamav = service("clamav", {
    source: image("clamav/clamav:1.5"),
    env: {
      CLAMD_CONF_MaxThreads: "4",
      CLAMD_CONF_MaxQueue: "32",
      CLAMD_CONF_StreamMaxLength: "12M",
      CLAMD_CONF_ReadTimeout: "60",
      CLAMD_CONF_CommandReadTimeout: "10",
      // Pauses scanning briefly during updates instead of holding two signature sets in memory.
      CLAMD_CONF_ConcurrentDatabaseReload: "no",
    },
    deploy: { restartPolicyType: "ALWAYS", ...limit(3) },
  });

  const shared = {
    ENV: "demo",
    DEMO_MODE: "true",
    DATABASE_URL: db.env.DATABASE_URL,
    CELERY_BROKER_URL: cache.env.REDIS_URL,
    CORS_ORIGINS: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    PUBLIC_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    STUDENT_ACTIVATION_BASE_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}/activate",
    DOCUMENT_SCANNER_PROVIDER: "clamav",
    CLAMAV_HOST: clamav.env.RAILWAY_PRIVATE_DOMAIN,
    CLAMAV_PORT: "3310",
    CLAMAV_TIMEOUT_SECONDS: "90",
    JWT_SECRET: preserve(),
    TOKENIZATION_KEY: preserve(),
    PROVIDER_WEBHOOK_SECRET: preserve(),
    DATA_ENCRYPTION_KEY: preserve(),
    S3_BUCKET_NAME: preserve(),
    S3_REGION: preserve(),
    S3_ACCESS_KEY_ID: preserve(),
    S3_SECRET_ACCESS_KEY: preserve(),
    EMAIL_PROVIDER: preserve(),
    EMAIL_FROM: preserve(),
    SMTP_HOST: preserve(),
    SMTP_USERNAME: preserve(),
    SMTP_PASSWORD: preserve(),
    SENTRY_DSN: preserve(),
  };
  const build = { builder: "DOCKERFILE" as const, dockerfilePath: "Dockerfile" };

  const web = service("web", {
    build,
    preDeploy: "alembic upgrade head",
    healthcheck: "/api/ready",
    healthcheckTimeout: 120,
    env: { ...shared, CLIENT_IP_HEADER: "X-Real-IP" },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 10, ...limit(2) },
  });

  const worker = service("worker", {
    build,
    start: "celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --concurrency=2",
    env: shared,
    deploy: { restartPolicyType: "ALWAYS", ...limit(2) },
  });

  // Exactly one replica: a second scheduler would dispatch every job twice.
  const scheduler = service("scheduler", {
    build,
    start: "celery -A app.workers.celery_app:celery_app beat --schedule=/tmp/celerybeat-schedule --loglevel=INFO",
    replicas: 1,
    env: shared,
    deploy: { restartPolicyType: "ALWAYS", ...limit(1) },
  });

  return project("edushield-staging", { resources: [db, cache, clamav, web, worker, scheduler] });
});
