import { Module, Global } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { JwtModule } from '@nestjs/jwt';
import { AuditLog } from '../database/entities/audit-log.entity';
import { AuditService } from './audit.service';
import { AuditController } from './audit.controller';
import { TenantContext } from '../../common/context/tenant-context';

@Global()
@Module({
  imports: [TypeOrmModule.forFeature([AuditLog]), JwtModule.register({})],
  controllers: [AuditController],
  providers: [AuditService, TenantContext],
  exports: [AuditService],
})
export class AuditModule {}
