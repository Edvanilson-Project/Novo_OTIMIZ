import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Company } from '../database/entities/company.entity';
import { CompaniesController } from './companies.controller';
import { CompaniesService } from './companies.service';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Company]), JwtModule.register({})],
  controllers: [CompaniesController],
  providers: [CompaniesService, TenantContext],
  exports: [CompaniesService],
})
export class CompaniesModule {}
