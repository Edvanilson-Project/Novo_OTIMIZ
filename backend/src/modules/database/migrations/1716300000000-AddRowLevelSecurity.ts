import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Habilita Row-Level Security (RLS) nas tabelas multi-tenant para garantir
 * isolamento de dados no nível do banco — não apenas no ORM.
 *
 * Estratégia: app_user (usuário de conexão) seta a variável de sessão
 * app.current_company_id antes de qualquer query. A policy usa esta variável
 * para filtrar automaticamente todas as linhas.
 *
 * O usuário de superusuário/admin do banco faz BYPASS RLS por padrão (pg_ctl).
 * Para migrations e seeds, usar o superusuário.
 */
export class AddRowLevelSecurity1716300000000 implements MigrationInterface {
  name = 'AddRowLevelSecurity1716300000000';

  private readonly TENANT_TABLES = [
    'trips',
    'drivers',
    'schedules',
    'block_assignments',
    'duty_assignments',
    'lines',
    'terminals',
    'audit_logs',
    'optimization_runs',
    'custom_reports',
    'company_parameters',
    'vehicles',
    'vehicle_types',
    'vehicle_maintenances',
    'vehicle_availability_windows',
  ];

  public async up(queryRunner: QueryRunner): Promise<void> {
    // Cria função helper para extrair o company_id da sessão corrente
    await queryRunner.query(`
      CREATE OR REPLACE FUNCTION current_company_id() RETURNS INTEGER AS $$
        SELECT NULLIF(current_setting('app.current_company_id', true), '')::INTEGER;
      $$ LANGUAGE SQL STABLE;
    `);

    for (const table of this.TENANT_TABLES) {
      const tableExists = await queryRunner.hasTable(table);
      if (!tableExists) continue;

      const hasCompanyId = await queryRunner.hasColumn(table, 'companyId');
      if (!hasCompanyId) continue;

      await queryRunner.query(`ALTER TABLE "${table}" ENABLE ROW LEVEL SECURITY`);

      // FORCE para não fazer bypass mesmo para o dono da tabela (exceto superusuário)
      await queryRunner.query(`ALTER TABLE "${table}" FORCE ROW LEVEL SECURITY`);

      // DROP se já existir (idempotente)
      await queryRunner.query(
        `DROP POLICY IF EXISTS tenant_isolation ON "${table}"`,
      );

      // Policy: quando current_company_id() é NULL (sessão sem contexto de tenant,
      // ex: Celery workers, migrations, seeds) todas as linhas são visíveis —
      // o isolamento fica a cargo do ORM. Quando está definido, restringe ao tenant.
      await queryRunner.query(`
        CREATE POLICY tenant_isolation ON "${table}"
          USING (current_company_id() IS NULL OR "companyId" = current_company_id())
          WITH CHECK (current_company_id() IS NULL OR "companyId" = current_company_id())
      `);
    }
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    for (const table of this.TENANT_TABLES) {
      const tableExists = await queryRunner.hasTable(table);
      if (!tableExists) continue;

      await queryRunner.query(
        `DROP POLICY IF EXISTS tenant_isolation ON "${table}"`,
      );
      await queryRunner.query(
        `ALTER TABLE "${table}" DISABLE ROW LEVEL SECURITY`,
      );
    }

    await queryRunner.query(`DROP FUNCTION IF EXISTS current_company_id()`);
  }
}
