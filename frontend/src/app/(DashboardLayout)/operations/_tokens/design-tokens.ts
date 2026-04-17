import type { Theme } from '@mui/material/styles';
import { alpha } from '@mui/material/styles';

// ── Table tokens ─────────────────────────────────────────────────────────────
/** Header cell: bold */
export const thSx = { fontWeight: 700 } as const;
/** Compact body cell: reduced vertical padding */
export const tdCompactSx = { py: 0.75 } as const;

// ── Card / KPI tokens ────────────────────────────────────────────────────────
export const kpiCardSx = {
  p: 2,
  borderRadius: 2,
  textAlign: 'center' as const,
  borderLeft: '4px solid',
} as const;

// ── Dialog tokens ────────────────────────────────────────────────────────────
export const dialogTitleSx = { fontWeight: 700 } as const;

// ── Gantt palette (theme-aware) ──────────────────────────────────────────────
/** 10-color palette for line-based visualizations (Gantt, charts) */
export function getLinePalette(theme: Theme): string[] {
  const isDark = theme.palette.mode === 'dark';
  return [
    isDark ? '#60a5fa' : '#2563eb', // Blue
    isDark ? '#34d399' : '#059669', // Emerald
    isDark ? '#fbbf24' : '#d97706', // Amber
    isDark ? '#f472b6' : '#db2777', // Rose
    isDark ? '#a78bfa' : '#7c3aed', // Violet
    isDark ? '#2dd4bf' : '#0d9488', // Teal
    isDark ? '#fb7185' : '#e11d48', // Rose-Red
    isDark ? '#818cf8' : '#4f46e5', // Indigo
    isDark ? '#fb923c' : '#ea580c', // Orange
    isDark ? '#94a3b8' : '#475569', // Slate
  ];
}

/** Gantt trip direction / deadhead colors */
export function getGanttColors(theme: Theme) {
  const isDark = theme.palette.mode === 'dark';
  return {
    ida: isDark ? '#60a5fa' : '#3b82f6',
    volta: isDark ? '#818cf8' : '#6366f1',
    // Cycles use a cohesive gradient or solid color
    cycle: isDark ? '#34d399' : '#10b981',
    // Unproductive/Idle colors use semantic categories and matching borders
    deadhead: alpha(theme.palette.warning.main, isDark ? 0.18 : 0.12),
    deadheadBorder: alpha(theme.palette.warning.main, 0.45),
    interval: alpha(theme.palette.info.main, isDark ? 0.18 : 0.1),
    intervalBorder: alpha(theme.palette.info.main, 0.35),
    mealBreak: alpha(theme.palette.success.main, isDark ? 0.2 : 0.12),
    mealBreakBorder: alpha(theme.palette.success.main, 0.4),
    idle: alpha(theme.palette.warning.light, isDark ? 0.18 : 0.14),
    idleBorder: alpha(theme.palette.warning.dark, isDark ? 0.35 : 0.3),
    waiting: alpha(theme.palette.info.main, isDark ? 0.18 : 0.1),
    // Backgrounds for the Gantt area
    trackBg: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.02)',
    gridLine: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)',
  } as const;
}
