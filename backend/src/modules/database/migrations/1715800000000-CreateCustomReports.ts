import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Cria a tabela `custom_reports` (FASE 4.2 — Relatórios Customizados).
 * Cada empresa pode salvar templates de relatório com seleção de métricas + filtros.
 * Idempotente.
 */
export class CreateCustomReports1715800000000 implements MigrationInterface {
  name = 'CreateCustomReports1715800000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'custom_report_format') THEN
          CREATE TYPE custom_report_format AS ENUM ('json', 'csv', 'pdf');
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS custom_reports (
        id SERIAL PRIMARY KEY,
        "createdAt" TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt" TIMESTAMP NOT NULL DEFAULT now(),
        "companyId" INTEGER NOT NULL,
        "name" VARCHAR(200) NOT NULL,
        "description" TEXT NULL,
        "ownerUserId" INTEGER NULL,
        "metrics" JSONB NOT NULL,
        "filters" JSONB NOT NULL DEFAULT '{}'::jsonb,
        "format" custom_report_format NOT NULL DEFAULT 'json'
      );
    `);

    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS idx_custom_reports_owner
        ON custom_reports ("companyId", "ownerUserId");
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS idx_custom_reports_owner;`);
    await queryRunner.query(`DROP TABLE IF EXISTS custom_reports;`);
    await queryRunner.query(`DROP TYPE IF EXISTS custom_report_format;`);
  }
}
