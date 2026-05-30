import { Entity, Column, Index } from 'typeorm';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

/**
 * Trilha de auditoria das análises do AI Cost Copilot (RISK-AI-AUDIT-01).
 * Guarda pergunta, resposta, modelo/modo usado e um snapshot das métricas
 * analisadas, isolado por empresa (companyId herdado de TenantBaseEntity).
 */
@Entity('ai_analyses')
@Index('IDX_ai_analyses_company_created', ['companyId', 'createdAt'])
export class AiAnalysis extends TenantBaseEntity {
  @Column('text', { nullable: true })
  question: string | null;

  @Column('text')
  analysis: string;

  @Column({ type: 'varchar', length: 200, nullable: true })
  model: string | null;

  @Column('jsonb', { nullable: true })
  metricsSnapshot: Record<string, unknown> | null;
}
