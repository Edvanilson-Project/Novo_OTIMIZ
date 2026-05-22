import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreatePasswordResetTokens1716500000000 implements MigrationInterface {
  name = 'CreatePasswordResetTokens1716500000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "password_reset_tokens" (
        "id"        SERIAL PRIMARY KEY,
        "userId"    INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "tokenHash" VARCHAR(64) NOT NULL,
        "expiresAt" TIMESTAMP NOT NULL,
        "usedAt"    TIMESTAMP,
        "createdAt" TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT "UQ_password_reset_tokens_tokenHash" UNIQUE ("tokenHash")
      )
    `);

    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_password_reset_tokens_userId"
      ON "password_reset_tokens" ("userId")
    `);

    // Purge expired/used tokens older than 24h
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_password_reset_tokens_expiresAt"
      ON "password_reset_tokens" ("expiresAt")
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE IF EXISTS "password_reset_tokens"`);
  }
}
