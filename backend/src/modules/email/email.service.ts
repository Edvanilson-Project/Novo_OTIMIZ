import { Injectable, Logger } from '@nestjs/common';
import * as nodemailer from 'nodemailer';
import type { Transporter } from 'nodemailer';

export interface SendMailOptions {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

/**
 * Thin wrapper over nodemailer.
 * Reads SMTP_* env vars. If not configured (dev), logs to stdout instead of sending.
 * Never throws — email failures are logged but don't break the request.
 */
@Injectable()
export class EmailService {
  private readonly logger = new Logger(EmailService.name);
  private readonly transporter: Transporter | null;
  private readonly fromAddress: string;

  constructor() {
    this.fromAddress =
      process.env.SMTP_FROM ?? 'OTIMIZ <noreply@otimiz.com.br>';

    if (process.env.SMTP_HOST) {
      this.transporter = nodemailer.createTransport({
        host: process.env.SMTP_HOST,
        port: Number(process.env.SMTP_PORT ?? 587),
        secure: process.env.SMTP_SECURE === 'true',
        auth: {
          user: process.env.SMTP_USER,
          pass: process.env.SMTP_PASS,
        },
      });
      this.logger.log(`Email transport configured via ${process.env.SMTP_HOST}`);
    } else {
      this.transporter = null;
      this.logger.warn(
        'SMTP_HOST not set — emails will be logged to stdout. Set SMTP_* env vars for production.',
      );
    }
  }

  async send(opts: SendMailOptions): Promise<void> {
    if (!this.transporter) {
      this.logger.log(
        `[DEV EMAIL] To: ${opts.to} | Subject: ${opts.subject}\n${opts.text ?? opts.html}`,
      );
      return;
    }

    try {
      await this.transporter.sendMail({
        from: this.fromAddress,
        to: opts.to,
        subject: opts.subject,
        html: opts.html,
        text: opts.text,
      });
      this.logger.log(`Email sent to ${opts.to}: ${opts.subject}`);
    } catch (err) {
      // Log but never crash the calling request
      this.logger.error(`Failed to send email to ${opts.to}: ${(err as Error).message}`);
    }
  }

  // ── Pre-built templates ──────────────────────────────────────────────────

  passwordReset(opts: { to: string; name: string; resetUrl: string; expiresInMinutes: number }): Promise<void> {
    return this.send({
      to: opts.to,
      subject: 'Redefinição de senha — OTIMIZ',
      text: `Olá ${opts.name},\n\nClique no link para redefinir sua senha (válido por ${opts.expiresInMinutes} minutos):\n${opts.resetUrl}\n\nSe você não solicitou isso, ignore este e-mail.`,
      html: `
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f4f4f5; margin:0; padding:40px 20px;">
  <div style="max-width:480px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:#0f172a; padding:32px 40px; text-align:center;">
      <h1 style="color:#fff; margin:0; font-size:22px; font-weight:600;">🚌 OTIMIZ</h1>
    </div>
    <div style="padding:40px;">
      <h2 style="color:#1e293b; font-size:18px; margin:0 0 16px;">Redefinição de senha</h2>
      <p style="color:#475569; line-height:1.6; margin:0 0 24px;">Olá ${opts.name}, recebemos uma solicitação para redefinir a senha da sua conta OTIMIZ.</p>
      <a href="${opts.resetUrl}" style="display:block; text-align:center; background:#16a34a; color:#fff; text-decoration:none; padding:14px 24px; border-radius:8px; font-weight:600; font-size:15px;">
        Redefinir minha senha
      </a>
      <p style="color:#94a3b8; font-size:13px; margin:24px 0 0; text-align:center;">
        Link válido por ${opts.expiresInMinutes} minutos.<br>
        Se você não solicitou isso, ignore este e-mail — sua senha permanece a mesma.
      </p>
    </div>
    <div style="background:#f8fafc; padding:16px 40px; text-align:center;">
      <p style="color:#94a3b8; font-size:12px; margin:0;">
        OTIMIZ · Sistema de otimização de transporte coletivo<br>
        Este é um e-mail automático. Não responda.
      </p>
    </div>
  </div>
</body>
</html>`,
    });
  }

  optimizationComplete(opts: {
    to: string;
    name: string;
    scheduleId: number;
    vehicles: number;
    cost: number;
    dashboardUrl: string;
  }): Promise<void> {
    return this.send({
      to: opts.to,
      subject: `Otimização concluída — ${opts.vehicles} veículos — OTIMIZ`,
      text: `Olá ${opts.name}, sua otimização foi concluída com sucesso!\n\nVeículos: ${opts.vehicles}\nCusto estimado: R$ ${opts.cost.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}\n\nVeja os resultados: ${opts.dashboardUrl}`,
      html: `
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f4f4f5; margin:0; padding:40px 20px;">
  <div style="max-width:480px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:#0f172a; padding:32px 40px; text-align:center;">
      <h1 style="color:#fff; margin:0; font-size:22px; font-weight:600;">🚌 OTIMIZ</h1>
    </div>
    <div style="padding:40px;">
      <h2 style="color:#1e293b; font-size:18px; margin:0 0 16px;">✅ Otimização concluída!</h2>
      <p style="color:#475569; line-height:1.6; margin:0 0 24px;">Olá ${opts.name}, sua escala foi otimizada com sucesso.</p>
      <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:20px; margin-bottom:24px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
          <span style="color:#166534; font-weight:600;">Veículos</span>
          <span style="color:#166534; font-weight:700;">${opts.vehicles}</span>
        </div>
        <div style="display:flex; justify-content:space-between;">
          <span style="color:#166534; font-weight:600;">Custo estimado</span>
          <span style="color:#166534; font-weight:700;">R$ ${opts.cost.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
        </div>
      </div>
      <a href="${opts.dashboardUrl}" style="display:block; text-align:center; background:#16a34a; color:#fff; text-decoration:none; padding:14px 24px; border-radius:8px; font-weight:600; font-size:15px;">
        Ver resultados no dashboard
      </a>
    </div>
  </div>
</body>
</html>`,
    });
  }
}
