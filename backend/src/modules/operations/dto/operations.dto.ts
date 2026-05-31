import {
  IsString,
  IsOptional,
  IsInt,
  IsNumber,
  IsBoolean,
  IsArray,
  IsIn,
  Min,
  Max,
  IsObject,
  ValidateNested,
} from 'class-validator';
import { Transform, Type } from 'class-transformer';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

function isBlank(value: unknown): boolean {
  return value === undefined || value === null || value === '';
}

function transformInt(value: unknown): unknown {
  if (isBlank(value)) return value;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : value;
}

function transformFloat(value: unknown): unknown {
  if (isBlank(value)) return value;
  const parsed = Number(String(value).replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : value;
}

function transformBoolean(value: unknown): unknown {
  if (isBlank(value)) return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true') return true;
    if (normalized === 'false') return false;
  }
  return value;
}

function transformMinutes(value: unknown): unknown {
  if (isBlank(value)) return value;
  if (typeof value === 'string') {
    const normalized = value.trim();
    const match = /^(\d+):(\d{2})(?::\d{2})?$/.exec(normalized);
    if (match) {
      return Number(match[1]) * 60 + Number(match[2]);
    }
  }
  return transformInt(value);
}

export class RunOptimizationDto {
  @ApiPropertyOptional({ example: 'hybrid_pipeline' })
  @IsOptional()
  @IsString()
  algorithm?: string;

  @ApiPropertyOptional({ example: 1 })
  @IsOptional()
  @IsInt()
  companyId?: number;

  @ApiPropertyOptional({ enum: ['strict', 'balanced', 'optimized'] })
  @IsOptional()
  @IsIn(['strict', 'balanced', 'optimized'])
  operational_quality_mode?: string;

  @ApiPropertyOptional({ type: [Number], example: [1, 2] })
  @IsOptional()
  @IsArray()
  @IsInt({ each: true })
  depot_ids?: number[];
}

export class ReassignTripDto {
  @ApiProperty()
  @IsInt()
  scheduleId: number;

  @ApiProperty()
  @IsInt()
  tripId: number;

  @ApiProperty()
  @IsInt()
  targetBlockId: number;
}

export class AiChatDto {
  @ApiProperty()
  @IsObject()
  metrics: Record<string, unknown>;

  @ApiProperty()
  @IsString()
  question: string;
}

export class CreateTripDto {
  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  tripId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  lineId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  lineCode?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  pairId?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  tripGroupId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  direction?: string;

  @ApiProperty({ description: 'Minutos desde meia-noite' })
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  startTime: number;

  @ApiProperty()
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  endTime: number;

  @ApiProperty()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  originId: number;

  @ApiProperty()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  destinationId: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  @Min(0)
  distanceKm?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  duration?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  originLatitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  originLongitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  destinationLatitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  destinationLongitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  reliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformBoolean(value))
  @IsBoolean()
  isReliefPoint?: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  midTripReliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  midTripReliefOffsetMinutes?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  depotId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformBoolean(value))
  @IsBoolean()
  roundTrip?: boolean;

  @ApiPropertyOptional({ description: 'Aceita minutos absolutos ou HH:MM' })
  @IsOptional()
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  returnStartTime?: number;

  @ApiPropertyOptional({ description: 'Aceita minutos absolutos ou HH:MM' })
  @IsOptional()
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  returnEndTime?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  returnDuration?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  returnOriginId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  returnDestinationId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  @Min(0)
  returnDistanceKm?: number;
}

export class UpdateTripDto {
  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  lineId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  lineCode?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  direction?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  startTime?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformMinutes(value))
  @IsInt()
  @Min(0)
  endTime?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  originId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  destinationId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  @Min(0)
  distanceKm?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  duration?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  reliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformBoolean(value))
  @IsBoolean()
  isReliefPoint?: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  midTripReliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  midTripReliefOffsetMinutes?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  @Min(0)
  midTripReliefDistanceRatio?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformFloat(value))
  @IsNumber()
  @Min(0)
  midTripReliefElevationRatio?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  depotId?: number;
}

export class CreateDriverDto {
  @ApiProperty()
  @IsString()
  driverId: string;

  @ApiProperty()
  @IsString()
  name: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  role?: string;

  @ApiPropertyOptional({ default: 480 })
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(60)
  @Max(840)
  maxHoursPerDay?: number;

  @ApiPropertyOptional({ default: 0 })
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  lastShiftEnd?: number;
}

export class UpdateDriverDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  driverId?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  name?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  role?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(60)
  @Max(840)
  maxHoursPerDay?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @Transform(({ value }) => transformInt(value))
  @IsInt()
  @Min(0)
  lastShiftEnd?: number;
}

export class EvaluateDeltaDto {
  @ApiProperty()
  @IsInt()
  scheduleId: number;

  @ApiProperty()
  @IsInt()
  tripId: number;

  @ApiProperty()
  @IsInt()
  targetBlockId: number;
}

/**
 * Subset mínimo de um bloco enviado pelo frontend para avaliação.
 * Aceita ambos os case-styles (camelCase do frontend e snake_case do solver)
 * porque o service normaliza internamente.
 */
export interface ScheduleBlockInput {
  id?: number;
  block_id?: number;
  trips?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface MoveTripInput {
  trip_id: number;
  source_block_id?: number;
  target_block_id: number;
  [key: string]: unknown;
}

export class EvaluateBaselineDto {
  @ApiProperty({ type: [Object] })
  @IsArray()
  blocks: ScheduleBlockInput[];
}

export class EvaluateDeltaPayloadDto {
  @ApiProperty({ type: [Object] })
  @IsArray()
  blocks: ScheduleBlockInput[];

  @ApiProperty({ type: Object })
  @IsObject()
  move: MoveTripInput;
}

/**
 * Body genérico para rostering semanal — encaminhado integralmente ao optimizer.
 * Schema flexível por design (parametrização avançada do solver Python).
 */
export class RosteringWeeklyDto {
  // Pass-through para o optimizer (/optimize/rostering/weekly faz a validação
  // profunda). Os campos precisam ser declarados porque a ValidationPipe global
  // usa whitelist+forbidNonWhitelisted: sem declará-los, o payload era rejeitado
  // com 400 e a Escala Semanal nunca executava.
  @IsOptional()
  @IsArray()
  operators?: unknown[];

  @IsOptional()
  @IsObject()
  daily_duties?: Record<string, unknown>;

  @IsOptional()
  @IsInt()
  weekly_hour_limit_minutes?: number;

  @IsOptional()
  @IsInt()
  min_days_off?: number;

  @IsOptional()
  @IsInt()
  min_inter_shift_rest_minutes?: number;

  @IsOptional()
  @IsNumber()
  time_budget_s?: number;
}
