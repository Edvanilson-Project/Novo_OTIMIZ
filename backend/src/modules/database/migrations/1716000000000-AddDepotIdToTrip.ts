import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddDepotIdToTrip1716000000000 implements MigrationInterface {
  name = 'AddDepotIdToTrip1716000000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "trips" ADD COLUMN IF NOT EXISTS "depotId" integer`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "trips" DROP COLUMN IF EXISTS "depotId"`,
    );
  }
}
