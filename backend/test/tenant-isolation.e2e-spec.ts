import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import { AppModule } from './../src/app.module';
import { UserRepository } from './../src/modules/database/repositories/user.repository';
import { TenantContext } from './../src/common/context/tenant-context';
import { DataSource } from 'typeorm';
import { Company } from './../src/modules/database/entities/company.entity';
import { User } from './../src/modules/database/entities/user.entity';

describe('Tenant Isolation (Módulo 1)', () => {
  let app: INestApplication;
  let userRepository: UserRepository;
  let dataSource: DataSource;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();

    userRepository = moduleFixture.get<UserRepository>(UserRepository);
    dataSource = moduleFixture.get<DataSource>(DataSource);

    // Limpar banco para o teste (Ordem importa para FKs)
    await dataSource.createQueryBuilder().delete().from(User).execute();
    await dataSource.createQueryBuilder().delete().from(Company).execute();
  });

  afterAll(async () => {
    await dataSource.destroy();
    await app.close();
  });

  it('Deve garantir que o Tenant A não veja dados do Tenant B', async () => {
    // 1. Criar Empresas
    const companyA = await dataSource.getRepository(Company).save({ name: 'Empresa A', slug: 'empresa-a' });
    const companyB = await dataSource.getRepository(Company).save({ name: 'Empresa B', slug: 'empresa-b' });

    // 2. Criar Usuário para Empresa A diretamente via repo nativo (sem filtro)
    await dataSource.getRepository(User).save({
      name: 'User A',
      email: 'a@otimiz.com',
      passwordHash: '123',
      companyId: companyA.id,
    });

    // 3. Tentar buscar Usuário de A usando o contexto da Empresa B
    await TenantContext.run({ companyId: companyB.id }, async () => {
      const usersInB = await userRepository.find();
      expect(usersInB.length).toBe(0); // Não deve encontrar nada
    });

    // 4. Confirmar que no contexto da Empresa A o usuário existe
    await TenantContext.run({ companyId: companyA.id }, async () => {
      const usersInA = await userRepository.find();
      expect(usersInA.length).toBe(1);
      expect(usersInA[0].name).toBe('User A');
    });
  });
});
