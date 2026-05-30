import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { BaseRepository } from '../../../common/repositories/base.repository';
import { AiAnalysis } from '../entities/ai-analysis.entity';

@Injectable()
export class AiAnalysisRepository extends BaseRepository<AiAnalysis> {
  constructor(private dataSource: DataSource) {
    super(AiAnalysis, dataSource.createEntityManager());
  }
}
