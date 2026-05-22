/**
 * Next.js App Router instrumentation hook.
 * Called once on server startup and once in the browser.
 * Sentry is initialized here — gracefully skips if NEXT_PUBLIC_SENTRY_DSN not set.
 *
 * Install: npm install @sentry/nextjs
 * Configure: NEXT_PUBLIC_SENTRY_DSN, SENTRY_ORG, SENTRY_PROJECT in .env
 */
export async function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  if (process.env.NEXT_RUNTIME === 'nodejs') {
    try {
      const Sentry = await import('@sentry/nextjs');
      Sentry.init({
        dsn,
        environment: process.env.NODE_ENV,
        tracesSampleRate: 0.1,
        // Don't send source maps to Sentry unless SENTRY_AUTH_TOKEN is set
      });
    } catch {
      // @sentry/nextjs not installed — acceptable in dev
    }
  }

  if (process.env.NEXT_RUNTIME === 'edge') {
    try {
      const Sentry = await import('@sentry/nextjs');
      Sentry.init({ dsn, environment: process.env.NODE_ENV });
    } catch {}
  }
}
