'use client';

import React, { useState } from 'react';
import {
  Box, Button, TextField, Typography, Alert, CircularProgress,
  InputAdornment, IconButton, Stack,
} from '@mui/material';
import { useRouter } from 'next/navigation';
import { authApi, saveSession } from '@/lib/api';
import { IconEye, IconEyeOff, IconRoute, IconChartBar, IconShield } from '@tabler/icons-react';

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
      const { user } = res.data;
      saveSession('', user);
      router.push('/dashboard');
    } catch (err) {
      const axiosErr = err as { response?: { data?: { message?: string } } };
      setError(axiosErr.response?.data?.message || 'Credenciais inválidas. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const features = [
    { icon: <IconRoute size={20} />, text: 'Otimização VSP/CSP com 7 algoritmos' },
    { icon: <IconChartBar size={20} />, text: 'Redução de até 20% nos custos operacionais' },
    { icon: <IconShield size={20} />, text: 'Conformidade CCT e legislação brasileira' },
  ];

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex' }}>
      {/* Painel esquerdo — marca */}
      <Box
        sx={{
          display: { xs: 'none', md: 'flex' },
          flex: '0 0 55%',
          flexDirection: 'column',
          justifyContent: 'center',
          px: 8,
          background: 'linear-gradient(145deg, #615DFF 0%, #4a46d4 50%, #2ec8db 100%)',
          position: 'relative',
          overflow: 'hidden',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: '-30%',
            right: '-10%',
            width: '500px',
            height: '500px',
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.06)',
          },
          '&::after': {
            content: '""',
            position: 'absolute',
            bottom: '-20%',
            left: '-5%',
            width: '400px',
            height: '400px',
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.04)',
          },
        }}
      >
        <Stack direction="row" spacing={1.5} sx={{ mb: 6, position: 'relative', zIndex: 1, alignItems: 'center' }}>
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: 2,
              bgcolor: 'rgba(255,255,255,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <IconRoute size={28} color="white" />
          </Box>
          <Typography variant="h4" sx={{ fontWeight: 800, color: 'white', letterSpacing: 2 }}>
            OTIMIZ
          </Typography>
        </Stack>

        <Typography variant="h3" sx={{ fontWeight: 800, color: 'white', mb: 2, lineHeight: 1.2, position: 'relative', zIndex: 1 }}>
          Otimização inteligente de transporte urbano
        </Typography>
        <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.75)', mb: 5, fontSize: '1.05rem', position: 'relative', zIndex: 1 }}>
          Plataforma de escala e tripulação para empresas de ônibus do Brasil.
        </Typography>

        <Stack spacing={2.5} sx={{ position: 'relative', zIndex: 1 }}>
          {features.map((f, i) => (
            <Stack key={i} direction="row" spacing={2} sx={{ alignItems: 'center' }}>
              <Box
                sx={{
                  p: 1,
                  borderRadius: 1.5,
                  bgcolor: 'rgba(255,255,255,0.15)',
                  color: 'white',
                  display: 'flex',
                }}
              >
                {f.icon}
              </Box>
              <Typography sx={{ color: 'rgba(255,255,255,0.9)', fontWeight: 500 }}>
                {f.text}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Box>

      {/* Painel direito — formulário */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          px: { xs: 3, sm: 6, md: 8 },
          bgcolor: 'background.default',
        }}
      >
        <Box sx={{ width: '100%', maxWidth: 400 }}>
          <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 4, textAlign: 'center' }}>
            <Typography variant="h5" sx={{ fontWeight: 800, color: 'primary.main' }}>OTIMIZ</Typography>
          </Box>

          <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
            Bem-vindo de volta
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
            Entre com suas credenciais para acessar o sistema
          </Typography>

          {error && <Alert severity="error" variant="filled" sx={{ mb: 2 }}>{error}</Alert>}

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
            />
            <TextField
              label="Senha"
              type={showPwd ? 'text' : 'password'}
              fullWidth
              size="small"
              value={password}
              onChange={e => setPassword(e.target.value)}
              sx={{ mb: 1 }}
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

            <Box sx={{ textAlign: 'right', mb: 3 }}>
              <Typography
                component="a"
                href="/auth/forgot-password"
                variant="caption"
                sx={{ color: 'primary.main', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
              >
                Esqueci minha senha
              </Typography>
            </Box>

            <Button
              type="submit"
              variant="contained"
              fullWidth
              size="large"
              disabled={loading}
              sx={{
                background: 'linear-gradient(135deg, #615DFF 0%, #3DD9EB 100%)',
                fontWeight: 700,
                letterSpacing: 0.5,
                py: 1.2,
              }}
            >
              {loading ? <CircularProgress size={22} color="inherit" /> : 'Entrar'}
            </Button>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
