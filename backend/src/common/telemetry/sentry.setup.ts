/**
 * Sentry error tracking — gracefully no-ops if SENTRY_DSN is not set.
 * Call initSentry() before NestFactory.create() in main.ts.
 *
 * Install: npm install @sentry/node @sentry/profiling-node
 * Configure via env: SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE
 */

let sentryLoaded = false;

export function initSentry(): void {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return; // dev / CI — skip silently

  try {
    // Dynamic require so the app starts even if @sentry/node is not installed
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Sentry = require('@sentry/node');
    Sentry.init({
      dsn,
      environment: process.env.SENTRY_ENVIRONMENT ?? process.env.NODE_ENV ?? 'production',
      release: process.env.SENTRY_RELEASE ?? process.env.npm_package_version,
      tracesSampleRate: 0.2, // 20% of requests — adjust based on traffic
      profilesSampleRate: 0.1,
      integrations: [Sentry.httpIntegration(), Sentry.expressIntegration()],
      beforeSend(event: any) {
        // Strip PII from events
        if (event.user) {
          delete event.user.ip_address;
          delete event.user.email;
        }
        return event;
      },
    });
    sentryLoaded = true;
    console.log(`[Sentry] Initialized (env: ${process.env.SENTRY_ENVIRONMENT ?? process.env.NODE_ENV})`);
  } catch (err) {
    console.warn('[Sentry] Failed to initialize — @sentry/node not installed?', (err as Error).message);
  }
}

export function captureException(err: unknown, context?: Record<string, unknown>): void {
  if (!sentryLoaded) return;
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Sentry = require('@sentry/node');
    Sentry.withScope((scope: any) => {
      if (context) scope.setExtras(context);
      Sentry.captureException(err);
    });
  } catch {}
}
