import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Migration inicial — cria todas as tabelas core do OTIMIZ.
 *
 * Padrão: IF NOT EXISTS em todas as criações para ser idempotente.
 * Ordem respeitando dependências de FK:
 *   companies → terminals, vehicle_types, lines, drivers, trips, users, company_parameters
 *   vehicles → (vehicle_types, terminals)
 *   schedules → (companies)
 *   block_assignments → (schedules, vehicles)
 *   duty_assignments → (schedules)
 *   vehicle_maintenance, vehicle_availability_windows → (vehicles)
 *   audit_logs (standalone)
 */
export class CreateCoreTables1700000000000 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    // ── Enums ────────────────────────────────────────────────────────────────
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE user_role_enum AS ENUM ('super_admin','company_admin','analyst','operator');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE schedule_status_enum AS ENUM ('processing','completed','failed');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE maintenance_type_enum AS ENUM ('preventive','corrective','inspection');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE maintenance_status_enum AS ENUM ('scheduled','in_progress','completed','cancelled');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE availability_reason_enum AS ENUM ('maintenance','inspection','fuel','cleaning','repair','other');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await queryRunner.query(`
      DO $$ BEGIN
        CREATE TYPE audit_action_enum AS ENUM ('CREATE','UPDATE','DELETE');
      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);

    // ── companies ─────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "companies" (
        "id"          SERIAL PRIMARY KEY,
        "createdAt"   TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"   TIMESTAMP NOT NULL DEFAULT now(),
        "name"        VARCHAR NOT NULL UNIQUE,
        "slug"        VARCHAR NOT NULL UNIQUE,
        "tradeName"   VARCHAR,
        "cnpj"        VARCHAR UNIQUE,
        "phone"       VARCHAR,
        "address"     VARCHAR,
        "city"        VARCHAR,
        "state"       VARCHAR,
        "isActive"    BOOLEAN NOT NULL DEFAULT true
      );
    `);

    // ── users ─────────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "users" (
        "id"           SERIAL PRIMARY KEY,
        "createdAt"    TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"    TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"    INTEGER NOT NULL,
        "email"        VARCHAR NOT NULL UNIQUE,
        "passwordHash" VARCHAR NOT NULL,
        "name"         VARCHAR NOT NULL,
        "role"         user_role_enum NOT NULL DEFAULT 'operator',
        "isActive"     BOOLEAN NOT NULL DEFAULT true,
        "lastLoginAt"  TIMESTAMP
      );
    `);

    // ── terminals ─────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "terminals" (
        "id"         SERIAL PRIMARY KEY,
        "createdAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"  INTEGER NOT NULL,
        "terminalId" VARCHAR NOT NULL,
        "name"       VARCHAR NOT NULL,
        "city"       VARCHAR,
        "latitude"   DOUBLE PRECISION,
        "longitude"  DOUBLE PRECISION
      );
    `);

    // ── vehicle_types ─────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "vehicle_types" (
        "id"          SERIAL PRIMARY KEY,
        "createdAt"   TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"   TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"   INTEGER NOT NULL,
        "name"        VARCHAR NOT NULL,
        "capacity"    INTEGER NOT NULL,
        "costPerDay"  DOUBLE PRECISION NOT NULL,
        "accessible"  BOOLEAN NOT NULL DEFAULT false,
        "description" TEXT,
        "metadata"    JSONB
      );
    `);

    // ── vehicles ──────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "vehicles" (
        "id"                  SERIAL PRIMARY KEY,
        "createdAt"           TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"           TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"           INTEGER NOT NULL,
        "vehicleId"           VARCHAR NOT NULL,
        "typeId"              INTEGER NOT NULL REFERENCES "vehicle_types"("id") ON DELETE RESTRICT,
        "depotId"             INTEGER NOT NULL REFERENCES "terminals"("id") ON DELETE RESTRICT,
        "isActive"            BOOLEAN NOT NULL DEFAULT true,
        "licensePlate"        TEXT,
        "odometer"            DOUBLE PRECISION,
        "lastMaintenanceDate" TIMESTAMP,
        "metadata"            JSONB
      );
    `);

    // ── lines ─────────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "lines" (
        "id"                       SERIAL PRIMARY KEY,
        "createdAt"                TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"                TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"                INTEGER NOT NULL,
        "lineId"                   VARCHAR NOT NULL,
        "name"                     VARCHAR NOT NULL,
        "description"              VARCHAR,
        "isActive"                 BOOLEAN NOT NULL DEFAULT true,
        "originTerminalId"         INTEGER,
        "destinationTerminalId"    INTEGER,
        "distanceKm"               DOUBLE PRECISION,
        "returnDistanceKm"         DOUBLE PRECISION,
        "avgTripDurationMinutes"   INTEGER,
        "avgReturnDurationMinutes" INTEGER,
        "garageTerminalId"         INTEGER,
        "garageDistanceKm"         DOUBLE PRECISION,
        "solturaMinutes"           INTEGER,
        "recolhimentoDistanceKm"   DOUBLE PRECISION,
        "recolhimentoMinutes"      INTEGER
      );
    `);

    // ── drivers ───────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "drivers" (
        "id"             SERIAL PRIMARY KEY,
        "createdAt"      TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"      TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"      INTEGER NOT NULL,
        "driverId"       VARCHAR NOT NULL,
        "name"           VARCHAR NOT NULL,
        "role"           VARCHAR,
        "maxHoursPerDay" INTEGER NOT NULL DEFAULT 480,
        "lastShiftEnd"   INTEGER NOT NULL DEFAULT 0,
        "metadata"       JSONB
      );
    `);

    // ── trips ─────────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "trips" (
        "id"                          SERIAL PRIMARY KEY,
        "createdAt"                   TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"                   TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"                   INTEGER NOT NULL,
        "tripId"                      INTEGER,
        "lineId"                      INTEGER,
        "lineCode"                    VARCHAR,
        "pairId"                      VARCHAR,
        "tripGroupId"                 INTEGER,
        "direction"                   VARCHAR,
        "startTime"                   INTEGER NOT NULL,
        "endTime"                     INTEGER NOT NULL,
        "originId"                    INTEGER NOT NULL,
        "destinationId"               INTEGER NOT NULL,
        "distanceKm"                  DOUBLE PRECISION NOT NULL DEFAULT 0,
        "duration"                    INTEGER NOT NULL DEFAULT 0,
        "originLatitude"              DOUBLE PRECISION,
        "originLongitude"             DOUBLE PRECISION,
        "destinationLatitude"         DOUBLE PRECISION,
        "destinationLongitude"        DOUBLE PRECISION,
        "reliefPointId"               INTEGER,
        "isReliefPoint"               BOOLEAN NOT NULL DEFAULT false,
        "midTripReliefPointId"        INTEGER,
        "midTripReliefOffsetMinutes"  INTEGER,
        "midTripReliefDistanceRatio"  DOUBLE PRECISION,
        "midTripReliefElevationRatio" DOUBLE PRECISION
      );
    `);

    // ── schedules ─────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "schedules" (
        "id"            SERIAL PRIMARY KEY,
        "createdAt"     TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"     TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"     INTEGER NOT NULL,
        "referenceDate" TIMESTAMP NOT NULL DEFAULT now(),
        "status"        schedule_status_enum NOT NULL DEFAULT 'processing',
        "metadata"      JSONB,
        "totalCost"     DOUBLE PRECISION,
        "cctViolations" INTEGER NOT NULL DEFAULT 0
      );
    `);

    // ── block_assignments ─────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "block_assignments" (
        "id"         SERIAL PRIMARY KEY,
        "createdAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"  INTEGER NOT NULL,
        "scheduleId" INTEGER NOT NULL REFERENCES "schedules"("id") ON DELETE CASCADE,
        "vehicleId"  INTEGER REFERENCES "vehicles"("id") ON DELETE SET NULL,
        "blockId"    INTEGER NOT NULL,
        "tripIds"    INTEGER[] NOT NULL,
        "cost"       DOUBLE PRECISION NOT NULL DEFAULT 0,
        "metadata"   JSONB
      );
    `);

    // ── duty_assignments ──────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "duty_assignments" (
        "id"         SERIAL PRIMARY KEY,
        "createdAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"  TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"  INTEGER NOT NULL,
        "scheduleId" INTEGER NOT NULL REFERENCES "schedules"("id") ON DELETE CASCADE,
        "dutyId"     INTEGER NOT NULL,
        "tripIds"    INTEGER[] NOT NULL,
        "cost"       DOUBLE PRECISION NOT NULL DEFAULT 0,
        "metadata"   JSONB
      );
    `);

    // ── vehicle_maintenance ───────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "vehicle_maintenance" (
        "id"                      SERIAL PRIMARY KEY,
        "createdAt"               TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"               TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"               INTEGER NOT NULL,
        "vehicleId"               INTEGER NOT NULL REFERENCES "vehicles"("id") ON DELETE CASCADE,
        "maintenanceDate"         DATE NOT NULL,
        "maintenanceType"         maintenance_type_enum NOT NULL DEFAULT 'preventive',
        "estimatedDurationHours"  INTEGER NOT NULL,
        "cost"                    DECIMAL(10,2) NOT NULL DEFAULT 0,
        "status"                  maintenance_status_enum NOT NULL DEFAULT 'scheduled',
        "description"             VARCHAR,
        "notes"                   VARCHAR
      );
    `);

    // ── vehicle_availability_windows ──────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "vehicle_availability_windows" (
        "id"               SERIAL PRIMARY KEY,
        "createdAt"        TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"        TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"        INTEGER NOT NULL,
        "vehicleId"        INTEGER NOT NULL REFERENCES "vehicles"("id") ON DELETE CASCADE,
        "startTime"        TIMESTAMP NOT NULL,
        "endTime"          TIMESTAMP NOT NULL,
        "reason"           availability_reason_enum NOT NULL DEFAULT 'other',
        "description"      VARCHAR,
        "isRecurring"      BOOLEAN NOT NULL DEFAULT false,
        "recurringPattern" VARCHAR
      );
    `);

    // ── audit_logs ────────────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "audit_logs" (
        "id"        SERIAL PRIMARY KEY,
        "userId"    INTEGER,
        "companyId" INTEGER,
        "action"    audit_action_enum NOT NULL,
        "entity"    VARCHAR NOT NULL,
        "entityId"  VARCHAR,
        "payload"   JSONB,
        "userEmail" VARCHAR,
        "createdAt" TIMESTAMP NOT NULL DEFAULT now()
      );
    `);
    await queryRunner.query(`CREATE INDEX IF NOT EXISTS "IDX_audit_logs_company_created" ON "audit_logs" ("companyId", "createdAt");`);
    await queryRunner.query(`CREATE INDEX IF NOT EXISTS "IDX_audit_logs_entity" ON "audit_logs" ("entity", "entityId");`);

    // ── company_parameters ────────────────────────────────────────────────────
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "company_parameters" (
        "id"                              SERIAL PRIMARY KEY,
        "createdAt"                       TIMESTAMP NOT NULL DEFAULT now(),
        "updatedAt"                       TIMESTAMP NOT NULL DEFAULT now(),
        "companyId"                       INTEGER NOT NULL,
        "driver_cost_per_minute"          DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        "collector_cost_per_minute"       DOUBLE PRECISION NOT NULL DEFAULT 0.4,
        "vehicle_fixed_cost"              DOUBLE PRECISION NOT NULL DEFAULT 800.0,
        "cost_vehicle"                    DOUBLE PRECISION NOT NULL DEFAULT 1000.0,
        "cost_km"                         DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        "cost_duty"                       DOUBLE PRECISION NOT NULL DEFAULT 500.0,
        "cct_violation_penalty"           DOUBLE PRECISION NOT NULL DEFAULT 500.0,
        "force_round_trip"                BOOLEAN NOT NULL DEFAULT true,
        "allow_vehicle_swap"              BOOLEAN NOT NULL DEFAULT false,
        "max_driving_time_minutes"        INTEGER NOT NULL DEFAULT 480,
        "meal_break_minutes"              INTEGER NOT NULL DEFAULT 60,
        "max_shift_minutes"               INTEGER NOT NULL DEFAULT 720,
        "max_work_minutes"                INTEGER,
        "min_work_minutes"                INTEGER,
        "min_shift_minutes"               INTEGER,
        "overtime_limit_minutes"          INTEGER,
        "max_driving_minutes"             INTEGER,
        "min_break_minutes"               INTEGER,
        "enforce_min_interval"            BOOLEAN NOT NULL DEFAULT true,
        "connection_tolerance_minutes"    INTEGER,
        "mandatory_break_after_minutes"   INTEGER,
        "split_break_first_minutes"       INTEGER,
        "split_break_second_minutes"      INTEGER,
        "inter_shift_rest_minutes"        INTEGER,
        "weekly_rest_minutes"             INTEGER,
        "reduced_weekly_rest_minutes"     INTEGER,
        "allow_reduced_weekly_rest"       BOOLEAN,
        "daily_driving_limit_minutes"     INTEGER,
        "extended_daily_driving_limit_minutes" INTEGER,
        "max_extended_driving_days_per_week"   INTEGER,
        "weekly_driving_limit_minutes"    INTEGER,
        "fortnight_driving_limit_minutes" INTEGER,
        "min_layover_minutes"             INTEGER,
        "pullout_minutes"                 INTEGER,
        "pullback_minutes"                INTEGER,
        "pullout_counts_in_driver_shift"  BOOLEAN,
        "pullback_counts_in_driver_shift" BOOLEAN,
        "idle_time_is_paid"               BOOLEAN,
        "waiting_time_pay_pct"            DOUBLE PRECISION,
        "min_guaranteed_work_minutes"     INTEGER,
        "max_unpaid_break_minutes"        INTEGER,
        "max_total_unpaid_break_minutes"  INTEGER,
        "long_unpaid_break_limit_minutes" INTEGER,
        "long_unpaid_break_penalty_weight" DOUBLE PRECISION,
        "allow_relief_points"             BOOLEAN NOT NULL DEFAULT false,
        "enforce_same_depot_start_end"    BOOLEAN NOT NULL DEFAULT false,
        "fairness_weight"                 DOUBLE PRECISION,
        "fairness_target_work_minutes"    INTEGER,
        "fairness_tolerance_minutes"      INTEGER,
        "operator_change_terminals_only"  BOOLEAN,
        "enforce_trip_groups_hard"        BOOLEAN NOT NULL DEFAULT true,
        "operator_pairing_hard"           BOOLEAN NOT NULL DEFAULT true,
        "trip_group_keep_bonus"           DOUBLE PRECISION NOT NULL DEFAULT 240.0,
        "sunday_off_weight"               DOUBLE PRECISION,
        "holiday_extra_pct"               DOUBLE PRECISION,
        "enforce_single_line_duty"        BOOLEAN NOT NULL DEFAULT false,
        "operator_single_vehicle_only"    BOOLEAN NOT NULL DEFAULT true,
        "nocturnal_start_hour"            INTEGER,
        "nocturnal_end_hour"              INTEGER,
        "nocturnal_factor"                DOUBLE PRECISION,
        "nocturnal_extra_pct"             DOUBLE PRECISION,
        "apply_cct"                       BOOLEAN,
        "strict_hard_validation"          BOOLEAN,
        "strict_zero_gap_validation"      BOOLEAN,
        "strict_operational_mode"         BOOLEAN,
        "strict_hard_constraints"         BOOLEAN,
        "strict_gps_validation"           BOOLEAN,
        "strict_terminal_sync_validation" BOOLEAN,
        "strict_union_rules"              BOOLEAN,
        "group_infeasibility_mode"        VARCHAR DEFAULT 'strict',
        "operational_quality_mode"        VARCHAR DEFAULT 'balanced',
        "terminal_location_ids"           INTEGER[] NOT NULL DEFAULT '{}',
        "time_budget_s"                   DOUBLE PRECISION,
        "random_seed"                     INTEGER,
        "max_vehicle_shift_minutes"       INTEGER,
        "max_vehicles"                    INTEGER,
        "deadhead_cost_per_minute"        DOUBLE PRECISION,
        "idle_cost_per_minute"            DOUBLE PRECISION,
        "allow_multi_line_block"          BOOLEAN,
        "allow_vehicle_split_shifts"      BOOLEAN,
        "split_shift_min_gap_minutes"     INTEGER,
        "split_shift_max_gap_minutes"     INTEGER,
        "max_simultaneous_chargers"       INTEGER,
        "enable_column_generation"        BOOLEAN,
        "pricing_enabled"                 BOOLEAN,
        "use_set_covering"                BOOLEAN,
        "min_workpiece_minutes"           INTEGER,
        "max_workpiece_minutes"           INTEGER,
        "min_trips_per_piece"             INTEGER,
        "max_trips_per_piece"             INTEGER,
        "peak_energy_cost_per_kwh"        DOUBLE PRECISION,
        "offpeak_energy_cost_per_kwh"     DOUBLE PRECISION,
        "preferred_pair_window_minutes"   INTEGER,
        "preserve_preferred_pairs"        BOOLEAN,
        "pair_break_penalty"              DOUBLE PRECISION,
        "paired_trip_bonus"               DOUBLE PRECISION,
        "max_connection_cost_for_reuse_ratio"  DOUBLE PRECISION,
        "max_candidate_successors_per_task"    INTEGER,
        "max_generated_columns"           INTEGER,
        "max_pricing_iterations"          INTEGER,
        "max_pricing_additions"           INTEGER,
        "vehicle_idle_gap_behavior"       VARCHAR DEFAULT 'solver_decides',
        "vehicle_idle_gap_threshold_minutes" INTEGER,
        "algorithm_preference"            VARCHAR NOT NULL DEFAULT 'hybrid_pipeline',
        "ilp_timeout_seconds"             INTEGER NOT NULL DEFAULT 120,
        "goal_weights"                    JSONB,
        "dynamic_rules"                   JSONB
      );
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP TABLE IF EXISTS "company_parameters" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "audit_logs" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "vehicle_availability_windows" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "vehicle_maintenance" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "duty_assignments" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "block_assignments" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "schedules" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "trips" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "drivers" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "lines" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "vehicles" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "vehicle_types" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "terminals" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "users" CASCADE;`);
    await queryRunner.query(`DROP TABLE IF EXISTS "companies" CASCADE;`);
    await queryRunner.query(`DROP TYPE IF EXISTS "audit_action_enum";`);
    await queryRunner.query(`DROP TYPE IF EXISTS "availability_reason_enum";`);
    await queryRunner.query(`DROP TYPE IF EXISTS "maintenance_status_enum";`);
    await queryRunner.query(`DROP TYPE IF EXISTS "maintenance_type_enum";`);
    await queryRunner.query(`DROP TYPE IF EXISTS "schedule_status_enum";`);
    await queryRunner.query(`DROP TYPE IF EXISTS "user_role_enum";`);
  }
}
