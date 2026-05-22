'use client';

import React, { useState, Suspense } from 'react';
import {
  Box, Button, TextField, Typography, Alert, CircularProgress, Paper, InputAdornment, IconButton,
} from '@mui/material';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { IconEye, IconEyeOff } from '@tabler/icons-react';
import { apiClient } from '@/lib/api';

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) { setError('Link inválido. Solicite um novo link de redefinição.'); return; }
    if (password.length < 8) { setError('A senha deve ter no mínimo 8 caracteres.'); return; }
    if (password !== confirm) { setError('As senhas não coincidem.'); return; }

    setLoading(true);
    setError('');
    try {
      await apiClient.post('/auth/reset-password', { token, newPassword: password });
      setSuccess(true);
      setTimeout(() => router.push('/auth/login'), 3000);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Erro ao redefinir a senha. O link pode ter expirado.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <Alert severity="error">
        Link inválido ou expirado.{' '}
        <Link href="/auth/forgot-password">Solicitar novo link</Link>
      </Alert>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      {success ? (
        <Alert severity="success">
          Senha redefinida com sucesso! Redirecionando para o login...
        </Alert>
      ) : (
        <>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <TextField
            label="Nova senha"
            type={showPwd ? 'text' : 'password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
            fullWidth
            size="small"
            sx={{ mb: 2 }}
            autoFocus
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPwd(v => !v)} size="small">
                      {showPwd ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
          <TextField
            label="Confirmar senha"
            type={showPwd ? 'text' : 'password'}
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            fullWidth
            size="small"
            sx={{ mb: 2 }}
          />
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={loading}
            sx={{ mb: 2 }}
          >
            {loading ? <CircularProgress size={20} color="inherit" /> : 'Redefinir senha'}
          </Button>
        </>
      )}
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'background.default', p: 2 }}>
      <Paper elevation={3} sx={{ p: 4, width: '100%', maxWidth: 400 }}>
        <Box sx={{ mb: 3, textAlign: 'center' }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>OTIMIZ</Typography>
          <Typography variant="subtitle2" color="text.secondary">Criar nova senha</Typography>
        </Box>

        <Suspense fallback={<CircularProgress />}>
          <ResetPasswordForm />
        </Suspense>

        <Box sx={{ textAlign: 'center', mt: 2 }}>
          <Link href="/auth/login" style={{ textDecoration: 'none' }}>
            <Typography variant="body2" color="primary">← Voltar ao login</Typography>
          </Link>
        </Box>
      </Paper>
    </Box>
  );
}
