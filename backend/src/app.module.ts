import {
  Module,
  MiddlewareConsumer,
  NestModule,
  RequestMethod,
} from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { APP_FILTER, APP_GUARD, APP_INTERCEPTOR } from '@nestjs/core';
import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';
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
import { CustomReportsModule } from './modules/custom-reports/custom-reports.module';
import { GtfsModule } from './modules/gtfs/gtfs.module';
import { VehiclesModule } from './modules/vehicles/vehicles.module';
import { Line } from './modules/database/entities/line.entity';
import { Terminal } from './modules/database/entities/terminal.entity';
import { VehicleType } from './modules/database/entities/vehicle-type.entity';
import { Vehicle } from './modules/database/entities/vehicle.entity';
import { VehicleMaintenance } from './modules/database/entities/vehicle-maintenance.entity';
import { VehicleAvailabilityWindow } from './modules/database/entities/vehicle-availability-window.entity';
import { OptimizationRun } from './modules/database/entities/optimization-run.entity';
import { CustomReport } from './modules/database/entities/custom-report.entity';

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
        entities: [
          Company,
          User,
          CompanyParameters,
          Trip,
          Driver,
          Schedule,
          BlockAssignment,
          DutyAssignment,
          Line,
          Terminal,
          AuditLog,
          VehicleType,
          Vehicle,
          VehicleMaintenance,
          VehicleAvailabilityWindow,
          OptimizationRun,
          CustomReport,
        ],
        // synchronize=true permite TypeORM dropar/alterar colunas a partir das entities. Em produção
        // isso pode causar perda silenciosa de dados em deploy. Mantemos auto-sync apenas em dev.
        synchronize: configService.get<string>('NODE_ENV') !== 'production',
        // Migrations explícitas: glob aceita .ts (dev) e .js (após build).
        migrations: [__dirname + '/modules/database/migrations/*{.ts,.js}'],
        // Auto-aplicar migrations pendentes ao subir. Idempotente — só roda as que faltam.
        migrationsRun: true,
        logging: false,
      }),
    }),
    TypeOrmModule.forFeature([
      Company,
      User,
      CompanyParameters,
      Trip,
      Driver,
      Schedule,
      BlockAssignment,
      DutyAssignment,
      Line,
      Terminal,
      VehicleType,
      Vehicle,
      VehicleMaintenance,
      VehicleAvailabilityWindow,
      OptimizationRun,
      CustomReport,
    ]),
    AuthModule,
    ParametersModule,
    OperationsModule,
    CompaniesModule,
    UsersModule,
    LinesModule,
    TerminalsModule,
    VehiclesModule,
    ReportsModule,
    CustomReportsModule,
    AuditModule,
    GtfsModule,
    JwtModule.register({}),
    // Rate limiting global: protege contra brute-force (login) e DoS por requisição pesada
    // (/optimize). Throttles podem ser sobrescritos por endpoint via @Throttle decorator.
    ThrottlerModule.forRoot([
      { name: 'short', ttl: 1_000, limit: 30 }, // 30 req/s por IP — burst defense
      { name: 'medium', ttl: 60_000, limit: 300 }, // 300 req/min — uso normal
    ]),
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
      useClass: ThrottlerGuard,
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
      .forRoutes({ path: '*path', method: RequestMethod.ALL });
  }
}
