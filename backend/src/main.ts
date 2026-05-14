// Polyfill global Web Crypto API in Node when missing (some libs call `crypto.randomUUID()`)
import { webcrypto } from 'crypto';
if (typeof (globalThis as any).crypto === 'undefined') {
  (globalThis as any).crypto = webcrypto;
}

import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import cookieParser from 'cookie-parser';
import { AppModule } from './app.module';
import type { Response } from 'express';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Configuração de Pipes globais para validação de DTOs
  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
  }));

  // Habilitar Cookie Parser para ler tokens HTTP-Only
  app.use(cookieParser());

  // CORS: combinar `origin: true` (refletir Origin) com `credentials: true` permite que qualquer
  // site exfiltre cookies/headers autenticados. Lemos a allowlist da env CORS_ALLOWED_ORIGINS
  // (separada por vírgula). Em dev, default permissivo para localhost:3000.
  const allowedOrigins = (process.env.CORS_ALLOWED_ORIGINS || 'http://localhost:3000')
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
      .setDescription('API de otimização operacional de transporte coletivo urbano')
      .setVersion('2.0')
      .addBearerAuth({ type: 'http', scheme: 'bearer', bearerFormat: 'JWT' }, 'JWT')
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
    console.log(`Swagger docs: http://localhost:${process.env.PORT || 3001}/api/v1/docs`);
  }

  const port = process.env.PORT || 3001;
  await app.listen(port);
  console.log(`Application is running on: http://localhost:${port}`);
}
bootstrap();
