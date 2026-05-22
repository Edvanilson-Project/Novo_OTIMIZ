/**
 * Defaults globais para parâmetros de otimização. Use estas constantes em vez de
 * literais espalhados (cost_vehicle ?? 1000.0, etc) — assim quando um default
 * mudar, basta editar um lugar.
 *
 * NÃO use estes valores como verdade operacional — eles são apenas fallback
 * para empresas sem `company_parameters` configurados. Em produção, todo
 * tenant precisa ter parâmetros próprios cadastrados.
 */

/** Custo de ativar um veículo no dia (R$). Sobrescrito por company_parameters.vehicle_fixed_cost. */
export const DEFAULT_VEHICLE_FIXED_COST = 800.0;

/** Penalidade legada por veículo ativado (R$). Mantido como fallback do `cost_vehicle` antigo. */
export const DEFAULT_COST_VEHICLE = 1000.0;

/** Custo por km de deadhead (R$/km). */
export const DEFAULT_COST_KM = 1.0;

/** Custo overhead por jornada criada (R$). Sobrescrito por company_parameters.cost_duty. */
export const DEFAULT_COST_DUTY = 500.0;

/** Penalidade por violação de CCT (R$ por violação). */
export const DEFAULT_CCT_VIOLATION_PENALTY = 500.0;

/** Timeout do ILP do solver set-partitioning (segundos). */
export const DEFAULT_ILP_TIMEOUT_SECONDS = 120;

/** TTL do cache local de schedule no service (ms). */
export const SCHEDULE_CACHE_TTL_MS = 15_000;

/** Limite de items detalhados por response em endpoints de relatório. */
export const REPORT_DETAIL_LIMIT = 10;
