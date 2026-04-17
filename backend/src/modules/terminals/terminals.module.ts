import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Terminal } from '../database/entities/terminal.entity';
import { TerminalsController } from './terminals.controller';
import { TerminalsService } from './terminals.service';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from '../../common/context/tenant-context';

@Module({
  imports: [TypeOrmModule.forFeature([Terminal]), JwtModule.register({})],
  controllers: [TerminalsController],
  providers: [TerminalsService, TenantContext],
  exports: [TerminalsService],
})
export class TerminalsModule {}
