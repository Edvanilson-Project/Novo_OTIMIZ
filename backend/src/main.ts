// Polyfill global Web Crypto API in Node when missing (some libs call `crypto.randomUUID()`)
import { webcrypto } from 'crypto';
if (typeof (globalThis as any).crypto === 'undefined') {
  (globalThis as any).crypto = webcrypto;
}

// Sentry must be initialized before any other module
import { initSentry } from './common/telemetry/sentry.setup';
initSentry();

import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import cookieParser from 'cookie-parser';
import helmet from 'helmet';
import { AppModule } from './app.module';
import type { Response } from 'express';

const WEAK_JWT_DEFAULTS = new Set([
  'otimiz-dev-jwt-secret-change-in-production',
  'your_jwt_secret_here_min_32_chars',
  '',
]);

function assertProductionSecrets(): void {
  if (process.env.NODE_ENV !== 'production') return;
  const jwtSecret = process.env.JWT_SECRET ?? '';
  if (WEAK_JWT_DEFAULTS.has(jwtSecret) || jwtSecret.length < 32) {
    console.error(
      'FATAL: JWT_SECRET is missing or too weak for production. Set a random string ≥32 chars.',
    );
    process.exit(1);
  }
  const internalKey = process.env.INTERNAL_OPTIMIZER_KEY ?? '';
  if (!internalKey || internalKey === 'internal-key-123456') {
    console.error(
      'FATAL: INTERNAL_OPTIMIZER_KEY is missing or using default value in production.',
    );
    process.exit(1);
  }
}

async function bootstrap() {
  assertProductionSecrets();
  const app = await NestFactory.create(AppModule);

  // Security headers via Helmet
  app.use(
    helmet({
      // CSP permissivo o suficiente para o Swagger UI em dev (fontawesome, CDN swagger)
      contentSecurityPolicy:
        process.env.NODE_ENV === 'production'
          ? undefined // helmet default estrito em produção
          : false, // desabilitado em dev para não bloquear Swagger UI
      crossOriginEmbedderPolicy: false, // WebSocket do Socket.IO requer isso
    }),
  );

  // Configuração de Pipes globais para validação de DTOs
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  // Habilitar Cookie Parser para ler tokens HTTP-Only
  app.use(cookieParser());

  // CORS: combinar `origin: true` (refletir Origin) com `credentials: true` permite que qualquer
  // site exfiltre cookies/headers autenticados. Lemos a allowlist da env CORS_ALLOWED_ORIGINS
  // (separada por vírgula). Em dev, default permissivo para localhost:3000.
  const allowedOrigins = (
    process.env.CORS_ALLOWED_ORIGINS || 'http://localhost:3000'
  )
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);
  app.enableCors({
    origin: allowedOrigins,
    credentials: true,
  });

  app.setGlobalPrefix('api/v1');

  // Swagger — acessível em /api/v1/docs (apenas fora de produção)
  if (process.env.NODE_ENV !== 'production') {
    const config = new DocumentBuilder()
      .setTitle('OTIMIZ API')
      .setDescription(
        'API de otimização operacional de transporte coletivo urbano',
      )
      .setVersion('2.0')
      .addBearerAuth(
        { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' },
        'JWT',
      )
      .addTag('auth', 'Autenticação e sessão')
      .addTag('operations', 'Planejamento e otimização de escalas')
      .addTag('reporting', 'Relatórios e análises operacionais')
      .addTag('reports', 'KPIs e histórico de otimização')
      .addTag('vehicles', 'Frota e manutenção de veículos')
      .addTag('lines', 'Linhas e terminais')
      .addTag('parameters', 'Parâmetros da empresa')
      .addTag('users', 'Gestão de usuários')
      .addTag('gtfs', 'Importação GTFS')
      .build();
    const document = SwaggerModule.createDocument(app, config);
    SwaggerModule.setup('api/v1/docs', app, document, {
      swaggerOptions: { persistAuthorization: true },
    });
    console.log(
      `Swagger docs: http://localhost:${process.env.PORT || 3001}/api/v1/docs`,
    );
  }

  const port = process.env.PORT || 3001;
  await app.listen(port);
  console.log(`Application is running on: http://localhost:${port}`);
}
void bootstrap();
