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
import { Type } from 'class-transformer';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

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
  @IsInt()
  tripId?: number;

  @ApiPropertyOptional()
  @IsOptional()
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
  @IsInt()
  tripGroupId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  direction?: string;

  @ApiProperty({ description: 'Minutos desde meia-noite' })
  @IsInt()
  @Min(0)
  @Max(1439)
  startTime: number;

  @ApiProperty()
  @IsInt()
  @Min(0)
  @Max(1439)
  endTime: number;

  @ApiProperty()
  @IsInt()
  originId: number;

  @ApiProperty()
  @IsInt()
  destinationId: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  @Min(0)
  distanceKm?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  duration?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  originLatitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  originLongitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  destinationLatitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  destinationLongitude?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  reliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsBoolean()
  isReliefPoint?: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  midTripReliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  midTripReliefOffsetMinutes?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  depotId?: number;
}

export class UpdateTripDto {
  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  lineId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  direction?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(1439)
  startTime?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(1439)
  endTime?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsNumber()
  @Min(0)
  distanceKm?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsBoolean()
  isReliefPoint?: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  midTripReliefPointId?: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsInt()
  @Min(0)
  midTripReliefOffsetMinutes?: number;

  @ApiPropertyOptional()
  @IsOptional()
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
  @IsInt()
  @Min(60)
  @Max(840)
  maxHoursPerDay?: number;
}

export class UpdateDriverDto {
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
  @IsInt()
  @Min(60)
  @Max(840)
  maxHoursPerDay?: number;
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
  [key: string]: unknown;
}
