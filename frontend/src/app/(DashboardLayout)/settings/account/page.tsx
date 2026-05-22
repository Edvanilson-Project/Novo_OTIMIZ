'use client';

import React, { useState } from 'react';
import {
  Box, Button, Card, CardContent, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, Stack, Typography, Alert, CircularProgress,
  TextField,
} from '@mui/material';
import { IconDownload, IconTrash, IconAlertTriangle } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';
import { usersApi } from '@/lib/api';
import { useRouter } from 'next/navigation';

export default function AccountSettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');

  const handleExportData = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await usersApi.exportMyData();
      // Create a blob and download
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dados-pessoais-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setSuccess('Dados exportados com sucesso!');
    } catch {
      setError('Erro ao exportar dados. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleAnonymizeAccount = async () => {
    if (deleteConfirmation !== 'anonimizar minha conta') {
      setError('Você deve digitar exatamente "anonimizar minha conta" para confirmar.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await usersApi.anonymizeMyAccount();
      setSuccess('Sua conta foi anonimizada com sucesso. Você será desconectado em alguns segundos...');
      setDeleteDialogOpen(false);
      // Redirect to login after a delay
      setTimeout(() => {
        router.push('/auth/login');
      }, 2000);
    } catch {
      setError('Erro ao anonimizar conta. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardCard title="Configurações da Conta">
      <Box sx={{ width: '100%', maxWidth: 600 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        <Stack spacing={3}>
          {/* Data Export Section */}
          <Card variant="outlined">
            <CardContent>
              <Stack spacing={1.5}>
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
                    Exportar Meus Dados (LGPD Art. 18 §2)
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Baixe uma cópia de todos os seus dados pessoais em formato JSON. Isso inclui seu perfil, preferências e histórico associado.
                  </Typography>
                </Box>
                <Divider />
                <Box>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<IconDownload size={18} />}
                    onClick={handleExportData}
                    disabled={loading}
                  >
                    {loading ? 'Exportando...' : 'Exportar Dados'}
                  </Button>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {/* Account Deletion Section */}
          <Card variant="outlined" sx={{ borderColor: '#f44336' }}>
            <CardContent>
              <Stack spacing={1.5}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <IconAlertTriangle size={20} color="#f44336" />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#f44336' }}>
                    Anonimizar Minha Conta (LGPD Art. 18 §6)
                  </Typography>
                </Box>
                <Typography variant="body2" color="textSecondary">
                  Anonimiza todos os seus dados pessoais identificáveis. Os registros de auditoria serão mantidos (obrigação legal). <strong>Esta ação é irreversível.</strong>
                </Typography>
                <Divider />
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<IconTrash size={18} />}
                  onClick={() => setDeleteDialogOpen(true)}
                  disabled={loading}
                >
                  Anonimizar Conta
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Stack>

        {/* Confirmation Dialog */}
        <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, color: '#f44336' }}>
            <IconAlertTriangle size={20} />
            Anonimizar Conta - Ação Irreversível
          </DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 2 }}>
              <Alert severity="error">
                Esta ação não pode ser desfeita. Todos os seus dados pessoais identificáveis serão removidos do sistema.
              </Alert>
              <Typography variant="body2">
                Para confirmar, digite exatamente: <strong>&quot;anonimizar minha conta&quot;</strong>
              </Typography>
              <TextField
                fullWidth
                label="Confirmação"
                placeholder="anonimizar minha conta"
                value={deleteConfirmation}
                onChange={(e) => setDeleteConfirmation(e.target.value)}
                variant="outlined"
                size="small"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => { setDeleteDialogOpen(false); setDeleteConfirmation(''); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleAnonymizeAccount}
              color="error"
              variant="contained"
              disabled={loading || deleteConfirmation !== 'anonimizar minha conta'}
            >
              {loading ? <CircularProgress size={20} /> : 'Anonimizar'}
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    </DashboardCard>
  );
}
