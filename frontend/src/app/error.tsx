'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error, {
      tags: { errorDigest: error.digest },
      level: 'error',
    });
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-100 p-6">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold text-red-400">Algo deu errado</h2>
          <p className="text-gray-400 text-sm">
            Ocorreu um erro inesperado nesta página.
          </p>
          {error.digest && (
            <p className="text-xs text-gray-600">
              Código: <code className="font-mono">{error.digest}</code>
            </p>
          )}
        </div>
        <button
          onClick={reset}
          className="px-6 py-2 bg-green-700 hover:bg-green-600 text-white rounded-md text-sm font-medium transition-colors"
        >
          Tentar novamente
        </button>
      </div>
    </div>
  );
}
