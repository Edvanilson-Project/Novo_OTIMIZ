/**
 * Seed mínimo para o job de E2E no CI.
 *
 * Cria:
 *  - Company #1 (Demo Transportes)
 *  - Usuário admin: admin@empresa.com / admin123
 *  - Terminais, tipos de veículo e veículos de demonstração
 *
 * Idempotente: usa INSERT ... ON CONFLICT DO NOTHING onde possível.
 *
 * Uso:
 *   npx ts-node -r tsconfig-paths/register src/database/seeds/seed-e2e.ts
 */
import 'reflect-metadata';
import * as bcrypt from 'bcrypt';
import { DataSource } from 'typeorm';
import { seedVehiclesData } from './vehicle-types-and-vehicles.seed';

const AppDataSource = new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432'),
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'otimiz_e2e',
  entities: [__dirname + '/../../modules/database/entities/**/*.entity.ts'],
  synchronize: false,
  logging: false,
});

async function run() {
  await AppDataSource.initialize();
  const qr = AppDataSource.createQueryRunner();

  try {
    // 1. Empresa
    await qr.query(`
      INSERT INTO companies (name, slug, cnpj, "isActive", "createdAt", "updatedAt")
      VALUES ('Demo Transportes', 'demo-transportes', '00000000000100', true, NOW(), NOW())
      ON CONFLICT (slug) DO NOTHING
    `);
    const [{ id: companyId }] = await qr.query(
      `SELECT id FROM companies WHERE slug = 'demo-transportes' LIMIT 1`,
    );

    // 2. Admin user
    const hash = await bcrypt.hash('admin123', 10);
    await qr.query(`
      INSERT INTO users (email, "passwordHash", name, role, "companyId", "isActive", "createdAt", "updatedAt")
      VALUES ('admin@empresa.com', $1, 'Admin E2E', 'super_admin', $2, true, NOW(), NOW())
      ON CONFLICT (email) DO NOTHING
    `, [hash, companyId]);

    console.log('✓ Company + admin user seeded (companyId=' + companyId + ')');

    // 3. Terminais, veículos, etc.
    await seedVehiclesData(AppDataSource);

    console.log('✓ E2E seed complete');
  } finally {
    await qr.release();
    await AppDataSource.destroy();
  }
}

run().catch((e) => { console.error(e); process.exit(1); });
