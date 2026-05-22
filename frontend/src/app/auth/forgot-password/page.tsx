'use client';

import React, { useState } from 'react';
import {
  Box, Button, TextField, Typography, Alert, CircularProgress, Paper,
} from '@mui/material';
import Link from 'next/link';
import { apiClient } from '@/lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) { setError('Informe seu e-mail.'); return; }
    setLoading(true);
    setError('');
    try {
      await apiClient.post('/auth/forgot-password', { email });
      setSent(true);
    } catch {
      // Backend always returns 200 — any error here is a network issue
      setError('Erro ao enviar a solicitação. Verifique sua conexão.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'background.default', p: 2 }}>
      <Paper elevation={3} sx={{ p: 4, width: '100%', maxWidth: 400 }}>
        <Box sx={{ mb: 3, textAlign: 'center' }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>OTIMIZ</Typography>
          <Typography variant="subtitle2" color="text.secondary">Redefinição de senha</Typography>
        </Box>

        {sent ? (
          <Alert severity="success" sx={{ mb: 2 }}>
            Se este e-mail estiver cadastrado, você receberá as instruções em breve.
            Verifique sua caixa de entrada (e a pasta de spam).
          </Alert>
        ) : (
          <form onSubmit={handleSubmit}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Informe seu e-mail e enviaremos um link para redefinir sua senha.
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <TextField
              label="E-mail"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              fullWidth
              size="small"
              sx={{ mb: 2 }}
              autoFocus
            />
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={loading}
              sx={{ mb: 2 }}
            >
              {loading ? <CircularProgress size={20} color="inherit" /> : 'Enviar link de redefinição'}
            </Button>
          </form>
        )}

        <Box sx={{ textAlign: 'center' }}>
          <Link href="/auth/login" style={{ textDecoration: 'none' }}>
            <Typography variant="body2" color="primary">← Voltar ao login</Typography>
          </Link>
        </Box>
      </Paper>
    </Box>
  );
}
