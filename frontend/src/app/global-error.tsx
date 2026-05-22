'use client';

import React, { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error, {
      tags: { errorDigest: error.digest, scope: 'global' },
      level: 'fatal',
    });
  }, [error]);
  return (
    <html lang="pt-br">
      <body>
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'monospace',
          backgroundColor: '#1a1a2e',
          color: '#e0e0e0',
          padding: '24px',
        }}>
          <div style={{ maxWidth: 640, width: '100%' }}>
            <h1 style={{ color: '#ff6b6b', marginBottom: 8 }}>Erro na aplicação</h1>
            <p style={{ color: '#aaa', marginBottom: 24 }}>
              Ocorreu um erro crítico durante o carregamento da página.
            </p>
            <div style={{
              background: '#0d1117',
              border: '1px solid #30363d',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
            }}>
              {/* Never expose stack traces to users — log internally instead */}
              <p style={{ color: '#aaa', margin: 0 }}>
                Se o problema persistir, entre em contato com o suporte informando o código de erro.
              </p>
              {error.digest && (
                <p style={{ marginTop: 8, color: '#666', fontSize: 12 }}>
                  Código: <code>{error.digest}</code>
                </p>
              )}
            </div>
            <button
              onClick={reset}
              style={{
                background: '#238636',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                padding: '8px 20px',
                cursor: 'pointer',
                fontSize: 14,
              }}
            >
              Tentar novamente
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
