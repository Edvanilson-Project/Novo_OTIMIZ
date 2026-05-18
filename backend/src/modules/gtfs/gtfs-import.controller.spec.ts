import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { GtfsImportController } from './gtfs-import.controller';
import { GtfsImportService } from './gtfs-import.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

describe('GtfsImportController', () => {
  let controller: GtfsImportController;
  let service: jest.Mocked<Partial<GtfsImportService>>;

  const mockResult = {
    imported: { terminals: 3, lines: 2, trips: 10 },
    skipped: 1,
    errors: [],
  };

  beforeEach(async () => {
    service = {
      importFromBuffer: jest.fn().mockResolvedValue(mockResult),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [GtfsImportController],
      providers: [{ provide: GtfsImportService, useValue: service }],
    })
      .overrideGuard(JwtAuthGuard)
      .useValue({ canActivate: () => true })
      .compile();

    controller = module.get(GtfsImportController);
  });

  it('import calls service with file buffer and returns result', async () => {
    const file = { buffer: Buffer.from('zip') } as Express.Multer.File;
    const result = await controller.import(file);
    expect(service.importFromBuffer).toHaveBeenCalledWith(file.buffer);
    expect(result).toMatchObject({
      imported: { terminals: 3, lines: 2, trips: 10 },
    });
  });

  it('throws BadRequestException when no file provided', async () => {
    await expect(controller.import(undefined as any)).rejects.toThrow(
      BadRequestException,
    );
  });
});
