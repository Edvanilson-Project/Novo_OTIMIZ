import React, { useState } from 'react';
import Link from 'next/link';
import {
  Box,
  Menu,
  Avatar,
  Typography,
  Divider,
  Button,
  IconButton,
} from '@mui/material';
import * as dropdownData from './data';

import { IconMail } from '@tabler/icons-react';
import { Stack } from '@mui/material';
import { useRouter } from 'next/navigation';
import { apiClient, clearSession } from '@/lib/api';
import { useAuth } from '@/app/hooks/useAuth';


const Profile = () => {
  const router = useRouter();
  const { user } = useAuth();
  const [anchorEl2, setAnchorEl2] = useState<HTMLElement | null>(null);
  const handleClick2 = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl2(event.currentTarget);
  };
  const handleClose2 = () => {
    setAnchorEl2(null);
  };

  const handleLogout = async () => {
    try {
      await apiClient.post('/auth/logout');
    } catch (err) {
      console.error('Erro ao fazer logout:', err);
    } finally {
      clearSession();
      router.push('/auth/login');
    }
  };

  return (
    <Box>
      <IconButton
        aria-label="Abrir menu do perfil"
        color="inherit"
        aria-controls="msgs-menu"
        aria-haspopup="true"
        sx={{
          ...(typeof anchorEl2 === 'object' && {
            color: 'primary.main',
          }),
        }}
        onClick={handleClick2}
      >
        <Avatar
          src={"/images/profile/user-1.jpg"}
          alt={'ProfileImg'}
          sx={{
            width: 35,
            height: 35,
          }}
        />
      </IconButton>
      {/* ------------------------------------------- */}
      {/* Message Dropdown */}
      {/* ------------------------------------------- */}
      <Menu
        id="msgs-menu"
        anchorEl={anchorEl2}
        keepMounted
        open={Boolean(anchorEl2)}
        onClose={handleClose2}
        anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        transformOrigin={{ horizontal: 'right', vertical: 'top' }}
        sx={{
          '& .MuiMenu-paper': {
            width: '360px',
            p: 4,
          },
        }}
      >
        <Typography variant="h5">Minha Conta</Typography>
        <Stack direction="row" spacing={2} sx={{ py: 3, alignItems: "center" }}>
          <Avatar src={"/images/profile/user-1.jpg"} alt={"ProfileImg"} sx={{ width: 95, height: 95 }} />
          <Box>
            <Typography variant="subtitle2" sx={{ color: "textPrimary", fontWeight: 600 }}>
              {user?.name ?? '—'}
            </Typography>
            <Typography variant="subtitle2" sx={{ color: "textSecondary" }}>
              {user?.role ?? '—'}
            </Typography>
            <Typography
              variant="subtitle2"
              sx={{ display: "flex", alignItems: "center", gap: 1, color: "textSecondary" }}
            >
              <IconMail width={15} height={15} />
              {user?.email ?? '—'}
            </Typography>
          </Box>
        </Stack>
        <Divider />
        {dropdownData.profile.map((profile) => (
          <Box key={profile.title}>
            <Box sx={{ py: 2, px: 0 }} className="hover-text-primary">
              <Link href={profile.href}>
                <Stack direction="row" spacing={2}>
                  <Box
                    sx={{
                      width: "45px",
                      height: "45px",
                      bgcolor: "primary.light",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0
                    }}
                  >
                    <Avatar
                      src={profile.icon}
                      alt={profile.icon}
                      sx={{
                        width: 24,
                        height: 24,
                        borderRadius: 0,
                      }}
                    />
                  </Box>
                  <Box>
                    <Typography
                      variant="subtitle2"
                      className="text-hover"
                      noWrap
                      sx={{
                        width: '240px',
                        fontWeight: 600,
                        color: "textPrimary"
                      }}
                    >
                      {profile.title}
                    </Typography>
                    <Typography
                      variant="subtitle2"
                      noWrap
                      sx={{
                        color: "textSecondary",
                        width: '240px',
                      }}
                    >
                      {profile.subtitle}
                    </Typography>
                  </Box>
                </Stack>
              </Link>
            </Box>
          </Box>
        ))}
        <Box sx={{ mt: 2 }}>
          <Button onClick={handleLogout} variant="outlined" color="primary" fullWidth>
            Sair
          </Button>
        </Box>
      </Menu>
    </Box>
  );
};

export default Profile;
