'use client';
import { useState } from 'react';
import { DataGrid, type DataGridProps, type GridRowModel } from '@mui/x-data-grid';
import { ptBR } from '@mui/x-data-grid/locales';
import { useTheme } from '@mui/material/styles';
import Box from '@mui/material/Box';
import InputAdornment from '@mui/material/InputAdornment';
import TextField from '@mui/material/TextField';
import { IconSearch } from '@tabler/icons-react';

type AppDataGridProps = DataGridProps & { searchable?: boolean };

export default function AppDataGrid({ searchable, ...props }: AppDataGridProps) {
  const theme = useTheme();
  const { localeText: callerLocaleText, sx: callerSx, rows, ...rest } = props;
  const [search, setSearch] = useState('');

  const filteredRows = searchable && search.trim()
    ? (rows as GridRowModel[]).filter((row) =>
        Object.values(row).some((v) =>
          String(v ?? '').toLowerCase().includes(search.toLowerCase())
        )
      )
    : rows;

  return (
    <Box>
      {searchable && (
        <TextField
          size="small"
          placeholder="Buscar..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mb: 1.5, width: 280 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <IconSearch size={16} color={theme.palette.text.secondary} />
                </InputAdornment>
              ),
            },
          }}
        />
      )}
      <DataGrid
      localeText={{
        ...ptBR.components.MuiDataGrid.defaultProps.localeText,
        ...callerLocaleText,
      }}
      sx={{
        border: 'none',
        '& .MuiDataGrid-columnHeader': {
          backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
          fontWeight: 700,
          fontSize: '0.75rem',
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          color: theme.palette.text.secondary,
        },
        '& .MuiDataGrid-row:hover': {
          backgroundColor: theme.palette.mode === 'dark' ? 'rgba(97,93,255,0.06)' : 'rgba(97,93,255,0.04)',
        },
        '& .MuiDataGrid-row.Mui-selected': {
          backgroundColor: theme.palette.mode === 'dark' ? 'rgba(97,93,255,0.12)' : 'rgba(97,93,255,0.08)',
        },
        '& .MuiDataGrid-cell': {
          borderColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
          fontSize: '0.875rem',
        },
        '& .MuiDataGrid-footerContainer': {
          borderTop: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'}`,
        },
        ...callerSx,
      }}
      rows={filteredRows}
      {...rest}
    />
    </Box>
  );
}
