// Polyfill global Web Crypto API in Node when missing (some libs call `crypto.randomUUID()`)
import { webcrypto } from 'crypto';
if (typeof (globalThis as any).crypto === 'undefined') {
  (globalThis as any).crypto = webcrypto;
}

import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
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

  const port = process.env.PORT || 3001;
  await app.listen(port);
  console.log(`Application is running on: http://localhost:${port}`);
}
bootstrap();
