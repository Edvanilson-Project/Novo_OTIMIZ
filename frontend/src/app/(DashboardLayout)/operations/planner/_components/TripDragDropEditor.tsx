'use client';

import React, { useState, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Chip,
  Stack,
  Typography,
  Alert,
  CircularProgress,
  Snackbar,
} from '@mui/material';
import {
  IconGripVertical,
  IconArrowRight,
  IconCheck,
  IconX,
} from '@tabler/icons-react';

export interface Trip {
  id: number;
  tripId: string;
  lineId: number;
  startTime: number;
  endTime: number;
  originId: number;
  destinationId: number;
}

export interface Block {
  id: number;
  blockId: number;
  trips: Trip[];
  vehicleTypeId?: number;
  cost?: number;
}

interface TripDragDropEditorProps {
  blocks: Block[];
  onBlocksUpdate: (updatedBlocks: Block[]) => Promise<void>;
}

interface DragState {
  sourceBlockId: number;
  tripId: number;
  tripData: Trip;
}

const TripDragDropEditor: React.FC<TripDragDropEditorProps> = ({ blocks, onBlocksUpdate }) => {
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [openMoveDialog, setOpenMoveDialog] = useState(false);
  const [targetBlockId, setTargetBlockId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' });

  // Handle drag start
  const handleTripDragStart = useCallback((blockId: number, trip: Trip) => {
    setDragState({
      sourceBlockId: blockId,
      tripId: trip.id,
      tripData: trip,
    });
  }, []);

  // Handle drag over (allow drop)
  const handleBlockDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  // Handle drop
  const handleBlockDrop = useCallback((targetId: number) => {
    if (!dragState) return;
    if (dragState.sourceBlockId === targetId) {
      setDragState(null);
      return;
    }

    setTargetBlockId(targetId);
    setOpenMoveDialog(true);
  }, [dragState]);

  // Confirm move
  const confirmMove = useCallback(async () => {
    if (!dragState || targetBlockId === null) return;

    try {
      setLoading(true);

      // Create updated blocks
      const updatedBlocks = blocks.map(block => {
        const isSourceBlock = block.id === dragState.sourceBlockId;
        const isTargetBlock = block.id === targetBlockId;

        if (isSourceBlock) {
          return {
            ...block,
            trips: block.trips.filter(trip => trip.id !== dragState.tripId),
          };
        }

        if (isTargetBlock) {
          return {
            ...block,
            trips: [...block.trips, dragState.tripData],
          };
        }

        return block;
      });

      // Call API to update
      await onBlocksUpdate(updatedBlocks);

      setSnackbar({
        open: true,
        message: `Viagem ${dragState.tripData.tripId} movida com sucesso`,
        severity: 'success',
      });

      setOpenMoveDialog(false);
      setDragState(null);
      setTargetBlockId(null);
    } catch (error) {
      setSnackbar({
        open: true,
        message: `Erro ao mover viagem: ${error instanceof Error ? error.message : 'Desconhecido'}`,
        severity: 'error',
      });
    } finally {
      setLoading(false);
    }
  }, [dragState, targetBlockId, blocks, onBlocksUpdate]);

  // Cancel move
  const cancelMove = useCallback(() => {
    setOpenMoveDialog(false);
    setDragState(null);
    setTargetBlockId(null);
  }, []);

  const formatTime = (minutes: number): string => {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
  };

  const getBlockLabel = (blockId: number): string => {
    const block = blocks.find(b => b.id === blockId);
    return block ? `Bloco ${block.blockId}` : `Bloco ${blockId}`;
  };

  return (
    <>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 2 }}>
        {blocks.map(block => (
          <Card
            key={block.id}
            onDragOver={handleBlockDragOver}
            onDrop={() => handleBlockDrop(block.id)}
            sx={{
              cursor: 'drop-target',
              backgroundColor: dragState?.sourceBlockId === block.id ? '#f5f5f5' : undefined,
              border: targetBlockId === block.id ? '2px dashed #1976d2' : '1px solid #ddd',
              transition: 'all 0.2s ease',
              '&:hover': {
                boxShadow: 2,
              },
            }}
          >
            <CardHeader
              title={`Bloco ${block.blockId}`}
              subheader={`${block.trips.length} viagens • Custo: R$ ${(block.cost || 0).toFixed(2)}`}
            />
            <CardContent>
              <List disablePadding>
                {block.trips.map(trip => (
                  <ListItem
                    key={trip.id}
                    draggable
                    onDragStart={() => handleTripDragStart(block.id, trip)}
                    sx={{
                      backgroundColor: dragState?.tripId === trip.id ? '#fff3cd' : undefined,
                      cursor: 'grab',
                      '&:active': { cursor: 'grabbing' },
                      borderRadius: 1,
                      mb: 1,
                      padding: 1.5,
                      border: '1px solid #eee',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        backgroundColor: '#f9f9f9',
                        boxShadow: 1,
                      },
                    }}
                  >
                    <IconGripVertical size={16} style={{ marginRight: 8 }} />
                    <ListItemText
                      primary={
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                          {trip.tripId}
                        </Typography>
                      }
                      secondary={
                        <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                          <Chip
                            label={`${formatTime(trip.startTime)} - ${formatTime(trip.endTime)}`}
                            size="small"
                            variant="outlined"
                          />
                        </Stack>
                      }
                    />
                  </ListItem>
                ))}

                {block.trips.length === 0 && (
                  <Typography variant="body2" color="textSecondary" sx={{ py: 2, textAlign: 'center' }}>
                    Nenhuma viagem
                  </Typography>
                )}
              </List>
            </CardContent>
          </Card>
        ))}
      </Box>

      {/* Move Dialog */}
      <Dialog open={openMoveDialog} onClose={cancelMove}>
        <DialogTitle>Confirmar Movimento de Viagem</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {dragState && (
            <Stack spacing={2}>
              <Alert severity="info">
                Você está movendo a viagem <strong>{dragState.tripData.tripId}</strong>
              </Alert>

              <Box>
                <Typography variant="caption" color="textSecondary">
                  DE
                </Typography>
                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                  {getBlockLabel(dragState.sourceBlockId)}
                </Typography>
              </Box>

              <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <IconArrowRight size={24} />
              </Box>

              <Box>
                <Typography variant="caption" color="textSecondary">
                  PARA
                </Typography>
                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                  {targetBlockId ? getBlockLabel(targetBlockId) : '—'}
                </Typography>
              </Box>

              <Alert severity="warning">
                Esta ação pode alterar o custo total da operação. Revise antes de confirmar.
              </Alert>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelMove} disabled={loading}>
            Cancelar
          </Button>
          <Button
            onClick={confirmMove}
            variant="contained"
            color="primary"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : <IconCheck size={20} />}
          >
            {loading ? 'Movendo...' : 'Confirmar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for feedback */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        message={snackbar.message}
      />
    </>
  );
};

export default TripDragDropEditor;
