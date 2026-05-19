'use client';

import React from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
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
              overflowX: 'auto',
            }}>
              <strong style={{ color: '#ff6b6b' }}>{error.name}: </strong>
              <span>{error.message}</span>
              {error.stack && (
                <pre style={{ marginTop: 12, fontSize: 12, color: '#888', whiteSpace: 'pre-wrap' }}>
                  {error.stack}
                </pre>
              )}
              {error.digest && (
                <p style={{ marginTop: 8, color: '#666', fontSize: 12 }}>digest: {error.digest}</p>
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
