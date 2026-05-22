/**
 * Type stub for @sentry/nextjs — declared locally so we don't bundle the
 * real package (~5 MB) until the team decides to enable Sentry in production.
 *
 * `src/instrumentation.ts` does `await import('@sentry/nextjs')` inside a
 * try/catch — if the package is not installed at runtime, the catch swallows
 * the error and instrumentation is a no-op. This declaration just makes the
 * compile-time import resolvable.
 *
 * When/if the team installs @sentry/nextjs for real, delete this file.
 */
declare module '@sentry/nextjs' {
  export interface InitOptions {
    dsn: string;
    environment?: string;
    tracesSampleRate?: number;
    [key: string]: unknown;
  }

  export function init(options: InitOptions): void;
}
