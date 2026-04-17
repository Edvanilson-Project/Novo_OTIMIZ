'use client';

import React, { useState } from 'react';
import {
  Box, Button, TextField, Typography, Alert, CircularProgress, Paper, InputAdornment, IconButton,
} from '@mui/material';
import { useRouter } from 'next/navigation';
import { authApi, saveSession } from '@/lib/api';
import { IconEye, IconEyeOff } from '@tabler/icons-react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('Preencha e-mail e senha.'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(email, password);
      const { access_token, user } = res.data;
      saveSession(access_token, user);
      router.push('/');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Credenciais inválidas. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'background.default', p: 2 }}>
      <Paper elevation={3} sx={{ p: 4, width: '100%', maxWidth: 400 }}>
        <Box sx={{ mb: 3, textAlign: 'center' }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>OTIMIZ</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            Plataforma de Otimização de Transportes
          </Typography>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box component="form" onSubmit={handleSubmit}>
          <TextField
            label="E-mail"
            type="email"
            fullWidth
            size="small"
            value={email}
            onChange={e => setEmail(e.target.value)}
            sx={{ mb: 2 }}
            autoComplete="email"
            autoFocus
          />
          <TextField
            label="Senha"
            type={showPwd ? 'text' : 'password'}
            fullWidth
            size="small"
            value={password}
            onChange={e => setPassword(e.target.value)}
            sx={{ mb: 3 }}
            autoComplete="current-password"
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setShowPwd(v => !v)} edge="end">
                      {showPwd ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={loading}
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
