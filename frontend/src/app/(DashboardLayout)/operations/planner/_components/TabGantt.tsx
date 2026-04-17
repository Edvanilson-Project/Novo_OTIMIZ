'use client';
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  Box, Typography, Stack, Paper, Tooltip, Button, Drawer, Divider,
  IconButton, Alert, Snackbar,
  alpha, useTheme, type Theme,
} from '@mui/material';
import { List, type RowComponentProps } from 'react-window';
import { IconInfoCircle } from '@tabler/icons-react';
import type {
  Line, Terminal, OptimizationResultSummary, TripDetail,
} from '../../_types';
import {
  minToHHMM, minToDuration, fmtCurrency, fmtSignedCurrency,
  getTerminalDisplayName, getTripPublicId,
  type TripIntervalPolicy,
} from '../_helpers/formatters';
import { getLinePalette, getGanttColors } from '../../_tokens/design-tokens';
import { OperationalConflictIndicator } from './OperationalConflictIndicator';
import { operationsApi } from '@/lib/api';

// ─── Constants ───────────────────────────────────────────────────────────────
const MIN_SCALE = 1;
const MAX_SCALE = 8;
const BASE_PIXELS_PER_MINUTE = 2;
const ROW_HEIGHT = 68;
const HEADER_HEIGHT = 44;
const TIME_INDICATOR_WIDTH = 2;
const OVERNIGHT_START_MIN = 1440;
const HORIZON_MINUTES = 1800;
const SIDEBAR_WIDTH = 140;

// ─── Interfaces ──────────────────────────────────────────────────────────────
export interface TabGanttProps {
  res: OptimizationResultSummary;
  lines: Line[];
  terminals: Terminal[];
  intervalPolicy: TripIntervalPolicy;
  onWhatIfUpdate?: (newCost: number | null) => void;
}

interface TripMetadata {
  lineId: number;
  color: string;
}

// ─── Components ──────────────────────────────────────────────────────────────

const GanttTimeHeader = React.memo(({ scale, theme }: { scale: number; theme: Theme }) => {
  const ppm = scale * BASE_PIXELS_PER_MINUTE;
  const marks: React.ReactNode[] = [];

  for (let min = 0; min <= HORIZON_MINUTES; min += 60) {
    const left = SIDEBAR_WIDTH + min * ppm;
    const isOvernight = min >= OVERNIGHT_START_MIN;
    marks.push(
      <Box key={min} sx={{ position: 'absolute', left, top: 0, height: '100%' }}>
        <Box sx={{ width: '1px', height: '100%', bgcolor: isOvernight ? 'warning.light' : 'divider', opacity: 0.6 }} />
        <Typography variant="caption" sx={{
          position: 'absolute', top: 6, left: 4,
          fontSize: '0.6rem',
          color: isOvernight ? 'warning.dark' : 'text.secondary',
          fontWeight: isOvernight ? 700 : 400,
          whiteSpace: 'nowrap',
        }}>
          {minToHHMM(min)}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ position: 'relative', height: HEADER_HEIGHT, borderBottom: `1px solid ${theme.palette.divider}`, bgcolor: 'background.default', overflow: 'hidden' }}>
      {/* Fundo overnight */}
      <Box sx={{
        position: 'absolute',
        left: SIDEBAR_WIDTH + OVERNIGHT_START_MIN * ppm,
        top: 0, bottom: 0, right: 0,
        bgcolor: alpha(theme.palette.warning.main, 0.07),
        pointerEvents: 'none',
      }} />
      {/* Placeholder da sidebar */}
      <Box sx={{
        position: 'absolute', left: 0, top: 0, bottom: 0,
        width: SIDEBAR_WIDTH,
        bgcolor: 'background.paper',
        borderRight: `1px solid ${theme.palette.divider}`,
        zIndex: 1,
      }} />
      {marks}
    </Box>
  );
});

GanttTimeHeader.displayName = 'GanttTimeHeader';

/**
 * Representação visual de um bloco de tempo (Viagem ou Apoio)
 */
const GanttRowItem = React.memo(({ 
  item, 
  scale, 
  onDragStart, 
  colors 
}: { 
  item: any; 
  scale: number; 
  onDragStart: (e: React.DragEvent, item: any) => void;
  colors: any;
}) => {
  const left = item.start_time * scale * BASE_PIXELS_PER_MINUTE;
  const width = (item.end_time - item.start_time) * scale * BASE_PIXELS_PER_MINUTE;

  const isApoio = item.kind === 'apoio' || !item.lineId;
  
  return (
    <Tooltip
      arrow
      title={
        <Box sx={{ p: 0.5 }}>
          <Typography variant="caption" sx={{ display: 'block', fontWeight: 700 }}>
            {isApoio ? 'Apoio / Ociosa' : `Viagem ${item.tripId} - Linha ${item.lineCode || item.lineId}`}
          </Typography>
          <Typography variant="caption" sx={{ display: 'block' }}>
            {minToHHMM(item.start_time)} → {minToHHMM(item.end_time)} ({minToDuration(item.end_time - item.start_time)})
          </Typography>
          {!isApoio && (
            <Typography variant="caption" sx={{ display: 'block', mt: 0.5, opacity: 0.8 }}>
               Clique e arraste para reatribuir veículo
            </Typography>
          )}
        </Box>
      }
    >
      <Box
        draggable={!isApoio}
        onDragStart={(e) => !isApoio && onDragStart(e, item)}
        sx={{
          position: 'absolute',
          left,
          width: Math.max(width, 4),
          height: 34,
          top: 17,
          borderRadius: 1,
          backgroundColor: isApoio ? colors.deadhead : item.color,
          border: '1px solid',
          borderColor: isApoio ? colors.deadheadBorder : alpha(item.color, 0.5),
          cursor: isApoio ? 'default' : 'grab',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          transition: 'transform 0.1s, box-shadow 0.1s',
          '&:hover': {
            transform: isApoio ? 'none' : 'scaleY(1.05)',
            boxShadow: isApoio ? 'none' : 3,
            zIndex: 10,
          },
          '&:active': { cursor: 'grabbing' },
          // Estilo hachurado para Deadhead/Apoio
          ...(isApoio && {
            backgroundImage: `linear-gradient(45deg, ${colors.deadheadBorder} 12.5%, transparent 12.5%, transparent 50%, ${colors.deadheadBorder} 50%, ${colors.deadheadBorder} 62.5%, transparent 62.5%, transparent 100%)`,
            backgroundSize: '8px 8px',
          })
        }}
      >
        {!isApoio && width > 40 && (
          <Typography 
            variant="caption" 
            sx={{ 
              color: 'white', 
              fontWeight: 800, 
              fontSize: '0.65rem',
              textShadow: '0px 1px 2px rgba(0,0,0,0.5)',
              userSelect: 'none'
            }}
          >
            {item.lineCode || item.lineId}
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
});

GanttRowItem.displayName = 'GanttRowItem';

/**
 * Main Content Component
 */
export function TabGantt({ res, lines, terminals, intervalPolicy, onWhatIfUpdate }: TabGanttProps) {
  const theme = useTheme();
  const colors = getGanttColors(theme);
  const linePalette = getLinePalette(theme);

  // ─── State ───
  const [scale, setScale] = useState(2.5);
  const [localBlocks, setLocalBlocks] = useState<any[]>([]);
  const [backupBlocks, setBackupBlocks] = useState<any[]>([]); // Estado canônico original
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState<{msg: string, sev: 'success' | 'error' | 'info'} | null>(null);

  /**
   * CORREÇÃO #1: Persistência de Cores com useRef
   * Mantemos o mapa id_viagem -> line_id em um Ref para que não se perca
   * quando a API devolver trips simplificadas (sem line_id).
   */
  const tripMetadataRef = useRef<Map<number, TripMetadata>>(new Map());

  // ─── Mapas de Referência ───
  const lineMap = useMemo(() => new Map(lines.map(l => [l.id, l])), [lines]);
  const terminalsMap = useMemo(() => {
    const map: Record<string, string> = {};
    terminals.forEach(t => { map[t.id.toString()] = t.shortName || t.name; });
    return map;
  }, [terminals]);

  /**
   * Hidratação Inicial: Transforma result.blocks em dados planos para renderização
   */
  useEffect(() => {
    if (!res.blocks) return;

    // 1. Primeiro passo: popular o mapa de metadados fixo se a viagem tiver lineId
    res.blocks.forEach(block => {
      block.trips?.forEach((trip: any) => {
        const tripId = getTripPublicId(trip);
        const lId = trip.line_id || trip.lineId;
        
        if (tripId && lId && !tripMetadataRef.current.has(tripId)) {
          const line = lineMap.get(lId);
          tripMetadataRef.current.set(tripId, {
            lineId: lId,
            color: line?.colorHex || linePalette[lId % linePalette.length]
          });
        }
      });
    });

    // 2. Segundo passo: Montar os blocos visuais usando o mapa de metadados
    const hydrated = res.blocks.map(block => ({
      ...block,
      items: (block.trips || []).map((trip: any) => {
        const tripId = getTripPublicId(trip);
        const meta = tripId ? tripMetadataRef.current.get(tripId) : null;
        const line = meta ? lineMap.get(meta.lineId) : null;

        return {
          ...trip,
          tripId,
          lineId: meta?.lineId,
          lineCode: line?.code,
          color: meta?.color,
          kind: 'trip'
        };
      })
    })).sort((a,b) => a.block_id - b.block_id);

    setLocalBlocks(hydrated);
    setBackupBlocks(JSON.parse(JSON.stringify(hydrated))); // Clone profundo para backup
  }, [res, lineMap, linePalette]);

  // ─── Event Handlers ───

  const handleDragStart = (e: React.DragEvent, item: any) => {
    e.dataTransfer.setData('trip_id', item.tripId.toString());
    e.dataTransfer.setData('origin_block_id', item.block_id?.toString() || '');
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  /**
   * CORREÇÃO #2, #3 e #4: Lógica de Drop (What-If)
   */
  const handleWhatIfDrop = async (e: React.DragEvent, targetBlockId: number) => {
    e.preventDefault();
    const tripId = parseInt(e.dataTransfer.getData('trip_id'));
    const originBlockId = parseInt(e.dataTransfer.getData('origin_block_id'));

    if (isNaN(tripId) || originBlockId === targetBlockId) return;

    // Otimismo na UI: Move localmente para feedback instantâneo
    const newLocalBlocks = localBlocks.map(block => {
      if (block.id === originBlockId || block.block_id === originBlockId) {
        return { ...block, items: block.items.filter((t: any) => t.tripId !== tripId) };
      }
      if (block.id === targetBlockId || block.block_id === targetBlockId) {
        const movingTrip = localBlocks.find(b => b.block_id === originBlockId)?.items.find((t: any) => t.tripId === tripId);
        return { ...block, items: [...block.items, { ...movingTrip, block_id: targetBlockId }].sort((a,b) => a.start_time - b.start_time) };
      }
      return block;
    });

    setLocalBlocks(newLocalBlocks);
    setLoading(true);

    try {
      /**
       * CORREÇÃO #3: SEMPRE enviar o backupBlocks (estado canônico) para a API.
       * Isso garante que dId = baseline - current seja calculado corretamente no Python.
       */
      const payload = {
        blocks: backupBlocks.map(b => ({
          block_id: b.block_id,
          trips: b.items.map((t: any) => ({
            id: t.tripId,
            start_time: t.start_time,
            end_time: t.end_time
          }))
        })),
        move: { trip_id: tripId, to_block_id: targetBlockId }
      };

      const result = await operationsApi.evaluateDelta(payload);

      if (result.isValid) {
        setNotification({ msg: `Movimento válido! Economia: ${fmtSignedCurrency(result.deltaCost)}`, sev: 'success' });
        
        /**
         * CORREÇÃO #4: Sincronização de horários devolvidos pela API.
         * Quando a API move, ela pode reajustar horários de outras viagens.
         * Devemos usar o result.blocks retornado pela API para atualizar a UI.
         */
        const apiBlocks = result.blocks.map((b: any) => ({
          ...b,
          id: b.block_id,
          items: b.trips.map((t: any) => {
            const meta = tripMetadataRef.current.get(t.id);
            const line = meta ? lineMap.get(meta.lineId) : null;
            return {
              ...t,
              tripId: t.id,
              lineId: meta?.lineId,
              lineCode: line?.code,
              color: meta?.color,
              kind: 'trip'
            };
          })
        }));

        setLocalBlocks(apiBlocks);
        setBackupBlocks(JSON.parse(JSON.stringify(apiBlocks)));
        if (onWhatIfUpdate) onWhatIfUpdate(result.totalCost);
      } else {
        setNotification({ msg: `Regra violada: ${result.violations?.join(', ')}`, sev: 'error' });
        setLocalBlocks(backupBlocks); // Rollback em caso de erro fatal
      }
    } catch (err) {
      setNotification({ msg: 'Erro ao avaliar movimento. Tente novamente.', sev: 'error' });
      setLocalBlocks(backupBlocks); // Rollback
    } finally {
      setLoading(false);
    }
  };

  // ─── Render Row ───
  const Row = useCallback(({ index, style }: RowComponentProps) => {
    const block = localBlocks[index];
    if (!block) return <Box style={style as React.CSSProperties} />;

    return (
      <Box 
        style={style} 
        onDragOver={handleDragOver}
        onDrop={(e) => handleWhatIfDrop(e, block.block_id)}
        sx={{ 
          borderBottom: `1px solid ${theme.palette.divider}`,
          display: 'flex',
          '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.02) }
        }}
      >
        {/* Header do Bloco (Fixo à esquerda) */}
        <Box sx={{ 
          width: 140, 
          minWidth: 140, 
          borderRight: `1px solid ${theme.palette.divider}`,
          p: 1.5,
          bgcolor: 'background.paper',
          zIndex: 2,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center'
        }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800, color: 'primary.main' }}>
            Veículo {block.block_id}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {block.items.filter((t: any) => t.kind === 'trip').length} viagens
          </Typography>
        </Box>

        {/* Linha do Tempo (Escálavel) */}
        <Box sx={{ flexGrow: 1, position: 'relative', overflow: 'hidden', bgcolor: colors.trackBg }}>
          {/* Fundo da área overnight (após meia-noite) */}
          <Box sx={{
            position: 'absolute',
            left: OVERNIGHT_START_MIN * scale * BASE_PIXELS_PER_MINUTE,
            top: 0, bottom: 0, right: 0,
            bgcolor: alpha(theme.palette.warning.main, 0.05),
            pointerEvents: 'none',
            zIndex: 0,
          }} />
          {/* Linha divisória da meia-noite (tracejada) */}
          <Box sx={{
            position: 'absolute',
            left: OVERNIGHT_START_MIN * scale * BASE_PIXELS_PER_MINUTE,
            top: 0, bottom: 0,
            width: 0,
            borderLeft: `2px dashed`,
            borderColor: 'divider',
            opacity: 0.9,
            pointerEvents: 'none',
            zIndex: 5,
          }} />
          {block.items.map((item: any, i: number) => (
            <GanttRowItem
              key={`${item.tripId}-${i}`}
              item={item}
              scale={scale}
              onDragStart={handleDragStart}
              colors={colors}
            />
          ))}
        </Box>
      </Box>
    );
  }, [localBlocks, scale, theme, colors]);

  // ─── View ───
  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: 'hidden', position: 'relative' }}>
      
      {/* Barra de Ferramentas do Gantt */}
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'center', p: 2, bgcolor: 'background.default', borderBottom: `1px solid ${theme.palette.divider}` }}
      >
        <Typography variant="h6" sx={{ fontWeight: 700 }}>Planejador Interativo</Typography>
        
        <Divider orientation="vertical" flexItem />
        
        <OperationalConflictIndicator res={{ ...res, blocks: localBlocks }} />

        <Box sx={{ flexGrow: 1 }} />

        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>Zoom</Typography>
          <Button size="small" variant="outlined" onClick={() => setScale(s => Math.max(MIN_SCALE, s - 0.5))}>-</Button>
          <Typography variant="caption" sx={{ minWidth: 40, textAlign: 'center' }}>{scale.toFixed(1)}x</Typography>
          <Button size="small" variant="outlined" onClick={() => setScale(s => Math.min(MAX_SCALE, s + 0.5))}>+</Button>
        </Stack>

        <Button 
          variant="contained" 
          color="primary" 
          size="small" 
          disabled={JSON.stringify(localBlocks) === JSON.stringify(backupBlocks)}
          onClick={() => {
            // Aqui você dispararia o salvamento definitivo no banco
            setNotification({ msg: 'Alterações enviadas para persistência!', sev: 'info' });
            setBackupBlocks(localBlocks);
          }}
        >
          Salvar Alterações
        </Button>
      </Stack>

      {/* Eixo de Tempo */}
      <GanttTimeHeader scale={scale} theme={theme} />

      {/* Grid Virtualizada */}
      <Box sx={{ height: 600, width: '100%', position: 'relative', overflowX: 'auto' }}>
        {loading && (
          <Box sx={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            bgcolor: 'rgba(255,255,255,0.7)', zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Typography variant="button" sx={{ fontWeight: 800, color: 'primary.main' }}>Recalculando...</Typography>
          </Box>
        )}

        <List
          defaultHeight={600}
          rowCount={localBlocks.length}
          rowHeight={ROW_HEIGHT}
          rowComponent={Row}
          rowProps={{}}
          style={{ height: 600, width: '100%' }}
        />
      </Box>

      {/* Notificações */}
      <Snackbar 
        open={Boolean(notification)} 
        autoHideDuration={4000} 
        onClose={() => setNotification(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {notification ? (
          <Alert severity={notification.sev} variant="filled" sx={{ fontWeight: 700 }}>
            {notification.msg}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Paper>
  );
}
