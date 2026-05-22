import { CompanyParameters } from '../database/entities/company-parameters.entity';

const FRACTION_PERCENT_FIELDS: Array<
  'waiting_time_pay_pct' | 'holiday_extra_pct' | 'nocturnal_extra_pct'
> = ['waiting_time_pay_pct', 'holiday_extra_pct', 'nocturnal_extra_pct'];

export function normalizeLegacyCompanyParameters<
  T extends Partial<CompanyParameters> | null | undefined,
>(params: T): { normalized: T; changed: boolean } {
  if (!params) {
    return { normalized: params, changed: false };
  }

  const normalized = { ...params } as T;
  let changed = false;

  for (const field of FRACTION_PERCENT_FIELDS) {
    const currentValue = (normalized as any)[field];
    if (
      typeof currentValue !== 'number' ||
      !Number.isFinite(currentValue) ||
      currentValue <= 1
    ) {
      continue;
    }

    (normalized as any)[field] = currentValue / 100;
    changed = true;
  }

  return { normalized, changed };
}
