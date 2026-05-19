'use client';
import { Box, Avatar, Typography, IconButton, Tooltip, useMediaQuery, Dialog, DialogTitle, DialogContent, DialogActions, Button } from '@mui/material';
import { IconPower } from '@tabler/icons-react';
import { CustomizerContext } from "@/app/context/customizerContext";
import { useContext, useState } from 'react';
import { getSessionUser, clearSession, apiClient } from '@/lib/api';
import { useRouter } from 'next/navigation';

const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Admin',
  company_admin: 'Admin da Empresa',
  analyst: 'Analista',
  operator: 'Operador',
};

export const Profile = () => {
  const lgUp = useMediaQuery((theme: any) => theme.breakpoints.up('lg'));
  const { isSidebarHover, isCollapse } = useContext(CustomizerContext);
  const hideMenu = lgUp ? isCollapse === 'mini-sidebar' && !isSidebarHover : false;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const router = useRouter();
  const user = getSessionUser();

  const handleLogout = async () => {
    try { await apiClient.post('/auth/logout'); } catch { /* ignora erro de rede */ }
    clearSession();
    setConfirmOpen(false);
    router.push('/auth/login');
  };

  const displayName = user?.name || user?.email?.split('@')[0] || 'Usuário';
  const displayRole = ROLE_LABELS[user?.role ?? ''] || user?.role || '';

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, m: 3, p: 2, bgcolor: 'secondary.light' }}>
        {!hideMenu ? (
          <>
            <Avatar alt={displayName} src="/images/profile/user-1.jpg" sx={{ height: 40, width: 40 }} />
            <Box>
              <Typography variant="h6" noWrap sx={{ maxWidth: 110 }}>{displayName}</Typography>
              <Typography variant="caption">{displayRole}</Typography>
            </Box>
            <Box sx={{ ml: 'auto' }}>
              <Tooltip title="Sair do sistema" placement="top">
                <IconButton color="primary" aria-label="logout" size="small" onClick={() => setConfirmOpen(true)}>
                  <IconPower size="20" />
                </IconButton>
              </Tooltip>
            </Box>
          </>
        ) : ''}
      </Box>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Sair do sistema</DialogTitle>
        <DialogContent>
          <Typography>Deseja realmente encerrar sua sessão?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>Cancelar</Button>
          <Button variant="contained" color="error" onClick={handleLogout}>Sair</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
