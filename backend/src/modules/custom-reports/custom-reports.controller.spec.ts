import { Test, TestingModule } from '@nestjs/testing';
import { CustomReportsController } from './custom-reports.controller';
import {
  CustomReportsService,
  SUPPORTED_METRICS,
} from './custom-reports.service';
import { CreateCustomReportDto } from './custom-reports.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('CustomReportsController', () => {
  let controller: CustomReportsController;
  let service: jest.Mocked<Partial<CustomReportsService>>;

  beforeEach(async () => {
    service = {
      findAll: jest.fn().mockResolvedValue([{ id: 1, name: 'R1' }]),
      findOne: jest.fn().mockResolvedValue({ id: 1, name: 'R1' }),
      create: jest.fn().mockResolvedValue({ id: 2, name: 'R2' }),
      update: jest.fn().mockResolvedValue({ id: 1, name: 'Updated' }),
      remove: jest.fn().mockResolvedValue(undefined),
      preview: jest.fn().mockResolvedValue({ rows: [] }),
      run: jest.fn().mockResolvedValue({ rows: [{ a: 1 }] }),
      toCsv: jest.fn().mockReturnValue('a\n1\n'),
      toPdf: jest.fn().mockResolvedValue(Buffer.from('PDF')),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [CustomReportsController],
      providers: [{ provide: CustomReportsService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(CustomReportsController);
  });

  it('listSupportedMetrics returns metrics list', () => {
    const result = controller.listSupportedMetrics();
    expect(result).toEqual({ metrics: SUPPORTED_METRICS });
  });

  it('findAll returns list', async () => {
    expect(await controller.findAll()).toHaveLength(1);
  });

  it('findOne calls service with id', async () => {
    const result = await controller.findOne(1);
    expect(service.findOne).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ id: 1 });
  });

  it('create calls service.create', async () => {
    // O input parcial é intencional — testamos o pass-through do controller,
    // não a validação (que é feita pelo ValidationPipe no app real).
    const result = await controller.create({ name: 'R2' } as CreateCustomReportDto);
    expect(service.create).toHaveBeenCalledWith({ name: 'R2' });
    expect(result).toMatchObject({ id: 2 });
  });

  it('update calls service.update', async () => {
    await controller.update(1, { name: 'Updated' });
    expect(service.update).toHaveBeenCalledWith(1, { name: 'Updated' });
  });

  it('remove calls service.remove', async () => {
    await controller.remove(1);
    expect(service.remove).toHaveBeenCalledWith(1);
  });

  it('preview calls service.preview with metrics and filters', async () => {
    const result = await controller.preview({
      metrics: ['trips'],
      filters: { companyId: 1 },
    });
    expect(service.preview).toHaveBeenCalledWith(['trips'], { companyId: 1 });
    expect(result).toMatchObject({ rows: [] });
  });

  it('preview defaults filters to empty object when absent', async () => {
    await controller.preview({ metrics: ['trips'] });
    expect(service.preview).toHaveBeenCalledWith(['trips'], {});
  });

  it('run calls service.run', async () => {
    const result = await controller.run(1);
    expect(service.run).toHaveBeenCalledWith(1);
    expect(result).toMatchObject({ rows: [{ a: 1 }] });
  });
});
