'use client';

import React, { useState } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Stack, Switch,
  FormControlLabel, Button, Divider, Select, MenuItem,
  FormControl, InputLabel, Snackbar, Alert, TextField, Chip,
} from '@mui/material';
import {
  IconBell, IconPalette, IconWorld, IconShieldLock,
} from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { useContext } from 'react';
import { CustomizerContext } from '@/app/context/customizerContext';

function SectionCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 2 }}>
          {icon}
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{title}</Typography>
        </Stack>
        <Divider sx={{ mb: 2 }} />
        {children}
      </CardContent>
    </Card>
  );
}

export default function GeneralSettingsPage() {
  const {
    activeMode, setActiveMode,
    activeTheme, setActiveTheme,
    isLayout, setIsLayout,
    isBorderRadius, setIsBorderRadius,
    activeDir, setActiveDir,
  } = useContext(CustomizerContext);

  const [notifications, setNotifications] = useState({
    emailOnComplete: true,
    emailOnError: true,
    browserPush: false,
  });
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
  };

  const themes = [
    { value: 'BLUE_THEME', label: 'Azul (padrão)' },
    { value: 'GREEN_THEME', label: 'Verde' },
    { value: 'AQUA_THEME', label: 'Aqua' },
    { value: 'PURPLE_THEME', label: 'Roxo' },
    { value: 'ORANGE_THEME', label: 'Laranja' },
  ];

  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Configurações Gerais"
        subtitle="Preferências globais de aparência, notificações e sistema"
        action={
          <Button variant="contained" size="small" onClick={handleSave}>
            Salvar Preferências
          </Button>
        }
      >
        <Stack spacing={3} sx={{ mt: 1 }}>

          {/* ── Aparência ── */}
          <SectionCard title="Aparência e Tema" icon={<IconPalette size={20} color="#1976d2" />}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Modo de Cor</InputLabel>
                  <Select label="Modo de Cor" value={activeMode}
                    onChange={(e) => setActiveMode(e.target.value as 'light' | 'dark')}>
                    <MenuItem value="light">Claro</MenuItem>
                    <MenuItem value="dark">Escuro</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Tema de Cor</InputLabel>
                  <Select label="Tema de Cor" value={activeTheme}
                    onChange={(e) => setActiveTheme(e.target.value)}>
                    {themes.map((t) => (
                      <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Layout do Container</InputLabel>
                  <Select label="Layout do Container" value={isLayout}
                    onChange={(e) => setIsLayout(e.target.value as 'boxed' | 'full')}>
                    <MenuItem value="boxed">Boxed (centralizado)</MenuItem>
                    <MenuItem value="full">Full Width</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Direção do Texto</InputLabel>
                  <Select label="Direção do Texto" value={activeDir}
                    onChange={(e) => setActiveDir(e.target.value as 'ltr' | 'rtl')}>
                    <MenuItem value="ltr">LTR (Esquerda → Direita)</MenuItem>
                    <MenuItem value="rtl">RTL (Direita → Esquerda)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <Stack spacing={1}>
                  <Typography variant="body2" color="text.secondary">
                    Raio de Borda: <strong>{isBorderRadius}px</strong>
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                    {[4, 7, 12, 16, 20].map((r) => (
                      <Chip
                        key={r}
                        label={`${r}px`}
                        size="small"
                        variant={isBorderRadius === r ? 'filled' : 'outlined'}
                        color={isBorderRadius === r ? 'primary' : 'default'}
                        onClick={() => setIsBorderRadius(r)}
                        sx={{ cursor: 'pointer' }}
                      />
                    ))}
                  </Stack>
                </Stack>
              </Grid>
            </Grid>
          </SectionCard>

          {/* ── Notificações ── */}
          <SectionCard title="Notificações" icon={<IconBell size={20} color="#e65100" />}>
            <Stack spacing={1}>
              <FormControlLabel
                control={
                  <Switch checked={notifications.emailOnComplete}
                    onChange={(e) => setNotifications((n) => ({ ...n, emailOnComplete: e.target.checked }))} />
                }
                label="Receber e-mail quando otimização concluir"
              />
              <FormControlLabel
                control={
                  <Switch checked={notifications.emailOnError}
                    onChange={(e) => setNotifications((n) => ({ ...n, emailOnError: e.target.checked }))} />
                }
                label="Receber e-mail em caso de erro na otimização"
              />
              <FormControlLabel
                control={
                  <Switch checked={notifications.browserPush}
                    onChange={(e) => setNotifications((n) => ({ ...n, browserPush: e.target.checked }))} />
                }
                label="Notificações push no navegador"
              />
            </Stack>
          </SectionCard>

          {/* ── Localização ── */}
          <SectionCard title="Localização e Idioma" icon={<IconWorld size={20} color="#2e7d32" />}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Idioma do Sistema</InputLabel>
                  <Select label="Idioma do Sistema" defaultValue="pt-BR">
                    <MenuItem value="pt-BR">Português (Brasil)</MenuItem>
                    <MenuItem value="en">English</MenuItem>
                    <MenuItem value="es">Español</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <FormControl fullWidth size="small">
                  <InputLabel>Fuso Horário</InputLabel>
                  <Select label="Fuso Horário" defaultValue="America/Sao_Paulo">
                    <MenuItem value="America/Sao_Paulo">America/São Paulo (BRT -3)</MenuItem>
                    <MenuItem value="America/Manaus">America/Manaus (AMT -4)</MenuItem>
                    <MenuItem value="America/Belem">America/Belém (BRT -3)</MenuItem>
                    <MenuItem value="America/Fortaleza">America/Fortaleza (BRT -3)</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </SectionCard>

          {/* ── Segurança ── */}
          <SectionCard title="Segurança e Sessão" icon={<IconShieldLock size={20} color="#c62828" />}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth size="small" type="number"
                  label="Timeout de Sessão (minutos)"
                  defaultValue={60}
                  helperText="Sessão encerrada automaticamente após inatividade."
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <Stack spacing={1}>
                  <FormControlLabel
                    control={<Switch defaultChecked />}
                    label="Exigir confirmação ao excluir dados"
                  />
                  <FormControlLabel
                    control={<Switch defaultChecked />}
                    label="Registrar log de auditoria de ações"
                  />
                </Stack>
              </Grid>
            </Grid>
          </SectionCard>

          <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button variant="contained" size="large" onClick={handleSave}>
              Salvar Preferências
            </Button>
          </Box>
        </Stack>
      </DashboardCard>

      <Snackbar open={saved} autoHideDuration={3000} onClose={() => setSaved(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity="success" variant="filled">Preferências salvas com sucesso!</Alert>
      </Snackbar>
    </Box>
  );
}
