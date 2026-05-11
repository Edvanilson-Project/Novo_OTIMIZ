import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Cria a tabela `optimization_runs` que liga cenários da FASE 3 a runs reais
 * do motor de otimização. Idempotente: usa IF NOT EXISTS para suportar bancos
 * onde o DDL ad-hoc inicial já foi aplicado.
 *
 * Cada run armazena:
 * - scenarioId: identificador estável (current, cost-optimized, etc.)
 * - baselineScheduleId: schedule sobre o qual o cenário foi gerado
 * - resultScheduleId: schedule criado pela execução do solver (Block/Duty
 *   completos vão para esse FK)
 * - inputFingerprint: SHA-256 estável dos inputs — permite idempotência
 *   por (companyId, baselineScheduleId, scenarioId) e replay reproduzível
 * - params/metrics: jsonb, snapshot completo de configuração + resultado
 * - status: pending/running/completed/failed (enum)
 */
export class CreateOptimizationRuns1715450000000 implements MigrationInterface {
  name = 'CreateOptimizationRuns1715450000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    // Cria o tipo enum se não existir (Postgres não tem CREATE TYPE IF NOT EXISTS,
    // então checamos via pg_catalog).
    await queryRunner.query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'optimization_run_status') THEN
          CREATE TYPE optimization_run_status AS ENUM ('pending', 'running', 'completed', 'failed');
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS optimization_runs (
        id SERIAL PRIMARY KEY,
        "createdAt" TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt" TIMESTAMP NOT NULL DEFAULT now(),
        "companyId" INTEGER NOT NULL,
        "scenarioId" VARCHAR(64) NOT NULL,
        "baselineScheduleId" INTEGER NULL REFERENCES schedules(id) ON DELETE SET NULL,
        "resultScheduleId" INTEGER NULL REFERENCES schedules(id) ON DELETE CASCADE,
        "inputFingerprint" VARCHAR(64) NOT NULL,
        "params" JSONB NOT NULL,
        "algorithm" VARCHAR(64) NULL,
        "randomSeed" INTEGER NULL,
        "status" optimization_run_status NOT NULL DEFAULT 'pending',
        "metrics" JSONB NULL,
        "errorMessage" TEXT NULL,
        "durationMs" INTEGER NULL,
        "completedAt" TIMESTAMP NULL
      );
    `);

    // Índice para o caminho mais frequente: ScenarioEvaluator.ensureScenarioRun
    // procura por (companyId, baselineScheduleId, scenarioId, inputFingerprint).
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS idx_optimization_runs_lookup
        ON optimization_runs ("companyId", "baselineScheduleId", "scenarioId", "inputFingerprint");
    `);

    // Índice para filtrar runs completed por baseline/cenário (idempotência + histórico).
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS idx_optimization_runs_status
        ON optimization_runs ("companyId", "baselineScheduleId", "scenarioId", status, "completedAt" DESC);
    `);

    // Índice para reporting (compareReports filtra por baseline + completed + janela temporal).
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS idx_optimization_runs_history
        ON optimization_runs ("baselineScheduleId", status, "completedAt");
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS idx_optimization_runs_history;`);
    await queryRunner.query(`DROP INDEX IF EXISTS idx_optimization_runs_status;`);
    await queryRunner.query(`DROP INDEX IF EXISTS idx_optimization_runs_lookup;`);
    await queryRunner.query(`DROP TABLE IF EXISTS optimization_runs;`);
    await queryRunner.query(`DROP TYPE IF EXISTS optimization_run_status;`);
  }
}
