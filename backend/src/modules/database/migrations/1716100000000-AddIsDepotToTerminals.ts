import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddIsDepotToTerminals1716100000000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE terminals
      ADD COLUMN IF NOT EXISTS "isDepot" boolean NOT NULL DEFAULT false
    `);
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE terminals DROP COLUMN IF EXISTS "isDepot"
    `);
  }
}
