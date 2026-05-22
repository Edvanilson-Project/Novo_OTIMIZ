'use client';

import React, { useState, useMemo } from 'react';
import {
  Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack,
  TextField, Typography, CircularProgress, Alert, Autocomplete,
} from '@mui/material';
import { IconPlane } from '@tabler/icons-react';
import { operationsApi } from '@/lib/api';

interface TripReassignmentModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  scheduleId: number;
  tripId: number;
  tripCode?: string;
  availableBlocks?: Array<{ id: number; label: string }>;
  onBlocksNeeded?: () => Promise<Array<{ id: number; label: string }>>;
}

export function TripReassignmentModal({
  open,
  onClose,
  onSuccess,
  scheduleId,
  tripId,
  tripCode,
  availableBlocks = [],
  onBlocksNeeded,
}: TripReassignmentModalProps) {
  const [selectedBlockId, setSelectedBlockId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocks, setBlocks] = useState(availableBlocks);

  const blockOptions = useMemo(
    () => blocks.map((b) => ({ label: b.label, id: b.id })),
    [blocks],
  );

  const handleLoadBlocks = async () => {
    if (onBlocksNeeded && blocks.length === 0) {
      try {
        const loaded = await onBlocksNeeded();
        setBlocks(loaded);
      } catch {
        setError('Erro ao carregar blocos disponíveis.');
      }
    }
  };

  const handleReassign = async () => {
    if (!selectedBlockId) {
      setError('Selecione um bloco de destino.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await operationsApi.reassignTrip({
        scheduleId,
        tripId,
        targetBlockId: selectedBlockId,
      });
      setError(null);
      onSuccess?.();
      onClose();
    } catch {
      setError('Erro ao reatribuir viagem. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    handleLoadBlocks();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <IconPlane size={20} />
        Reatribuir Viagem
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {tripCode && (
            <Typography variant="body2" color="textSecondary">
              <strong>Viagem:</strong> {tripCode}
            </Typography>
          )}
          {error && (
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
          <Autocomplete
            options={blockOptions}
            getOptionLabel={(option) => option.label}
            isOptionEqualToValue={(option, value) => option.id === value.id}
            value={
              selectedBlockId
                ? blockOptions.find((b) => b.id === selectedBlockId) || null
                : null
            }
            onChange={(_, newValue) => {
              setSelectedBlockId(newValue?.id ?? null);
            }}
            onOpen={handleOpen}
            loading={loading && blocks.length === 0}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Bloco de Destino"
                placeholder="Procure ou selecione"
                InputProps={{
                  ...params.InputProps,
                  endAdornment: (
                    <>
                      {loading && blocks.length === 0 ? <CircularProgress color="inherit" size={20} /> : null}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                }}
              />
            )}
          />
          <Typography variant="caption" color="textSecondary">
            Selecione o bloco onde deseja reatribuir esta viagem.
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button
          onClick={handleReassign}
          variant="contained"
          disabled={!selectedBlockId || loading}
        >
          {loading ? <CircularProgress size={20} /> : 'Reatribuir'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
