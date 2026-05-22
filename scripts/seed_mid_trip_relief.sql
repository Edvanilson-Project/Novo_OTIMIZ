-- Seed mid-trip relief data for company 16 (testing end-to-end)
-- Run: PGPASSWORD=$(grep -E "POSTGRES_PASSWORD|DB_PASSWORD" .env | head -1 | cut -d= -f2) \
--      psql -h localhost -p 5444 -U otimiz_admin -d otimiz_db -f scripts/seed_mid_trip_relief.sql

BEGIN;

-- 1. Habilita rendição mid-trip para empresa 16
UPDATE company_parameters
SET allow_relief_points = true
WHERE "companyId" = 16;

-- 2. Marca terminais 1, 2, 3 como pontos válidos de rendição (relief points)
--    (qualquer trip que tenha origin/destination em 1/2/3 pode ter relief)
UPDATE trips
SET "isReliefPoint" = true,
    "reliefPointId" = "originId"
WHERE "companyId" = 16
  AND "originId" IN (1, 2, 3);

-- 3. Para 8 viagens longas (>= 50 min), define ponto de rendição no MEIO
--    midTripReliefPointId = terminal intermediário (usamos 2 por simplicidade)
--    midTripReliefOffsetMinutes = duração/2 (motorista entrega no meio)
-- Usa terminal 3 como ponto intermediário (não pode ser origin nem destination da viagem)
UPDATE trips
SET "midTripReliefPointId" = 3,
    "midTripReliefOffsetMinutes" = duration / 2,
    "midTripReliefDistanceRatio" = 0.5,
    "midTripReliefElevationRatio" = 0.5
WHERE "companyId" = 16
  AND duration >= 50
  AND "originId" = 1
  AND "destinationId" = 2;

-- Verificação
SELECT
  (SELECT allow_relief_points FROM company_parameters WHERE "companyId"=16) AS flag_on,
  (SELECT COUNT(*) FROM trips WHERE "companyId"=16 AND "isReliefPoint" = true) AS trips_with_relief,
  (SELECT COUNT(*) FROM trips WHERE "companyId"=16 AND "midTripReliefPointId" IS NOT NULL) AS trips_mid_split;

COMMIT;
