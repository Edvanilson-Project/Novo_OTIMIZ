/**
 * Formatadores globais compartilhados entre módulos.
 *
 * Fonte única de verdade para moeda, duração, hora, porcentagens e parsing.
 * Módulos específicos (ex.: optimization) podem adicionar seus próprios
 * formatadores locais, mas NÃO devem redefinir os que estão aqui.
 */

// ─── Parsing helpers ────────────────────────────────────────────────────────

export function asRecord(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : null;
}

export function toMinuteValue(value: unknown): number | null {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

// ─── Moeda ──────────────────────────────────────────────────────────────────

export interface CurrencyOptions {
  /** Máximo de casas decimais exibidas. Default: 2 (ex.: "R$ 1.234,56"). */
  maxFractionDigits?: number;
}

export function fmtCurrency(
  value: number | string | null | undefined,
  options?: CurrencyOptions,
): string {
  if (value == null || value === "") return "--";
  const amount = Number(value);
  if (Number.isNaN(amount)) return "--";
  return amount.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 0,
    maximumFractionDigits: options?.maxFractionDigits ?? 2,
  });
}

export function fmtSignedCurrency(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const amount = Number(value);
  const absolute = Math.abs(amount).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  if (amount > 0) return `+${absolute}`;
  if (amount < 0) return `-${absolute}`;
  return absolute;
}

// ─── Numéricos ──────────────────────────────────────────────────────────────

export interface NumberOptions {
  /** Sufixo anexado ao final (ex.: "ms", "%", "km"). Default: "". */
  suffix?: string;
  /** Máximo de casas decimais. Default: 2. */
  maxFractionDigits?: number;
  /** Mínimo de casas decimais. Default: 0 (não força zeros à direita). */
  minFractionDigits?: number;
}

export function fmtNumber(
  value?: number | null,
  options: NumberOptions | string = {},
): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  // Backwards-compat: se options for string, trata como suffix.
  const opts: NumberOptions = typeof options === "string" ? { suffix: options } : options;
  return `${Number(value).toLocaleString("pt-BR", {
    maximumFractionDigits: opts.maxFractionDigits ?? 2,
    minimumFractionDigits: opts.minFractionDigits ?? 0,
  })}${opts.suffix ?? ""}`;
}

export function fmtSignedNumber(value?: number | null, suffix = ""): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const amount = Number(value);
  const sign = amount > 0 ? "+" : amount < 0 ? "-" : "";
  return `${sign}${Math.abs(amount).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}${suffix}`;
}

/** Percentual simples com N casas (sem sinal). Ex.: fmtPercent(12.7, 1) → "12,7%". */
export function fmtPercent(value?: number | null, digits = 0): string {
  if (value == null || !Number.isFinite(Number(value))) return "--";
  return `${Number(value).toLocaleString("pt-BR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}%`;
}

export function fmtSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const amount = Number(value);
  const sign = amount > 0 ? "+" : amount < 0 ? "-" : "";
  return `${sign}${Math.abs(amount).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

// ─── Tempo e duração ────────────────────────────────────────────────────────

/** Converte minutos em "Xh", "Xh05" ou "Xmin". Aceita negativos (usa abs). */
export function minToDuration(minutes: number | null | undefined): string {
  if (minutes == null || isNaN(Number(minutes))) return "--";
  const m = Math.floor(Math.abs(Number(minutes)));
  if (m < 60) return `${m}min`;
  const h = Math.floor(m / 60);
  const min = m % 60;
  return min > 0 ? `${h}h${min.toString().padStart(2, "0")}` : `${h}h`;
}

/** Converte minutos em "HH:MM". Para valores >= 1440 (dia seguinte), adiciona sufixo "+N". */
export function minToHHMM(minutes?: number | null): string {
  if (minutes == null || isNaN(Number(minutes))) return "--:--";
  const m = Math.abs(Number(minutes));
  const dayOffset = Math.floor(m / 1440);
  const minuteOfDay = m % 1440;
  const h = Math.floor(minuteOfDay / 60);
  const min = Math.floor(minuteOfDay % 60);
  const timeStr = `${h.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`;
  return dayOffset > 0 ? `${timeStr} +${dayOffset}` : timeStr;
}

/**
 * Formata duração em milissegundos para leitura humana:
 *   < 1s   → "543ms"
 *   < 1min → "1.2s"
 *   resto  → "2m 14s"
 * Ideal para cards de KPI de tempo de execução.
 */
export function fmtDurationMs(ms?: number | null): string {
  if (ms == null || !Number.isFinite(Number(ms)) || Number(ms) <= 0) return "--";
  const value = Number(ms);
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60000) {
    return `${(value / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}s`;
  }
  return `${Math.floor(value / 60000)}m ${Math.floor((value % 60000) / 1000)}s`;
}

/** Converte milissegundos em "1.2s" (>=1000ms) ou "543ms". */
export function fmtElapsedMsCompact(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const totalMs = Number(value);
  if (Math.abs(totalMs) >= 1000) {
    return `${(totalMs / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}s`;
  }
  return `${Math.round(totalMs).toLocaleString("pt-BR")}ms`;
}

// ─── Data ───────────────────────────────────────────────────────────────────

/** Formata Date/ISO em "DD/MM/YYYY HH:mm" (pt-BR). Retorna "--" para null/inválido. */
export function fmtDate(value: Date | string | number | null | undefined): string {
  if (value == null || value === "") return "--";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Formata Date/ISO em "DD/MM" (compacto — eixos de gráfico, labels densos). */
export function fmtDayMonth(value: Date | string | number | null | undefined): string {
  if (value == null || value === "") return "--";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** Formata Date/ISO em "DD/MM HH:mm" (sem ano — para linhas de tabela densas). */
export function fmtDateTimeShort(value: Date | string | number | null | undefined): string {
  if (value == null || value === "") return "--";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Formata Date/ISO só como "DD/MM/YYYY". */
export function fmtDateOnly(value: Date | string | number | null | undefined): string {
  if (value == null || value === "") return "--";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleDateString("pt-BR");
}

// ─── Strings ────────────────────────────────────────────────────────────────

/** "total_cost" → "Total Cost", "totalCost" → "Total Cost". */
export function labelizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Trunca string pelo meio preservando head/tail. Útil para hashes. */
export function truncateMiddle(value?: string | null, head = 5, tail = 4): string {
  if (!value) return "--";
  return value.length <= head + tail + 1
    ? value
    : `${value.slice(0, head)}...${value.slice(-tail)}`;
}
