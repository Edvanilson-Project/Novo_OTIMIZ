import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { AiController } from './ai.controller';
import { AiService } from './ai.service';
import { AiAnalysis } from '../database/entities/ai-analysis.entity';
import { AiAnalysisRepository } from '../database/repositories/ai-analysis.repository';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    HttpModule,
    TypeOrmModule.forFeature([AiAnalysis]),
    JwtModule.register({}), // Re-utiliza a config global se disponível
  ],
  controllers: [AiController],
  providers: [AiService, AiAnalysisRepository, TenantContext],
  exports: [AiService],
})
export class AiModule {}
