import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddMaxBlockSpanMinutes1716700000000
  implements MigrationInterface
{
  name = 'AddMaxBlockSpanMinutes1716700000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "company_parameters" ADD COLUMN IF NOT EXISTS "max_block_span_minutes" integer',
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "company_parameters" DROP COLUMN IF EXISTS "max_block_span_minutes"',
    );
  }
}
