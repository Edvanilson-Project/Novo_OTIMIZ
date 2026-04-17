import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { ParametersController } from './parameters.controller';
import { ParametersService } from './parameters.service';
import { CompanyParametersRepository } from '../database/repositories/company-parameters.repository';
import { CompanyParameters } from '../database/entities/company-parameters.entity';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [
    TypeOrmModule.forFeature([CompanyParameters]),
    JwtModule.register({}), // Re-utiliza a config global se disponível
  ],
  controllers: [ParametersController],
  providers: [
    ParametersService,
    CompanyParametersRepository,
    TenantContext,
  ],
  exports: [ParametersService],
})
export class ParametersModule {}
