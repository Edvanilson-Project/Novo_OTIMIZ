import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { BaseRepository } from '../../../common/repositories/base.repository';
import { CompanyParameters } from '../entities/company-parameters.entity';

@Injectable()
export class CompanyParametersRepository extends BaseRepository<CompanyParameters> {
  constructor(private dataSource: DataSource) {
    super(CompanyParameters, dataSource.createEntityManager());
  }
}
