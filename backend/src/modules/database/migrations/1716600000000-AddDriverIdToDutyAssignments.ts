import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddDriverIdToDutyAssignments1716600000000
  implements MigrationInterface
{
  name = 'AddDriverIdToDutyAssignments1716600000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "duty_assignments" ADD COLUMN IF NOT EXISTS "driverId" integer',
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "duty_assignments" DROP COLUMN IF EXISTS "driverId"',
    );
  }
}