/**
 * Helpers para exportar conflitos operacionais em diferentes formatos
 */

import type { OperationalConflict } from './operational-conflicts';
import type { OptimizationResultSummary } from '../../_types';
import { detectOperationalConflicts } from './operational-conflicts';

export interface ExportFormat {
  format: 'csv' | 'json' | 'tsv' | 'html';
  filename: string;
  content: string;
  mimeType: string;
}

/**
 * Converte conflitos para CSV
 */
export function conflictsToCSV(conflicts: OperationalConflict[]): string {
  const header = ['Bloco', 'Tipo', 'Severidade', 'Mensagem', 'Count'].join(',');
  
  const rows = conflicts.map(c => {
    const bloco = c.blockId ? `#${c.blockId}` : 'N/A';
    const tipo = c.type.toUpperCase();
    const severidade = c.severity === 'error' ? 'ERRO' : 'AVISO';
    const mensagem = `"${c.message.replace(/"/g, '""')}"`;
    const count = c.count || 1;
    
    return [bloco, tipo, severidade, mensagem, count].join(',');
  });

  return [header, ...rows].join('\n');
}

/**
 * Converte conflitos para TSV (Tab-Separated)
 */
export function conflictsToTSV(conflicts: OperationalConflict[]): string {
  const header = ['Bloco', 'Tipo', 'Severidade', 'Mensagem', 'Count'].join('\t');
  
  const rows = conflicts.map(c => {
    const bloco = c.blockId ? `#${c.blockId}` : 'N/A';
    const tipo = c.type.toUpperCase();
    const severidade = c.severity === 'error' ? 'ERRO' : 'AVISO';
    const mensagem = c.message;
    const count = c.count || 1;
    
    return [bloco, tipo, severidade, mensagem, count].join('\t');
  });

  return [header, ...rows].join('\n');
}

/**
 * Converte conflitos para JSON estruturado
 */
export function conflictsToJSON(conflicts: OperationalConflict[], res: OptimizationResultSummary): string {
  const summary = {
    exportDate: new Date().toISOString(),
    totalConflicts: conflicts.length,
    totalBlocks: res.blocks?.length || 0,
    totalDuties: res.duties?.length || 0,
    conflicts: conflicts.map(c => ({
      blockId: c.blockId,
      type: c.type,
      severity: c.severity,
      message: c.message,
      count: c.count,
    })),
    stats: {
      errors: conflicts.filter(c => c.severity === 'error').length,
      warnings: conflicts.filter(c => c.severity === 'warning').length,
      byType: Array.from(
        conflicts.reduce((map, c) => {
          map.set(c.type, (map.get(c.type) || 0) + 1);
          return map;
        }, new Map<string, number>())
      ).map(([type, count]) => ({ type, count })),
    },
  };

  return JSON.stringify(summary, null, 2);
}

/**
 * Converte conflitos para HTML tabulado
 */
export function conflictsToHTML(conflicts: OperationalConflict[]): string {
  const timestamp = new Date().toLocaleString('pt-BR');
  
  const rows = conflicts.map(c => {
    const severityColor = c.severity === 'error' ? '#d32f2f' : '#f57c00';
    return `
    <tr>
      <td style="border: 1px solid #ddd; padding: 8px;">${c.blockId ? `#${c.blockId}` : 'N/A'}</td>
      <td style="border: 1px solid #ddd; padding: 8px;">${c.type.toUpperCase()}</td>
      <td style="border: 1px solid #ddd; padding: 8px; color: ${severityColor}; font-weight: bold;">${c.severity === 'error' ? 'ERRO' : 'AVISO'}</td>
      <td style="border: 1px solid #ddd; padding: 8px;">${c.message}</td>
      <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">${c.count || 1}</td>
    </tr>
    `;
  }).join('');

  return `
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatório de Conflitos Operacionais</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }
    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    h1 { color: #333; border-bottom: 2px solid #1976d2; padding-bottom: 10px; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }
    .summary-card { padding: 15px; background: #f9f9f9; border-left: 4px solid #1976d2; border-radius: 4px; }
    .summary-card h3 { margin: 0 0 5px 0; font-size: 14px; color: #666; }
    .summary-card .value { font-size: 24px; font-weight: bold; color: #333; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background: #f5f5f5; border: 1px solid #ddd; padding: 12px; text-align: left; font-weight: 600; }
    .timestamp { text-align: right; color: #999; font-size: 12px; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Relatório de Conflitos Operacionais</h1>
    
    <div class="summary">
      <div class="summary-card">
        <h3>Total de Conflitos</h3>
        <div class="value">${conflicts.length}</div>
      </div>
      <div class="summary-card">
        <h3>Erros</h3>
        <div class="value" style="color: #d32f2f;">${conflicts.filter(c => c.severity === 'error').length}</div>
      </div>
      <div class="summary-card">
        <h3>Avisos</h3>
        <div class="value" style="color: #f57c00;">${conflicts.filter(c => c.severity === 'warning').length}</div>
      </div>
      <div class="summary-card">
        <h3>Tipos Únicos</h3>
        <div class="value">${new Set(conflicts.map(c => c.type)).size}</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Bloco</th>
          <th>Tipo</th>
          <th>Severidade</th>
          <th>Mensagem</th>
          <th style="text-align: center; width: 50px;">Count</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>

    <div class="timestamp">Gerado em: ${timestamp}</div>
  </div>
</body>
</html>
  `;
}

/**
 * Cria um Blob para download e dispara o download
 */
export function downloadExport(format: ExportFormat) {
  const blob = new Blob([format.content], { type: format.mimeType });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = format.filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

/**
 * Gera e dispara download de conflitos em formato selecionado
 */
export function exportConflicts(
  res: OptimizationResultSummary,
  format: 'csv' | 'tsv' | 'json' | 'html'
): ExportFormat {
  const conflicts = detectOperationalConflicts(res);
  const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD

  switch (format) {
    case 'csv':
      return {
        format: 'csv',
        filename: `conflitos-operacionais-${timestamp}.csv`,
        content: conflictsToCSV(conflicts),
        mimeType: 'text/csv;charset=utf-8',
      };

    case 'tsv':
      return {
        format: 'tsv',
        filename: `conflitos-operacionais-${timestamp}.tsv`,
        content: conflictsToTSV(conflicts),
        mimeType: 'text/tab-separated-values;charset=utf-8',
      };

    case 'json':
      return {
        format: 'json',
        filename: `conflitos-operacionais-${timestamp}.json`,
        content: conflictsToJSON(conflicts, res),
        mimeType: 'application/json;charset=utf-8',
      };

    case 'html':
      return {
        format: 'html',
        filename: `conflitos-operacionais-${timestamp}.html`,
        content: conflictsToHTML(conflicts),
        mimeType: 'text/html;charset=utf-8',
      };

    default:
      throw new Error(`Unsupported export format: ${format}`);
  }
}
