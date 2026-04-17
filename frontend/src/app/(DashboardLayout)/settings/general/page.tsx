'use client';

import React from 'react';
import { Box, Alert } from '@mui/material';
import { IconSettings } from '@tabler/icons-react';
import DashboardCard from '@/app/components/shared/DashboardCard';

export default function GeneralSettingsPage() {
  return (
    <Box sx={{ p: 3 }}>
      <DashboardCard
        title="Configurações Gerais"
        subtitle="Preferências globais do sistema"
        action={<IconSettings size={20} />}
      >
        <Alert severity="info" sx={{ mt: 1 }}>
          Esta seção está em desenvolvimento. Em breve você poderá configurar fuso horário, idioma, notificações e integrações.
        </Alert>
      </DashboardCard>
    </Box>
  );
}
