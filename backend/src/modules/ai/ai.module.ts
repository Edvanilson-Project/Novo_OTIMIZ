import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { AiController } from './ai.controller';
import { AiService } from './ai.service';
import { AiAnalysis } from '../database/entities/ai-analysis.entity';
import { AiAnalysisRepository } from '../database/repositories/ai-analysis.repository';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    TypeOrmModule.forFeature([AiAnalysis]),
    JwtModule.register({}),
  ],
  controllers: [AiController],
  providers: [AiService, AiAnalysisRepository, TenantContext],
  exports: [AiService],
})
export class AiModule {}
