import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';
import { JwtService } from '@nestjs/jwt';
import { TenantContext } from '../context/tenant-context';

@Injectable()
export class TenantMiddleware implements NestMiddleware {
  constructor(private readonly jwtService: JwtService) {}

  use(req: Request, res: Response, next: NextFunction) {
    let companyId: number | undefined;

    // 1. Tentar extrair do Token no Cookie ou Header Authorization
    let token = req.cookies?.['access_token'];
    if (!token && req.headers.authorization) {
      const [type, authToken] = req.headers.authorization.split(' ');
      if (type === 'Bearer') {
        token = authToken;
      }
    }

    if (token) {
      try {
        // verify() valida a assinatura — decode() não valida e permitiria forjar companyId
        const secret = process.env.JWT_SECRET;
        const payload = secret
          ? this.jwtService.verify(token, { secret })
          : null;
        if (payload && payload.companyId) {
          companyId = payload.companyId;
        }
      } catch {
        // Token inválido/expirado — JwtAuthGuard rejeitará na camada de autorização
      }
    }

    // 3. Bypass dev: SOMENTE quando NODE_ENV=development, request veio de loopback (localhost)
    //    e variável ALLOW_DEV_TENANT_FALLBACK=true. Reduz risco de bypass acidental
    //    se ambiente de dev for exposto na rede ou via reverse proxy mal configurado.
    if (
      !companyId &&
      process.env.NODE_ENV === 'development' &&
      process.env.ALLOW_DEV_TENANT_FALLBACK === 'true'
    ) {
      const ip = req.ip || (req.socket && req.socket.remoteAddress) || '';
      const isLoopback =
        ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1';
      if (isLoopback) {
        companyId = 1;
      }
    }

    if (companyId) {
      TenantContext.run({ companyId }, () => next());
    } else {
      next();
    }
  }
}
