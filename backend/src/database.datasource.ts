/**
 * DataSource para o TypeORM CLI (migration:run, migration:generate, etc.)
 *
 * Uso:
 *   npm run migration:run      — aplica migrations pendentes
 *   npm run migration:revert   — reverte a última migration
 *   npm run migration:generate -- src/modules/database/migrations/NomeDaMigration
 *
 * Requer variáveis de ambiente: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
 * (ou os valores padrão abaixo para desenvolvimento local).
 */
import 'reflect-metadata';
import 'dotenv/config';
import { DataSource } from 'typeorm';

export default new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST || 'localhost',
  port: Number(process.env.DB_PORT) || 5432,
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'otimiz',
  entities: [__dirname + '/modules/database/entities/*.entity.ts', '!' + __dirname + '/modules/database/entities/*.spec.ts'],
  migrations: [__dirname + '/modules/database/migrations/*{.ts,.js}'],
  synchronize: false,
});
