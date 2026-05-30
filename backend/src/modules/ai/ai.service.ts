import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import { TenantContext } from '../../common/context/tenant-context';
import { AiAnalysisRepository } from '../database/repositories/ai-analysis.repository';
import { AiAnalysis } from '../database/entities/ai-analysis.entity';

interface ProjectContext {
  generatedAt: string;
  rootName: string;
  packageManagers: string[];
  backendControllers: string[];
  backendServices: number;
  frontendPages: string[];
  frontendComponents: number;
  optimizerAlgorithms: string[];
  backendSpecs: number;
  frontendE2eSpecs: number;
  optimizerTests: number;
  sourceFiles: number;
  testFiles: number;
  docs: string[];
  mockSignals: string[];
}

export interface OptimizationResultSummary {
  id?: number;
  scheduleId?: number;
  num_vehicles?: number;
  vehicles?: number;
  crew?: number;
  num_crew?: number;
  total_cost?: number;
  totalCost?: number;
  total_trips?: number;
  totalTrips?: number;
  cct_violations?: number;
  cctViolations?: number;
  vsp_algorithm?: string;
  csp_algorithm?: string;
  solver_source?: string;
  elapsed_ms?: number;
  hardConstraintReport?: Record<string, unknown> | null;
  hard_constraint_report?: Record<string, unknown> | null;
  warnings?: unknown[];
  fairness?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  costBreakdown?: Record<string, unknown> | null;
  cost_breakdown?: Record<string, unknown> | null;
}

interface AIAnalysisRequest {
  result: OptimizationResultSummary;
  question?: string;
  specialist?: string;
  includeProjectContext?: boolean;
}

interface AIAnalysisResponse {
  analysis: string;
  model?: string;
  mode: 'openrouter_free' | 'rule_based';
  tokens_used?: number;
  project_context_included?: boolean;
}

interface OpenRouterModel {
  id?: string;
  name?: string;
  context_length?: number;
  pricing?: {
    prompt?: string | number;
    completion?: string | number;
  };
  architecture?: {
    modality?: string;
    input_modalities?: string[];
    output_modalities?: string[];
  };
}

export interface FreeModelInfo {
  id: string;
  name: string;
  contextLength: number;
  inputModalities: string[];
  outputModalities: string[];
  multimodal: boolean;
  score: number;
  cooling: boolean;
}

interface ResultFacts {
  scheduleId?: number;
  vehicles?: number;
  crew?: number;
  totalCost?: number;
  totalTrips?: number;
  cctViolations?: number;
  algorithm: string;
  elapsedMs?: number;
  hardIssues?: number;
  softIssues?: number;
  gini?: number;
}

const STATIC_FREE_MODELS = [
  'deepseek/deepseek-r1:free',
  'qwen/qwen3-coder:free',
  'meta-llama/llama-3.3-70b-instruct:free',
  'google/gemma-3-27b-it:free',
  'mistralai/mistral-small-3.2-24b-instruct:free',
  'nousresearch/hermes-3-llama-3.1-405b:free',
];

@Injectable()
export class AiService {
  private readonly logger = new Logger(AiService.name);
  private readonly OPENROUTER_API_URL =
    'https://openrouter.ai/api/v1/chat/completions';
  private readonly OPENROUTER_MODELS_URL =
    'https://openrouter.ai/api/v1/models';

  private cachedFreeModels: string[] = [];
  private cachedFreeModelMeta: FreeModelInfo[] = [];
  private modelsCacheExpiry = 0;
  // Refresh com frequência para captar modelos que entram/saem do free tier.
  private readonly MODELS_CACHE_MS = 1_800_000; // 30 min
  // Modelos que falharam recentemente (ex.: 429 / cota diária) são pulados até o
  // cooldown expirar — assim o seletor sempre cai no melhor modelo DISPONÍVEL.
  private modelCooldownUntil = new Map<string, number>();

  constructor(
    private http: HttpService,
    private config: ConfigService,
    private readonly aiAnalysisRepository: AiAnalysisRepository,
    private readonly tenantContext: TenantContext,
  ) {}

  async analyze(req: AIAnalysisRequest): Promise<AIAnalysisResponse> {
    const response = await this.computeAnalysis(req);
    await this.persistAnalysis(req, response);
    return response;
  }

  /**
   * Persiste a análise como trilha de auditoria (RISK-AI-AUDIT-01).
   * Best-effort: nunca falha a resposta da IA. Sem companyId no contexto
   * (chamada interna/não autenticada) a persistência é pulada.
   */
  private async persistAnalysis(
    req: AIAnalysisRequest,
    response: AIAnalysisResponse,
  ): Promise<void> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) return;
    try {
      await this.aiAnalysisRepository.save(
        this.aiAnalysisRepository.create({
          companyId,
          question: req.question ?? null,
          analysis: response.analysis,
          model: response.model ?? response.mode ?? null,
          metricsSnapshot: (req.result ?? null) as Record<
            string,
            unknown
          > | null,
        }),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.logger.warn(`Failed to persist AI analysis: ${message}`);
    }
  }

  /** Lista as análises recentes da empresa atual (mais novas primeiro). */
  async listHistory(limit = 20): Promise<AiAnalysis[]> {
    const companyId = this.tenantContext.getCompanyId();
    if (!companyId) return [];
    return this.aiAnalysisRepository.find({
      where: { companyId },
      order: { createdAt: 'DESC' },
      take: Math.min(Math.max(limit, 1), 100),
    });
  }

  private async computeAnalysis(
    req: AIAnalysisRequest,
  ): Promise<AIAnalysisResponse> {
    const result = req.result ?? {};
    const apiKey = this.config.get<string>('OPENROUTER_API_KEY');

    let projectContext: ProjectContext | undefined;
    if (req.includeProjectContext) {
      try {
        projectContext = await this.collectProjectContext();
      } catch {
        // non-fatal: project context is optional
      }
    }

    if (!apiKey) {
      this.logger.warn(
        'OPENROUTER_API_KEY not configured, using evidence-based local fallback',
      );
      return {
        analysis: this.ruleBasedAnalysis(
          result,
          req.question,
          req.specialist,
          projectContext,
        ),
        mode: 'rule_based',
        project_context_included: !!projectContext,
      };
    }

    try {
      const response = await this.callOpenRouter(
        apiKey,
        result,
        req.question,
        req.specialist,
      );
      return {
        analysis: response.analysis,
        model: response.model,
        tokens_used: response.tokensUsed,
        mode: 'openrouter_free',
        project_context_included: !!projectContext,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.logger.warn(
        `OpenRouter free models failed: ${message}; using local fallback`,
      );
      return {
        analysis: this.ruleBasedAnalysis(
          result,
          req.question,
          req.specialist,
          projectContext,
        ),
        mode: 'rule_based',
        project_context_included: !!projectContext,
      };
    }
  }

  private async callOpenRouter(
    apiKey: string,
    result: OptimizationResultSummary,
    question?: string,
    specialist?: string,
  ): Promise<{ analysis: string; model: string; tokensUsed?: number }> {
    const ranked = await this.selectFreeModels(apiKey);
    const maxAttempts = this.getMaxModelAttempts();
    // Pula modelos em cooldown (sem cota agora); se todos estiverem, tenta a lista cheia.
    const available = ranked.filter((m) => !this.isCooled(m));
    const selectedModels = (available.length ? available : ranked).slice(
      0,
      maxAttempts,
    );
    const messages = [
      {
        role: 'system',
        content: this.buildSystemPrompt(result, specialist),
      },
      {
        role: 'user',
        content: this.buildUserPrompt(result, question),
      },
    ];

    let lastError = 'no free model attempted';
    for (const model of selectedModels) {
      try {
        const response = await firstValueFrom(
          this.http.post<any>(
            this.OPENROUTER_API_URL,
            {
              model,
              messages,
              temperature: 0.25,
              max_tokens: 1000,
            },
            {
              headers: {
                Authorization: `Bearer ${apiKey}`,
                'HTTP-Referer': 'https://otimiz.app',
                'X-Title': 'OTIMIZ AI Cost Copilot Pro',
              },
              timeout: 30000,
            },
          ),
        );

        if (response.status && response.status >= 400) {
          this.markCooldown(model, response.status);
          lastError = `${model} returned HTTP ${response.status}`;
          continue;
        }

        const text = String(
          (response.data as any)?.choices?.[0]?.message?.content ?? '',
        ).trim();
        if (!text) {
          this.markCooldown(model);
          lastError = `${model} returned empty content`;
          continue;
        }

        return {
          analysis: text,
          model,
          tokensUsed: (response.data as any)?.usage?.total_tokens,
        };
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response
          ?.status;
        this.markCooldown(model, status);
        lastError = `${model}: ${err instanceof Error ? err.message : String(err)}`;
        this.logger.warn(
          `OpenRouter free model failed, trying next: ${lastError}`,
        );
      }
    }

    throw new Error(lastError);
  }

  private isCooled(modelId: string): boolean {
    return (this.modelCooldownUntil.get(modelId) ?? 0) > Date.now();
  }

  /**
   * Marca um modelo como indisponível por um tempo. Cota/limite diário (HTTP 429)
   * recebe cooldown longo; outras falhas, curto. Assim o seletor migra para o
   * melhor modelo disponível e volta a usar este quando o limite renovar.
   */
  private markCooldown(modelId: string, status?: number): void {
    const ms = status === 429 ? 30 * 60_000 : 3 * 60_000;
    this.modelCooldownUntil.set(modelId, Date.now() + ms);
  }

  private async selectFreeModels(apiKey: string): Promise<string[]> {
    const now = Date.now();
    const pinnedModel = this.config.get<string>('OPENROUTER_MODEL');
    const allowPaid =
      this.config.get<string>('OPENROUTER_ALLOW_PAID_MODELS') === 'true';

    if (now > this.modelsCacheExpiry || this.cachedFreeModels.length === 0) {
      this.cachedFreeModels = await this.fetchFreeModels(apiKey);
      this.modelsCacheExpiry = now + this.MODELS_CACHE_MS;
    }

    const models = [...this.cachedFreeModels];
    if (pinnedModel) {
      if (allowPaid || this.isModelIdFree(pinnedModel)) {
        return [pinnedModel, ...models.filter((m) => m !== pinnedModel)];
      }
      this.logger.warn(
        `OPENROUTER_MODEL=${pinnedModel} ignored because paid models are disabled`,
      );
    }

    return models.length ? models : STATIC_FREE_MODELS;
  }

  private async fetchFreeModels(apiKey: string): Promise<string[]> {
    try {
      const response = await firstValueFrom(
        this.http.get<any>(this.OPENROUTER_MODELS_URL, {
          headers: { Authorization: `Bearer ${apiKey}` },
          timeout: 10000,
        }),
      );

      const models = ((response.data as any)?.data ?? []) as OpenRouterModel[];
      const ranked = models
        .filter((m) => m.id && this.isFreeModel(m))
        .sort((a, b) => this.modelScore(b) - this.modelScore(a));

      // Guarda metadados (modalidades, contexto) para expor as possibilidades
      // — incluindo modelos que aceitam imagem/áudio/vídeo — via /ai/models.
      const seen = new Set<string>();
      this.cachedFreeModelMeta = [];
      for (const m of ranked) {
        const id = m.id as string;
        if (seen.has(id)) continue;
        seen.add(id);
        const inputModalities = m.architecture?.input_modalities ?? ['text'];
        const outputModalities = m.architecture?.output_modalities ?? ['text'];
        this.cachedFreeModelMeta.push({
          id,
          name: m.name ?? id,
          contextLength: Number(m.context_length ?? 0),
          inputModalities,
          outputModalities,
          multimodal: inputModalities.some((x) => x && x !== 'text'),
          score: Math.round(this.modelScore(m)),
          cooling: false,
        });
      }

      // Candidatos para o chat: precisam GERAR texto (exclui modelos de música/
      // imagem como geradores). A lista completa fica em cachedFreeModelMeta
      // (exposta em /ai/models) para mostrar todas as possibilidades.
      const freeModels = this.cachedFreeModelMeta
        .filter(
          (m) =>
            m.outputModalities.length === 0 ||
            m.outputModalities.includes('text'),
        )
        .map((m) => m.id);
      if (!freeModels.length) {
        this.logger.warn(
          'OpenRouter model list returned no free models; using static free fallback',
        );
        return STATIC_FREE_MODELS;
      }

      return freeModels;
    } catch (err) {
      this.logger.warn(
        `Failed to fetch OpenRouter models: ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
      return STATIC_FREE_MODELS;
    }
  }

  private isFreeModel(model: OpenRouterModel): boolean {
    if (model.id && this.isModelIdFree(model.id)) return true;
    return (
      this.priceIsFree(model.pricing?.prompt) &&
      this.priceIsFree(model.pricing?.completion)
    );
  }

  private isModelIdFree(modelId: string): boolean {
    return modelId.toLowerCase().includes(':free');
  }

  private priceIsFree(value: unknown): boolean {
    if (value === undefined || value === null) return false;
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed === 0;
  }

  private modelScore(model: OpenRouterModel): number {
    const id = String(model.id ?? '').toLowerCase();
    const contextScore = Number(model.context_length ?? 0) / 1000;
    const reasoningBonus =
      id.includes('deepseek') || id.includes('qwen') || id.includes('llama')
        ? 80
        : 0;
    const codingBonus =
      id.includes('coder') || id.includes('instruct') || id.includes('reason')
        ? 30
        : 0;
    // Pequeno desempate a favor de modelos multimodais (aceitam imagem/áudio/
    // arquivo) — sem dominar a escolha, pois a análise do copiloto é texto.
    const extraModalities = (model.architecture?.input_modalities ?? []).filter(
      (m) => m && m !== 'text',
    ).length;
    const multimodalBonus = extraModalities * 3;
    return contextScore + reasoningBonus + codingBonus + multimodalBonus;
  }

  /**
   * Lista os modelos FREE disponíveis no momento, já ranqueados (melhor primeiro),
   * com modalidades de entrada/saída e estado de cooldown. Permite ao frontend
   * mostrar as possibilidades (texto, imagem, áudio, vídeo…) e o modelo ativo.
   */
  async listModels(): Promise<{
    updatedAt: string;
    activeModel: string | null;
    models: FreeModelInfo[];
  }> {
    const apiKey = this.config.get<string>('OPENROUTER_API_KEY');
    if (!apiKey) {
      return { updatedAt: new Date().toISOString(), activeModel: null, models: [] };
    }
    await this.selectFreeModels(apiKey);
    const models = this.cachedFreeModelMeta.map((m) => ({
      ...m,
      cooling: this.isCooled(m.id),
    }));
    // activeModel = melhor candidato real do chat: gera texto e não está em cooldown.
    const activeModel =
      models.find(
        (m) =>
          !m.cooling &&
          (m.outputModalities.length === 0 ||
            m.outputModalities.includes('text')),
      )?.id ?? null;
    return {
      updatedAt: new Date(this.modelsCacheExpiry - this.MODELS_CACHE_MS).toISOString(),
      activeModel,
      models,
    };
  }

  private getMaxModelAttempts(): number {
    const configured = Number(
      this.config.get<string>('OPENROUTER_FREE_MODEL_ATTEMPTS') ?? 4,
    );
    if (!Number.isFinite(configured)) return 4;
    return Math.max(1, Math.min(8, Math.floor(configured)));
  }

  private buildSystemPrompt(
    result: OptimizationResultSummary,
    specialist?: string,
  ): string {
    const persona = this.specialistPersona(specialist);
    const facts = this.extractFacts(result);

    return `Você é ${persona} do OTIMIZ/OTTrans.

REGRAS DE EVIDÊNCIA:
- Use somente DADOS CONFIRMADOS da programação/escala enviada no prompt.
- Não leia, peça ou mencione projeto, código-fonte, repositório, arquivos, backend ou frontend.
- Não invente benchmark, economia, km, horas, escala de mercado, regra CCT ou comportamento.
- Se um dado não estiver no payload operacional, escreva "não verificado" e diga qual evidência operacional falta.
- Pode calcular apenas razões diretas a partir de valores confirmados, como custo/veículo e viagens/veículo.
- Recomendações devem ser ações testáveis na operação ou no solver: parâmetro, cenário, garagem, frota, bloco, jornada, CCT, pareamento ou reotimização.
- Explique em português claro o que deixa a programação boa ou ruim e quais dados faltam para concluir.
- Modelos pagos não devem ser exigidos; esta resposta deve funcionar com modelos OpenRouter gratuitos.

CONTEXTO DA ESCALA:
- ID: ${facts.scheduleId ?? 'não informado'}
- Veículos: ${facts.vehicles ?? 'não informado'}
- Motoristas/tripulação: ${facts.crew ?? 'não informado'}
- Viagens: ${facts.totalTrips ?? 'não informado'}
- Custo total: ${this.formatCurrencyOrMissing(facts.totalCost)}
- Algoritmo: ${facts.algorithm}
- CCT: ${
      facts.cctViolations === undefined
        ? 'não informado'
        : `${facts.cctViolations} violação(ões)`
    }
- Issues críticos: ${facts.hardIssues ?? 'não informado'}
- Alertas: ${facts.softIssues ?? 'não informado'}

FORMATO:
**Diagnóstico**
**Evidências**
**Ações recomendadas**
**Não verificado**

Máximo 500 palavras.`;
  }

  private buildUserPrompt(
    result: OptimizationResultSummary,
    question?: string,
  ): string {
    const facts = this.extractFacts(result);
    const lines = [
      'DADOS CONFIRMADOS DA ESCALA:',
      `- scheduleId: ${facts.scheduleId ?? 'não informado'}`,
      `- vehicles: ${facts.vehicles ?? 'não informado'}`,
      `- crew: ${facts.crew ?? 'não informado'}`,
      `- totalTrips: ${facts.totalTrips ?? 'não informado'}`,
      `- totalCost: ${facts.totalCost ?? 'não informado'}`,
      `- cctViolations: ${facts.cctViolations ?? 'não informado'}`,
      `- algorithm: ${facts.algorithm}`,
      `- elapsedMs: ${facts.elapsedMs ?? 'não informado'}`,
      `- hardIssues: ${facts.hardIssues ?? 'não informado'}`,
      `- softIssues: ${facts.softIssues ?? 'não informado'}`,
      `- fairness.gini: ${facts.gini ?? 'não informado'}`,
    ];

    if (facts.vehicles && facts.totalCost !== undefined) {
      lines.push(
        `- derived.costPerVehicle: ${(facts.totalCost / facts.vehicles).toFixed(2)}`,
      );
    }
    if (facts.totalTrips && facts.totalCost !== undefined) {
      lines.push(
        `- derived.costPerTrip: ${(facts.totalCost / facts.totalTrips).toFixed(2)}`,
      );
    }
    if (facts.vehicles && facts.totalTrips !== undefined) {
      lines.push(
        `- derived.tripsPerVehicle: ${(facts.totalTrips / facts.vehicles).toFixed(2)}`,
      );
    }

    const operationalContext = this.formatOperationalContext(result);
    if (operationalContext) {
      lines.push('', 'CONTEXTO OPERACIONAL DA PROGRAMAÇÃO EXECUTADA:');
      lines.push(operationalContext);
    }

    lines.push(
      '',
      'PERGUNTA OU TAREFA:',
      question?.trim() || 'Faça uma análise executiva da escala atual.',
    );

    return lines.join('\n');
  }

  private formatOperationalContext(result: OptimizationResultSummary): string {
    const metadata = asRecord(result.metadata) ?? asRecord(result.meta);
    const context = asRecord(metadata?.ai_operational_context);
    if (!context) return '';

    try {
      return JSON.stringify(context, null, 2).slice(0, 12000);
    } catch {
      return '';
    }
  }

  private specialistPersona(specialist?: string): string {
    const key = (specialist ?? '').toLowerCase().replace(/_/g, '-');
    const personas: Record<string, string> = {
      operations: 'um Diretor de Operações de transporte coletivo urbano',
      planner: 'um Planejador de Escala e Programação operacional',
      optimization: 'um Matemático de Otimização VSP/CSP e auditor de solver',
      blocks: 'um Auditor de Blocos, viagens e cobertura operacional',
      cost: 'um Especialista em Custos Operacionais de frota e tripulação',
      cct: 'um Especialista em CCT/CLT Brasil aplicado à escala de motoristas',
      fleet: 'um Engenheiro de Frota e Manutenção',
      regularity: 'um Fiscal de Terminal e Regularidade de campo',
      risk: 'um Especialista em Risco Operacional, Auditoria e Continuidade',
      improvement: 'um Consultor de melhoria de cenários e reotimização operacional',
    };
    return personas[key] ?? 'um Diretor Técnico de Operações e Produto';
  }

  private appendProjectContext(analysis: string, ctx: ProjectContext): string {
    const signals = ctx.mockSignals ?? [];
    const signalList = signals.length > 0 ? signals.join('; ') : 'nenhum';
    return (
      analysis +
      [
        '',
        '**snapshot estrutural do projeto (leitura parcial)**',
        `- Projeto: ${ctx.rootName} — ${ctx.sourceFiles} arquivos fonte, ${ctx.testFiles} de teste`,
        `- Sinais de simulação detectados: ${signalList}`,
        '',
        'Aviso: esta análise não leu o conteúdo completo dos arquivos — apenas metadados e sinais estruturais foram coletados.',
      ].join('\n')
    );
  }

  private ruleBasedAnalysis(
    result: OptimizationResultSummary,
    question?: string,
    specialist?: string,
    projectContext?: ProjectContext,
  ): string {
    const facts = this.extractFacts(result);
    const q = `${question ?? ''} ${specialist ?? ''}`.toLowerCase();
    const base = this.confirmedFactsSummary(facts);

    const withCtx = (analysis: string) =>
      projectContext ? this.appendProjectContext(analysis, projectContext) : analysis;

    if (
      q.includes('custo') ||
      q.includes('redu') ||
      q.includes('econom') ||
      q.includes('cost')
    ) {
      const costLines = [
        '**Diagnóstico**',
        base,
        '',
        '**Evidências**',
        `- Custo total: ${this.formatCurrencyOrMissing(facts.totalCost)}`,
        `- Custo/veículo: ${
          facts.totalCost !== undefined && facts.vehicles
            ? this.formatCurrencyOrMissing(facts.totalCost / facts.vehicles)
            : 'não verificado'
        }`,
        `- Custo/viagem: ${
          facts.totalCost !== undefined && facts.totalTrips
            ? this.formatCurrencyOrMissing(facts.totalCost / facts.totalTrips)
            : 'não verificado'
        }`,
        '',
        '**Ações recomendadas**',
        '- Rodar cenário comparativo com MCNF e Pipeline Híbrido e comparar custo total, frota e issues.',
        '- Investigar tempos mortos e km morto somente se esses campos estiverem no relatório da escala.',
        '- Bloquear publicação se houver hard issue ou violação CCT.',
        '',
        '**Não verificado**',
        '- Economia percentual, benchmark externo e custo/km não foram calculados porque não estão confirmados neste payload.',
      ];
      return withCtx(costLines.join('\n'));
    }

    if (
      q.includes('cct') ||
      q.includes('clt') ||
      q.includes('trabalh') ||
      q.includes('legal')
    ) {
      return withCtx([
        '**Diagnóstico**',
        facts.cctViolations === undefined
          ? 'Violação CCT não veio no payload.'
          : facts.cctViolations > 0
            ? `${facts.cctViolations} violação(ões) CCT exigem revisão antes de operar.`
            : 'Payload informa zero violações CCT.',
        '',
        '**Evidências**',
        base,
        '',
        '**Ações recomendadas**',
        '- Abrir aba Motoristas e validar jornadas, intervalos e descansos contra o relatório de hard constraints.',
        '- Confirmar se a regra aplicável veio dos parâmetros da empresa e não de valor padrão escondido.',
        '- Retestar após qualquer reotimização ou edição manual da escala.',
        '',
        '**Não verificado**',
        '- A CCT vigente e os detalhes por motorista não vieram neste payload.',
      ].join('\n'));
    }

    if (
      q.includes('algorit') ||
      q.includes('mcnf') ||
      q.includes('vsp') ||
      q.includes('csp') ||
      q.includes('otimiz')
    ) {
      return withCtx([
        '**Diagnóstico**',
        `Algoritmo informado: ${facts.algorithm}.`,
        '',
        '**Evidências**',
        base,
        '',
        '**Ações recomendadas**',
        '- Comparar algoritmos com a mesma massa de viagens, mesmos parâmetros e mesma empresa.',
        '- Exigir evidência de cobertura exata das viagens e ausência de duplicidade.',
        '- Usar certificado/gap quando disponível antes de chamar um resultado de ótimo.',
        '',
        '**Não verificado**',
        '- Gap de otimalidade, lower bound e detalhamento VSP/CSP não estão confirmados neste payload.',
      ].join('\n'));
    }

    return withCtx([
      '**Diagnóstico**',
      base,
      '',
      '**Evidências**',
      `- Algoritmo: ${facts.algorithm}`,
      `- Issues críticos: ${facts.hardIssues ?? 'não informado'}`,
      `- Alertas: ${facts.softIssues ?? 'não informado'}`,
      '',
      '**Ações recomendadas**',
      '- Perguntar por custos, CCT, algoritmo, frota, blocos, jornadas ou melhorias para análise direcionada.',
      '- Rodar cenários comparáveis no solver antes de assumir economia ou qualidade superior.',
      '',
      '**Não verificado**',
      '- Campos ausentes no payload não foram inferidos.',
    ].join('\n'));
  }

  private confirmedFactsSummary(facts: ResultFacts): string {
    return [
      `Escala ${facts.scheduleId ?? 'não informada'}:`,
      `${facts.vehicles ?? 'não informado'} veículo(s),`,
      `${facts.totalTrips ?? 'não informado'} viagem(ns),`,
      `${this.formatCurrencyOrMissing(facts.totalCost)} de custo total,`,
      `algoritmo ${facts.algorithm},`,
      `CCT ${
        facts.cctViolations === undefined
          ? 'não informado'
          : `${facts.cctViolations} violação(ões)`
      }.`,
    ].join(' ');
  }

  private extractFacts(result: OptimizationResultSummary): ResultFacts {
    const hardConstraintReport =
      asRecord(result.hardConstraintReport) ??
      asRecord(result.hard_constraint_report);
    const output = asRecord(hardConstraintReport?.output);
    const fairness = asRecord(result.fairness);
    const warnings = Array.isArray(result.warnings)
      ? result.warnings.length
      : undefined;

    return {
      scheduleId: firstNumber(result.id, result.scheduleId),
      vehicles: firstNumber(result.num_vehicles, result.vehicles),
      crew: firstNumber(result.num_crew, result.crew),
      totalCost: firstNumber(result.total_cost, result.totalCost),
      totalTrips: firstNumber(result.total_trips, result.totalTrips),
      cctViolations: firstNumber(
        result.cct_violations,
        result.cctViolations,
      ),
      algorithm:
        result.vsp_algorithm ??
        result.csp_algorithm ??
        result.solver_source ??
        'não informado',
      elapsedMs: firstNumber(result.elapsed_ms),
      hardIssues:
        countArray(output?.hard_issues) ??
        countArray(hardConstraintReport?.hardIssues) ??
        countArray(hardConstraintReport?.hard_issues),
      softIssues:
        countArray(output?.soft_issues) ??
        warnings ??
        countArray(hardConstraintReport?.softIssues) ??
        countArray(hardConstraintReport?.soft_issues),
      gini: firstNumber(fairness?.gini_coefficient, fairness?.gini),
    };
  }

  private formatCurrencyOrMissing(value?: number): string {
    if (value === undefined) return 'não informado';
    return `R$${value.toFixed(2)}`;
  }

  private async collectMockSignals(root: string): Promise<string[]> {
    const signals: string[] = [];
    const identifierRegex =
      /\b(?:function|const|let|var|class)\s+(\w*(?:mock|placeholder|Mock|Placeholder)\w*)/g;

    const scanDir = async (dir: string) => {
      const entries = await fs
        .readdir(dir, { withFileTypes: true })
        .catch(() => null);
      if (!entries) return;
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        const relative = path.relative(root, full);
        if (entry.isDirectory()) {
          if (entry.name === 'node_modules' || entry.name === '.git') continue;
          await scanDir(full);
        } else if (entry.isFile() && /\.[tj]sx?$/.test(entry.name)) {
          if (
            relative.startsWith('frontend' + path.sep) ||
            relative.includes(path.join('ai', 'ai.service'))
          ) {
            continue;
          }
          let content = '';
          try {
            content = await fs.readFile(full, 'utf8');
          } catch {
            continue;
          }
          identifierRegex.lastIndex = 0;
          let match: RegExpExecArray | null;
          while ((match = identifierRegex.exec(content)) !== null) {
            signals.push(`${relative}: ${match[1]}`);
          }
        }
      }
    };

    await scanDir(root);
    return signals;
  }

  private async collectProjectContext(): Promise<ProjectContext> {
    const root = path.resolve(__dirname, '../../../../..');
    const mockSignals = await this.collectMockSignals(root);

    const countFiles = async (
      dir: string,
      pattern: RegExp,
    ): Promise<string[]> => {
      const found: string[] = [];
      const walk = async (d: string) => {
        const entries = await fs
          .readdir(d, { withFileTypes: true })
          .catch(() => null);
        if (!entries) return;
        for (const e of entries) {
          const full = path.join(d, e.name);
          if (e.isDirectory()) {
            if (e.name === 'node_modules' || e.name === '.git') continue;
            await walk(full);
          } else if (e.isFile() && pattern.test(e.name)) {
            found.push(path.relative(root, full));
          }
        }
      };
      await walk(dir);
      return found;
    };

    const [backendControllers, frontendPages, optimizerAlgorithms, allTs, allSpecs] =
      await Promise.all([
        countFiles(path.join(root, 'backend/src'), /\.controller\.ts$/),
        countFiles(path.join(root, 'frontend/src/app'), /\/page\.tsx$/),
        countFiles(path.join(root, 'optimizer/src/algorithms'), /\.py$/),
        countFiles(root, /\.[tj]sx?$/),
        countFiles(root, /\.spec\.[tj]sx?$/),
      ]).catch(() => [[], [], [], [], []]);

    return {
      generatedAt: new Date().toISOString(),
      rootName: path.basename(root),
      packageManagers: ['backend:pnpm', 'frontend:pnpm', 'optimizer:pip'],
      backendControllers,
      backendServices: 0,
      frontendPages,
      frontendComponents: 0,
      optimizerAlgorithms,
      backendSpecs: allSpecs.filter((f) => f.includes('backend')).length,
      frontendE2eSpecs: allSpecs.filter((f) => f.includes('frontend')).length,
      optimizerTests: allSpecs.filter((f) => f.includes('optimizer')).length,
      sourceFiles: allTs.length,
      testFiles: allSpecs.length,
      docs: [],
      mockSignals,
    };
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    const parsed =
      typeof value === 'number'
        ? value
        : typeof value === 'string'
          ? Number(value)
          : Number.NaN;
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

function countArray(value: unknown): number | undefined {
  return Array.isArray(value) ? value.length : undefined;
}
