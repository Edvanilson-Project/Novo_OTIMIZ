import { of } from 'rxjs';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { AiService } from './ai.service';

describe('AiService', () => {
  let http: { get: jest.Mock; post: jest.Mock };
  let config: { get: jest.Mock };
  let configValues: Record<string, string | undefined>;
  let repo: { create: jest.Mock; save: jest.Mock; find: jest.Mock };
  let companyId: number | undefined;

  beforeEach(() => {
    http = {
      get: jest.fn(),
      post: jest.fn(),
    };
    configValues = {};
    config = {
      get: jest.fn((key: string) => configValues[key]),
    };
    repo = {
      create: jest.fn((data) => data),
      save: jest.fn(async (data) => ({ id: 1, ...data })),
      find: jest.fn(async () => []),
    };
    companyId = undefined;
  });

  const tenant = () => ({ getCompanyId: () => companyId });

  function service() {
    return new AiService(http as any, config as any, repo as any, tenant() as any);
  }

  it('uses an honest rule-based fallback when OpenRouter is not configured', async () => {
    const ai = service();

    const response = await ai.analyze({
      result: {
        id: 10,
        num_vehicles: 2,
        total_trips: 10,
        total_cost: 3738.4,
        cct_violations: 0,
        vsp_algorithm: 'mcnf_vsp',
      },
      question: 'Qual é a maior oportunidade de redução de custo?',
    });

    expect(response.mode).toBe('rule_based');
    expect(response.analysis).toContain('Custo total');
    expect(response.analysis).toContain('não foram calculados');
    expect(response.analysis).not.toMatch(/R\$800|1200|15%|ollama/i);
  });

  it('tries only free OpenRouter models and fails over to the next free model', async () => {
    configValues.OPENROUTER_API_KEY = 'sk-or-test';
    configValues.OPENROUTER_FREE_MODEL_ATTEMPTS = '2';
    http.get.mockReturnValue(
      of({
        data: {
          data: [
            {
              id: 'paid/model',
              context_length: 200000,
              pricing: { prompt: '0.00001', completion: '0.00001' },
            },
            {
              id: 'provider/free-small:free',
              context_length: 1000,
              pricing: { prompt: '0', completion: '0' },
            },
            {
              id: 'provider/free-big:free',
              context_length: 2000,
              pricing: { prompt: '0', completion: '0' },
            },
          ],
        },
      }),
    );
    http.post
      .mockReturnValueOnce(of({ status: 429, data: {} }))
      .mockReturnValueOnce(
        of({
          status: 200,
          data: {
            choices: [{ message: { content: 'análise grátis ok' } }],
            usage: { total_tokens: 42 },
          },
        }),
      );

    const response = await service().analyze({
      result: { vehicles: 2, totalTrips: 10, totalCost: 1000 },
      question: 'Analise a escala.',
    });

    expect(response.mode).toBe('openrouter_free');
    expect(response.model).toBe('provider/free-small:free');
    expect(response.tokens_used).toBe(42);
    expect(http.post.mock.calls[0][1].model).toBe('provider/free-big:free');
    expect(http.post.mock.calls[1][1].model).toBe('provider/free-small:free');
    expect(http.post.mock.calls.map((call) => call[1].model)).not.toContain(
      'paid/model',
    );
  });

  it('includes project context for project-analysis questions without claiming full-file review', async () => {
    const ai = service();
    jest.spyOn(ai as any, 'collectProjectContext').mockResolvedValue({
      generatedAt: '2026-05-25T00:00:00.000Z',
      rootName: 'Novo_OTIMIZ',
      packageManagers: ['backend:pnpm', 'frontend:pnpm', 'optimizer:pip'],
      backendControllers: ['backend/src/modules/ai/ai.controller.ts'],
      backendServices: 10,
      frontendPages: ['frontend/src/app/(DashboardLayout)/operations/planner/page.tsx'],
      frontendComponents: 80,
      optimizerAlgorithms: ['optimizer/src/algorithms/vsp/mcnf.py'],
      backendSpecs: 50,
      frontendE2eSpecs: 4,
      optimizerTests: 60,
      sourceFiles: 500,
      testFiles: 114,
      docs: ['AUDITORIA_PLANEJADOR_GANTT_2026_05_24.md'],
      mockSignals: ['optimizer/src/api/routes/whatif.py: mock'],
    });

    const response = await ai.analyze({
      result: { vehicles: 2, totalTrips: 10, totalCost: 1000 },
      question: 'Analise a arquitetura do projeto e os mocks restantes.',
      includeProjectContext: true,
    });

    expect(response.mode).toBe('rule_based');
    expect(response.project_context_included).toBe(true);
    expect(response.analysis).toContain('snapshot estrutural');
    expect(response.analysis).toContain('optimizer/src/api/routes/whatif.py');
    expect(response.analysis).toContain('não leu o conteúdo completo');
  });

  it('filters UI placeholders and the auditor implementation from production data-simulation signals', async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'otimiz-ai-signals-'));
    try {
      await fs.mkdir(path.join(root, 'frontend/src/app'), { recursive: true });
      await fs.mkdir(path.join(root, 'backend/src/modules/ai'), {
        recursive: true,
      });
      await fs.mkdir(path.join(root, 'backend/src/modules/operations'), {
        recursive: true,
      });

      await fs.writeFile(
        path.join(root, 'frontend/src/app/Search.tsx'),
        '<TextField placeholder="Buscar..." />',
      );
      await fs.writeFile(
        path.join(root, 'backend/src/modules/ai/ai.service.ts'),
        "const auditorVocabulary = ['mock', 'placeholder'];",
      );
      await fs.writeFile(
        path.join(root, 'backend/src/modules/operations/scenario.ts'),
        'export function placeholderScenario() { return { source: "fallback" }; }',
      );

      const signals = await (service() as any).collectMockSignals(root);

      expect(signals).toEqual([
        'backend/src/modules/operations/scenario.ts: placeholderScenario',
      ]);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });

  it('does not persist when there is no company in context', async () => {
    companyId = undefined;
    await service().analyze({
      result: { total_cost: 1000 },
      question: 'pergunta',
    });
    expect(repo.save).not.toHaveBeenCalled();
  });

  it('persists the analysis as an audit trail when a company is in context', async () => {
    companyId = 7;
    const response = await service().analyze({
      result: { total_cost: 1000 },
      question: 'pergunta',
    });
    expect(repo.save).toHaveBeenCalledTimes(1);
    const saved = repo.save.mock.calls[0][0];
    expect(saved.companyId).toBe(7);
    expect(saved.question).toBe('pergunta');
    expect(saved.analysis).toBe(response.analysis);
  });

  it('never fails the analysis when persistence throws', async () => {
    companyId = 7;
    repo.save.mockRejectedValueOnce(new Error('db down'));
    const response = await service().analyze({ result: { total_cost: 1000 } });
    expect(response.analysis).toBeTruthy();
  });

  it('returns an empty history when there is no company in context', async () => {
    companyId = undefined;
    expect(await service().listHistory()).toEqual([]);
    expect(repo.find).not.toHaveBeenCalled();
  });

  it('lists history scoped to the current company', async () => {
    companyId = 7;
    await service().listHistory(5);
    expect(repo.find).toHaveBeenCalledWith({
      where: { companyId: 7 },
      order: { createdAt: 'DESC' },
      take: 5,
    });
  });

  it('skips a rate-limited (429) model on the next call (cooldown self-heal)', async () => {
    configValues.OPENROUTER_API_KEY = 'sk-or-test';
    http.get.mockReturnValue(
      of({
        data: {
          data: [
            {
              id: 'p/big:free',
              context_length: 2000,
              pricing: { prompt: '0', completion: '0' },
            },
            {
              id: 'p/small:free',
              context_length: 1000,
              pricing: { prompt: '0', completion: '0' },
            },
          ],
        },
      }),
    );
    http.post.mockImplementation((_url: string, body: { model: string }) =>
      of(
        body.model.includes('big')
          ? { status: 429, data: {} }
          : {
              status: 200,
              data: {
                choices: [{ message: { content: 'ok' } }],
                usage: { total_tokens: 5 },
              },
            },
      ),
    );
    const ai = service();
    const r1 = await ai.analyze({ result: { totalCost: 1 }, question: 'q1' });
    expect(r1.model).toBe('p/small:free');
    http.post.mockClear();
    const r2 = await ai.analyze({ result: { totalCost: 1 }, question: 'q2' });
    expect(r2.model).toBe('p/small:free');
    // O modelo que deu 429 entrou em cooldown e não é tentado de novo.
    expect(http.post.mock.calls.map((c) => c[1].model)).not.toContain(
      'p/big:free',
    );
  });

  it('lists ranked free models with modality info and active model', async () => {
    configValues.OPENROUTER_API_KEY = 'sk-or-test';
    http.get.mockReturnValue(
      of({
        data: {
          data: [
            {
              id: 'x/text:free',
              context_length: 1000,
              pricing: { prompt: '0', completion: '0' },
              architecture: { input_modalities: ['text'] },
            },
            {
              id: 'y/vision:free',
              name: 'Vision',
              context_length: 1000,
              pricing: { prompt: '0', completion: '0' },
              architecture: { input_modalities: ['text', 'image'] },
            },
          ],
        },
      }),
    );
    const out = await service().listModels();
    expect(out.models.length).toBe(2);
    const vision = out.models.find((m) => m.id === 'y/vision:free');
    expect(vision?.multimodal).toBe(true);
    expect(vision?.inputModalities).toContain('image');
    // multimodal pontua mais → fica como modelo ativo (melhor disponível).
    expect(out.activeModel).toBe('y/vision:free');
  });
});
