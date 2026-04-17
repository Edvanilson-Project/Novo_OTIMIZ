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
        const payload = this.jwtService.decode(token) as any;
        if (payload && payload.companyId) {
          companyId = payload.companyId;
        }
      } catch (err) {
        // Token inválido, mas o middleware segue para que o AuthGuard trate as permissões
      }
    }

    // 2. Fallback para Header (Útil para testes de integração e dev tools)
    if (!companyId) {
      const companyIdStr = req.headers['x-company-id'] as string;
      companyId = companyIdStr ? parseInt(companyIdStr, 10) : undefined;
    }

    // 3. Bypass de Desenvolvedor: injeta companyId=1 quando NODE_ENV=development e não há token
    if (!companyId && process.env.NODE_ENV === 'development') {
      companyId = 1;
    }

    if (companyId) {
      TenantContext.run({ companyId }, () => next());
    } else {
      next();
    }
  }
}
