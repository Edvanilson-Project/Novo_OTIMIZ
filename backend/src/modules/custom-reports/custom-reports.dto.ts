import {
  ArrayMinSize,
  ArrayNotEmpty,
  IsArray,
  IsEnum,
  IsInt,
  IsOptional,
  IsString,
  MaxLength,
  Min,
} from 'class-validator';
import { Type } from 'class-transformer';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { CustomReportFormat } from '../database/entities/custom-report.entity';

/**
 * Filtros suportados ao executar/prever um relatório.
 * Mantido como interface porque a coluna é jsonb (extensível por design).
 */
export interface CustomReportFilters {
  dateRangeDays?: number;
  [key: string]: unknown;
}

/**
 * Linha do array recentRuns retornada em runs/previews.
 * Campos opcionais — preenchidos pelo execute() conforme `metrics` solicitadas;
 * helpers como toCsv/toPdf aceitam objetos parciais (eg. fixtures de teste).
 */
export interface RecentRunSummary {
  id: number;
  status: string;
  createdAt?: Date | string;
  totalCost?: string | number | null;
  cctViolations?: number | null;
  vehicles?: number | null;
  crew?: number | null;
  algorithm?: string | null;
}

/**
 * Payload retornado por run/preview/execute.
 * Os campos são opcionais porque dependem das `metrics` solicitadas.
 * O `[key: string]: unknown` permite que toCsv/toPdf consumam payloads
 * parciais (eg. fixtures de teste com campos arbitrários).
 */
export interface CustomReportPayload {
  generatedAt?: string;
  filters?: { dateRangeDays: number };
  totalRuns?: number;
  completedRuns?: number;
  failedRuns?: number;
  successRate?: number;
  totalTrips?: number;
  totalLines?: number;
  avgVehicles?: number | null;
  avgCrew?: number | null;
  avgCost?: number | null;
  trend7d?: number | null;
  recentRuns?: RecentRunSummary[];
  [key: string]: unknown;
}

export class CreateCustomReportDto {
  @ApiProperty({ example: 'Relatório operacional mensal' })
  @IsString()
  @MaxLength(200)
  name: string;

  @ApiPropertyOptional({ example: 'Resumo das otimizações dos últimos 30 dias' })
  @IsOptional()
  @IsString()
  description?: string;

  @ApiPropertyOptional({ example: 42 })
  @IsOptional()
  @IsInt()
  ownerUserId?: number;

  @ApiProperty({ example: ['totalRuns', 'successRate'], type: [String] })
  @IsArray()
  @ArrayNotEmpty()
  @IsString({ each: true })
  metrics: string[];

  @ApiPropertyOptional({ type: Object, example: { dateRangeDays: 30 } })
  @IsOptional()
  filters?: CustomReportFilters;

  @ApiPropertyOptional({ enum: CustomReportFormat })
  @IsOptional()
  @IsEnum(CustomReportFormat)
  format?: CustomReportFormat;
}

export class UpdateCustomReportDto {
  @ApiPropertyOptional({ example: 'Relatório semanal' })
  @IsOptional()
  @IsString()
  @MaxLength(200)
  name?: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  description?: string;

  @ApiPropertyOptional({ type: [String] })
  @IsOptional()
  @IsArray()
  @ArrayMinSize(1)
  @IsString({ each: true })
  metrics?: string[];

  @ApiPropertyOptional({ type: Object })
  @IsOptional()
  filters?: CustomReportFilters;

  @ApiPropertyOptional({ enum: CustomReportFormat })
  @IsOptional()
  @IsEnum(CustomReportFormat)
  format?: CustomReportFormat;
}

export class PreviewCustomReportDto {
  @ApiProperty({ type: [String] })
  @IsArray()
  @ArrayNotEmpty()
  @IsString({ each: true })
  metrics: string[];

  @ApiPropertyOptional({ type: Object })
  @IsOptional()
  filters?: CustomReportFilters;
}

/**
 * Subset de filtros usados em queries de janela temporal.
 */
export class DateRangeFiltersDto {
  @ApiPropertyOptional({ example: 30, minimum: 1 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  dateRangeDays?: number;
}
