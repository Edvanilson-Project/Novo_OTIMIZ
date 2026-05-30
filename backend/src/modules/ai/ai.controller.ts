import {
  Controller,
  Post,
  Get,
  Body,
  Query,
  HttpCode,
  UseGuards,
} from '@nestjs/common';
import { AiService, OptimizationResultSummary } from './ai.service';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { AiAnalysis } from '../database/entities/ai-analysis.entity';

interface AnalyzeRequest {
  result: OptimizationResultSummary;
  question?: string;
}

interface AnalyzeResponse {
  analysis: string;
  model?: string;
}

@Controller('ai')
export class AiController {
  constructor(private aiService: AiService) {}

  @Post('analyze')
  @HttpCode(200)
  async analyze(@Body() body: AnalyzeRequest): Promise<AnalyzeResponse> {
    const response = await this.aiService.analyze(body);
    return response;
  }

  @Get('history')
  @UseGuards(JwtAuthGuard)
  async history(@Query('limit') limit?: string): Promise<AiAnalysis[]> {
    const parsed = limit ? parseInt(limit, 10) : 20;
    return this.aiService.listHistory(Number.isNaN(parsed) ? 20 : parsed);
  }

  @Get('models')
  @UseGuards(JwtAuthGuard)
  async models() {
    return this.aiService.listModels();
  }
}
