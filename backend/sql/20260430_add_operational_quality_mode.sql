ALTER TABLE company_parameters
ADD COLUMN IF NOT EXISTS operational_quality_mode varchar(16) NOT NULL DEFAULT 'balanced';

UPDATE company_parameters
SET operational_quality_mode = 'balanced'
WHERE operational_quality_mode IS NULL
   OR operational_quality_mode NOT IN ('strict', 'balanced', 'optimized');

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'company_parameters_operational_quality_mode_check'
  ) THEN
    ALTER TABLE company_parameters
    ADD CONSTRAINT company_parameters_operational_quality_mode_check
    CHECK (operational_quality_mode IN ('strict', 'balanced', 'optimized'));
  END IF;
END $$;
