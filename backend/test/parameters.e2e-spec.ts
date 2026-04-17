import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from './../src/app.module';
import { DataSource } from 'typeorm';
import { JwtService } from '@nestjs/jwt';
import { Company } from './../src/modules/database/entities/company.entity';
import { CompanyParameters } from './../src/modules/database/entities/company-parameters.entity';
import { User } from './../src/modules/database/entities/user.entity';

describe('Parameters E2E (Módulo 3)', () => {
  let app: INestApplication;
  let dataSource: DataSource;
  let jwtService: JwtService;
  let companyA: Company;
  let companyB: Company;
  let tokenA: string;
  let tokenB: string;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();

    dataSource = moduleFixture.get<DataSource>(DataSource);
    jwtService = moduleFixture.get<JwtService>(JwtService);

    // Limpeza reset total
    await dataSource.createQueryBuilder().delete().from(CompanyParameters).execute();
    await dataSource.createQueryBuilder().delete().from(User).execute();
    await dataSource.createQueryBuilder().delete().from(Company).execute();

    // Setup de teste - Empresa A
    companyA = await dataSource.getRepository(Company).save({ name: 'Matriz SP', slug: 'matriz-sp' });
    const userA = await dataSource.getRepository(User).save({
      name: 'Admin A',
      email: 'admin-a@otimiz.com',
      passwordHash: '123',
      companyId: companyA.id,
    });
    tokenA = await jwtService.signAsync({ sub: userA.id, email: userA.email, companyId: companyA.id }, { secret: 'mudar_para_um_segredo_forte_em_producao' });

    // Setup de teste - Empresa B
    companyB = await dataSource.getRepository(Company).save({ name: 'Filial RJ', slug: 'filial-rj' });
    const userB = await dataSource.getRepository(User).save({
      name: 'Admin B',
      email: 'admin-b@otimiz.com',
      passwordHash: '123',
      companyId: companyB.id,
    });
    tokenB = await jwtService.signAsync({ sub: userB.id, email: userB.email, companyId: companyB.id }, { secret: 'mudar_para_um_segredo_forte_em_producao' });
  });

  afterAll(async () => {
    await dataSource.destroy();
    await app.close();
  });

  it('Deve criar parâmetros padrão no primeiro GET e atualizar no PUT (Tenant A)', async () => {
    // 1. GET Inicial (deve criar padrão)
    const resGet = await request(app.getHttpServer())
      .get('/parameters')
      .set('Authorization', `Bearer ${tokenA}`)
      .expect(200);

    expect(resGet.body.meal_break_minutes).toBe(60);
    expect(resGet.body.vehicle_fixed_cost).toBe(800.0);
    expect(resGet.body.companyId).toBe(companyA.id);

    // 2. PUT Atualização
    await request(app.getHttpServer())
      .put('/parameters')
      .set('Authorization', `Bearer ${tokenA}`)
      .send({ meal_break_minutes: 45, driver_cost_per_minute: 0.8, vehicle_fixed_cost: 950.0 })
      .expect(200);

    // 3. GET Verificação
    const resVerify = await request(app.getHttpServer())
      .get('/parameters')
      .set('Authorization', `Bearer ${tokenA}`)
      .expect(200);

    expect(resVerify.body.meal_break_minutes).toBe(45);
    expect(resVerify.body.driver_cost_per_minute).toBe(0.8);
    expect(resVerify.body.vehicle_fixed_cost).toBe(950.0);
  });

  it('Deve garantir isolamento de parâmetros entre Tenants', async () => {
    // 1. Garantir que Empresa B tenha seus próprios parâmetros (padrão)
    const resGetB = await request(app.getHttpServer())
      .get('/parameters')
      .set('Authorization', `Bearer ${tokenB}`)
      .expect(200);

    expect(resGetB.body.meal_break_minutes).toBe(60); // B continua com o padrão
    expect(resGetB.body.companyId).toBe(companyB.id);

    // 2. Verificar que Empresa A ainda tem seus valores alterados
    const resGetA = await request(app.getHttpServer())
      .get('/parameters')
      .set('Authorization', `Bearer ${tokenA}`)
      .expect(200);

    expect(resGetA.body.meal_break_minutes).toBe(45); // A mantém o que salvou
  });
});
