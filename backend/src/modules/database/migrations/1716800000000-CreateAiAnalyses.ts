import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateAiAnalyses1716800000000 implements MigrationInterface {
  name = 'CreateAiAnalyses1716800000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "ai_analyses" (
        "id" SERIAL PRIMARY KEY,
        "createdAt" TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt" TIMESTAMP NOT NULL DEFAULT now(),
        "companyId" integer NOT NULL,
        "question" text,
        "analysis" text NOT NULL,
        "model" varchar(200),
        "metricsSnapshot" jsonb
      )
    `);
    await queryRunner.query(
      'CREATE INDEX IF NOT EXISTS "IDX_ai_analyses_company_created" ON "ai_analyses" ("companyId", "createdAt")',
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'DROP INDEX IF EXISTS "IDX_ai_analyses_company_created"',
    );
    await queryRunner.query('DROP TABLE IF EXISTS "ai_analyses"');
  }
}
