import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Moves refresh token storage from users table into a dedicated
 * refresh_tokens table with a UNIQUE index on token_hash.
 *
 * This enables O(1) token lookup (SHA-256 comparison) instead of
 * the previous O(n) bcrypt scan across all active users.
 *
 * The old refreshTokenHash/refreshTokenExpiresAt columns on users
 * are left intact (not dropped here) to allow safe rollback.
 */
export class CreateRefreshTokensTable1716400000000 implements MigrationInterface {
  name = 'CreateRefreshTokensTable1716400000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "refresh_tokens" (
        "id"          SERIAL PRIMARY KEY,
        "userId"      INTEGER NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
        "tokenHash"   VARCHAR(64) NOT NULL,
        "expiresAt"   TIMESTAMP NOT NULL,
        "userAgent"   VARCHAR(512),
        "createdAt"   TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT "UQ_refresh_tokens_tokenHash" UNIQUE ("tokenHash")
      )
    `);

    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_refresh_tokens_userId"
      ON "refresh_tokens" ("userId")
    `);

    // Purge expired rows daily — keeps the table lean
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_refresh_tokens_expiresAt"
      ON "refresh_tokens" ("expiresAt")
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE IF EXISTS "refresh_tokens"`);
  }
}
