import { Module, MiddlewareConsumer, NestModule, RequestMethod } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { APP_FILTER, APP_GUARD, APP_INTERCEPTOR } from '@nestjs/core';
import { RolesGuard } from './common/guards/roles.guard';
import { JwtAuthGuard } from './modules/auth/jwt-auth.guard';
import { AuditModule } from './modules/audit/audit.module';
import { AuditInterceptor } from './modules/audit/audit.interceptor';
import { AuditLog } from './modules/database/entities/audit-log.entity';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { TenantMiddleware } from './common/middleware/tenant.middleware';
import { GlobalExceptionFilter } from './common/filters/http-exception.filter';
import { Company } from './modules/database/entities/company.entity';
import { User } from './modules/database/entities/user.entity';
import { CompanyParameters } from './modules/database/entities/company-parameters.entity';
import { ParametersModule } from './modules/parameters/parameters.module';
import { AuthModule } from './modules/auth/auth.module';
import { JwtModule } from '@nestjs/jwt';
import { TenantContext } from './common/context/tenant-context';
import { UserRepository } from './modules/database/repositories/user.repository';
import { Trip } from './modules/database/entities/trip.entity';
import { Driver } from './modules/database/entities/driver.entity';
import { Schedule } from './modules/database/entities/schedule.entity';
import { BlockAssignment } from './modules/database/entities/block-assignment.entity';
import { DutyAssignment } from './modules/database/entities/duty-assignment.entity';
import { OperationsModule } from './modules/operations/operations.module';
import { CompaniesModule } from './modules/companies/companies.module';
import { UsersModule } from './modules/users/users.module';
import { LinesModule } from './modules/lines/lines.module';
import { TerminalsModule } from './modules/terminals/terminals.module';
import { ReportsModule } from './modules/reports/reports.module';
import { Line } from './modules/database/entities/line.entity';
import { Terminal } from './modules/database/entities/terminal.entity';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        type: 'postgres',
        host: configService.get<string>('DB_HOST'),
        port: configService.get<number>('DB_PORT'),
        username: configService.get<string>('DB_USER'),
        password: configService.get<string>('DB_PASSWORD'),
        database: configService.get<string>('DB_NAME'),
        entities: [Company, User, CompanyParameters, Trip, Driver, Schedule, BlockAssignment, DutyAssignment, Line, Terminal, AuditLog],
        synchronize: true, 
        logging: false,
      }),
    }),
    TypeOrmModule.forFeature([Company, User, CompanyParameters, Trip, Driver, Schedule, BlockAssignment, DutyAssignment, Line, Terminal]),
    AuthModule,
    ParametersModule,
    OperationsModule,
    CompaniesModule,
    UsersModule,
    LinesModule,
    TerminalsModule,
    ReportsModule,
    AuditModule,
    JwtModule.register({}),
],
  controllers: [AppController],
  providers: [
    AppService,
    TenantContext,
    UserRepository,
    {
      provide: APP_FILTER,
      useClass: GlobalExceptionFilter,
    },
    {
      provide: APP_GUARD,
      useClass: JwtAuthGuard,
    },
    {
      provide: APP_GUARD,
      useClass: RolesGuard,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: AuditInterceptor,
    },
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer
      .apply(TenantMiddleware)
      .forRoutes({ path: '*', method: RequestMethod.ALL });
  }
}
