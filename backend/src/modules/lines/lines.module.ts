import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Line } from '../database/entities/line.entity';
import { LinesController } from './lines.controller';
import { LinesService } from './lines.service';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Line]), JwtModule.register({})],
  controllers: [LinesController],
  providers: [LinesService, TenantContext],
  exports: [LinesService],
})
export class LinesModule {}
