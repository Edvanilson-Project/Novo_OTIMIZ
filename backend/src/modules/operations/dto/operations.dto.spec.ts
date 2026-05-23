import { plainToInstance } from 'class-transformer';
import { validateSync } from 'class-validator';
import {
  CreateDriverDto,
  CreateTripDto,
  UpdateDriverDto,
  UpdateTripDto,
} from './operations.dto';

describe('operations DTO contract', () => {
  it('aceita viagens com HH:MM, overnight e payload de ida+volta', () => {
    const dto = plainToInstance(CreateTripDto, {
      startTime: '23:00',
      endTime: '02:00',
      originId: '1',
      destinationId: '2',
      distanceKm: '12.5',
      roundTrip: 'true',
      returnStartTime: '02:15',
      returnEndTime: '04:00',
      returnOriginId: '2',
      returnDestinationId: '1',
      returnDistanceKm: '12.5',
    });

    expect(validateSync(dto)).toHaveLength(0);
    expect(dto.startTime).toBe(1380);
    expect(dto.endTime).toBe(120);
    expect(dto.roundTrip).toBe(true);
    expect(dto.returnStartTime).toBe(135);
    expect(dto.returnEndTime).toBe(240);
  });

  it('aceita update de viagem com minutos acima de 24h e campos reais do frontend', () => {
    const dto = plainToInstance(UpdateTripDto, {
      lineCode: 'L1',
      startTime: 1500,
      endTime: 1680,
      originId: '10',
      destinationId: '11',
      duration: '180',
    });

    expect(validateSync(dto)).toHaveLength(0);
    expect(dto.startTime).toBe(1500);
    expect(dto.endTime).toBe(1680);
    expect(dto.originId).toBe(10);
    expect(dto.destinationId).toBe(11);
  });

  it('aceita lastShiftEnd e driverId em create/update de motoristas', () => {
    const createDto = plainToInstance(CreateDriverDto, {
      driverId: 'D001',
      name: 'João',
      maxHoursPerDay: '480',
      lastShiftEnd: '1500',
    });
    const updateDto = plainToInstance(UpdateDriverDto, {
      driverId: 'D001',
      lastShiftEnd: '90',
    });

    expect(validateSync(createDto)).toHaveLength(0);
    expect(validateSync(updateDto)).toHaveLength(0);
    expect(createDto.lastShiftEnd).toBe(1500);
    expect(updateDto.driverId).toBe('D001');
    expect(updateDto.lastShiftEnd).toBe(90);
  });
});