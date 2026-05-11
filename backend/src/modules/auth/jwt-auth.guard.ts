import { Injectable, CanActivate, ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { Reflector } from '@nestjs/core';

@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(
    private jwtService: JwtService,
    private reflector: Reflector,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const isPublic = this.reflector.getAllAndOverride<boolean>('isPublic', [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;

    const request = context.switchToHttp().getRequest();
    const token = this.extractTokenFromHeader(request) || request.cookies?.['access_token'];

    if (!token) throw new UnauthorizedException('Token não fornecido');

    const secret = process.env.JWT_SECRET;
    if (!secret) {
      // Fail-loud: nunca aceitamos requisições sem segredo configurado.
      // O fallback antigo ('fallback_dev_only') aceitava tokens forjados em ambientes mal configurados.
      throw new UnauthorizedException('Servidor sem JWT_SECRET configurado.');
    }
    try {
      const payload = await this.jwtService.verifyAsync(token, { secret });
      request['user'] = payload;
    } catch {
      throw new UnauthorizedException('Token inválido ou expirado');
    }
    return true;
  }

  private extractTokenFromHeader(request: any): string | undefined {
    const [type, token] = request.headers.authorization?.split(' ') ?? [];
    return type === 'Bearer' ? token : undefined;
  }
}
