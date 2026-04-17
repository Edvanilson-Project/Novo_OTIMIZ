import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from './../src/app.module';
import { DataSource } from 'typeorm';
import { JwtService } from '@nestjs/jwt';
import * as XLSX from 'xlsx';
import { Company } from './../src/modules/database/entities/company.entity';
import { Trip } from './../src/modules/database/entities/trip.entity';
import { User } from './../src/modules/database/entities/user.entity';

describe('Operations E2E (Módulo 4)', () => {
  let app: INestApplication;
  let dataSource: DataSource;
  let jwtService: JwtService;
  let companyA: Company;
  let tokenA: string;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();

    dataSource = moduleFixture.get<DataSource>(DataSource);
    jwtService = moduleFixture.get<JwtService>(JwtService);

    // Reset total
    await dataSource.createQueryBuilder().delete().from(Trip).execute();
    await dataSource.createQueryBuilder().delete().from(User).execute();
    await dataSource.createQueryBuilder().delete().from(Company).execute();

    // Setup Empresa A
    companyA = await dataSource.getRepository(Company).save({ name: 'Matriz SP', slug: 'matriz-sp' });
    const userA = await dataSource.getRepository(User).save({
      name: 'Ops A',
      email: 'ops-a@otimiz.com',
      passwordHash: '123',
      companyId: companyA.id,
    });
    tokenA = await jwtService.signAsync(
      { sub: userA.id, email: userA.email, companyId: companyA.id },
      { secret: 'mudar_para_um_segredo_forte_em_producao' }
    );
  });

  afterAll(async () => {
    await dataSource.destroy();
    await app.close();
  });

  it('Deve fazer upload de planilha de viagens e persistir com sucesso', async () => {
    // 1. Gerar planilha em memória
    const data = [
      { tripId: 101, lineId: 1, startTime: 480, endTime: 540, originId: 1, destinationId: 2 },
      { tripId: 102, lineId: 1, startTime: 550, endTime: 610, originId: 2, destinationId: 1 },
    ];
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Trips');
    const buffer = XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' });

    // 2. Upload via Supertest
    await request(app.getHttpServer())
      .post('/operations/upload')
      .set('Authorization', `Bearer ${tokenA}`)
      .field('type', 'trips')
      .attach('file', buffer, 'trips.xlsx')
      .expect(201);

    // 3. Verificar persistência
    const trips = await dataSource.getRepository(Trip).find({ where: { companyId: companyA.id } });
    expect(trips.length).toBe(2);
    expect(trips[0].tripId).toBe(101);
    expect(trips[0].startTime).toBe(480);
  });

  it('Deve rejeitar upload se campos obrigatórios estiverem ausentes', async () => {
    const data = [{ tripId: 201, startTime: 600 }]; // Falta endTime
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Incompleto');
    const buffer = XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' });

    const res = await request(app.getHttpServer())
      .post('/operations/upload')
      .set('Authorization', `Bearer ${tokenA}`)
      .field('type', 'trips')
      .attach('file', buffer, 'bad.xlsx')
      .expect(400);

    expect(res.body.message).toContain('endTime são obrigatórios');
  });
});
