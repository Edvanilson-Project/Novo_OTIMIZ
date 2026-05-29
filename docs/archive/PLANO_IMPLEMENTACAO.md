# 📋 Plano de Implementação — Resolver Problemas Críticos

## FASE 1: Remover Ollama do Frontend (2-3 horas)

### 1.1 Deletar Função Ollama em AiCostDrawer.tsx

**Arquivo**: `frontend/src/app/(DashboardLayout)/operations/planner/_components/AiCostDrawer.tsx`

**REMOVER linhas 130-148:**
```typescript
// ─── Ollama ───────────────────────────────────────────────────────────────────
// DELETE ISTO COMPLETAMENTE:
async function callOllama(prompt: string, onChunk: (t: string) => void): Promise<void> {
  const resp = await fetch('http://localhost:11434/api/generate', {
    // ... DELETE TUDO
  });
}
```

### 1.2 Remover Verificação Ollama em useEffect

**REMOVER linhas 186-190:**
```typescript
useEffect(() => {
  fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(2000) })
    .then(r => setOllamaOk(r.ok))
    .catch(() => setOllamaOk(false));
}, []);
```

### 1.3 Remover Estado ollamaOk

**REMOVER linha 171:**
```typescript
const [ollamaOk, setOllamaOk] = useState<boolean | null>(null);
```

### 1.4 Remover Status Indicator no Header

**REMOVER linhas 262:**
```typescript
{ollamaOk === true ? '🟢 Ollama ativo (qwen2.5:14b)' : ollamaOk === false ? '🟡 Análise inteligente (offline)' : '⏳ Verificando IA...'}
```

**SUBSTITUIR por:**
```typescript
'🌐 IA OpenRouter (Cloud)'
```

### 1.5 Remover Alert Ollama Offline

**REMOVER linhas 421-425:**
```typescript
{ollamaOk === false && (
  <Alert severity="info" sx={{ py: 0.25, fontSize: '0.68rem' }}>
    Ollama offline — análise inteligente ativa. Para IA: <code>ollama serve</code>
  </Alert>
)}
```

---

## FASE 2: Criar Endpoint Backend para IA (3-4 horas)

### 2.1 Criar Módulo AI no Backend

**Novo arquivo**: `backend/src/modules/ai/ai.module.ts`

```typescript
import { Module } from '@nestjs/common';
import { AiController } from './ai.controller';
import { AiService } from './ai.service';
import { HttpModule } from '@nestjs/axios';

@Module({
  imports: [HttpModule],
  controllers: [AiController],
  providers: [AiService],
  exports: [AiService],
})
export class AiModule {}
```

### 2.2 Criar Serviço AI que Chama Optimizer

**Novo arquivo**: `backend/src/modules/ai/ai.service.ts`

```typescript
import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import type { OptimizationResultSummary } from '...types...';

@Injectable()
export class AiService {
  private readonly logger = new Logger(AiService.name);

  constructor(
    private http: HttpService,
    private config: ConfigService,
  ) {}

  async analyzeOptimization(result: OptimizationResultSummary): Promise<string> {
    const optimizerUrl = this.config.get('OPTIMIZER_URL') || 'http://localhost:8000';
    const internalKey = this.config.get('INTERNAL_OPTIMIZER_KEY');

    try {
      const response = await firstValueFrom(
        this.http.post(
          `${optimizerUrl}/api/ai/analyze`,
          { result },
          {
            headers: {
              'X-Internal-Key': internalKey,
              'Content-Type': 'application/json',
            },
            timeout: 30000,
          },
        ),
      );
      return response.data.analysis || '';
    } catch (err) {
      this.logger.warn(`OpenRouter failed: ${err.message}, falling back to rule-based`);
      // Fallback: análise honesta baseada em regras
      return this.ruleBasedAnalysis(result);
    }
  }

  private ruleBasedAnalysis(result: OptimizationResultSummary): string {
    const vehicles = result.num_vehicles ?? 0;
    const totalCost = result.total_cost ?? 0;
    const totalTrips = result.total_trips ?? 0;
    const cctViolations = result.cct_violations ?? 0;

    if (totalCost / (vehicles || 1) > 1200) {
      return `⚠️ Custo/veículo: R$${(totalCost / vehicles).toFixed(0)} — acima da média (R$1.200/dia). 
        Recomendação: use MCNF para minimizar frota ou revise headways em baixa demanda.`;
    }

    if (cctViolations > 0) {
      return `⚠️ ${cctViolations} violação(ões) CCT detectada(s). 
        Ação imediata: abra aba Motoristas e revise jornadas com flag vermelha.`;
    }

    return `✅ Escala viável: ${vehicles} veículos, ${totalTrips} viagens, ${totalTrips / vehicles} viagens/veíc.`;
  }
}
```

### 2.3 Criar Controller AI

**Novo arquivo**: `backend/src/modules/ai/ai.controller.ts`

```typescript
import { Controller, Post, Body } from '@nestjs/common';
import { AiService } from './ai.service';
import type { OptimizationResultSummary } from '...types...';

@Controller('api/ai')
export class AiController {
  constructor(private aiService: AiService) {}

  @Post('analyze')
  async analyze(@Body() body: { result: OptimizationResultSummary }): Promise<{ analysis: string }> {
    const analysis = await this.aiService.analyzeOptimization(body.result);
    return { analysis };
  }
}
```

### 2.4 Registrar Módulo em app.module.ts

**Em `backend/src/app.module.ts`**, adicione em `imports`:

```typescript
import { AiModule } from './modules/ai/ai.module';

@Module({
  imports: [
    // ... outros módulos
    AiModule,
  ],
})
export class AppModule {}
```

---

## FASE 3: Integrar Frontend com Backend IA (2-3 horas)

### 3.1 Criar Hook useAiAnalysis no Frontend

**Novo arquivo**: `frontend/src/hooks/useAiAnalysis.ts`

```typescript
import { useState } from 'react';
import type { OptimizationResultSummary } from '...types...';

export function useAiAnalysis() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async (result: OptimizationResultSummary): Promise<string> => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/ai/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();
      return data.analysis || '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao analisar');
      return '';
    } finally {
      setLoading(false);
    }
  };

  return { analyze, loading, error };
}
```

### 3.2 Atualizar AiCostDrawer para Usar Backend

**Em `frontend/src/app/(DashboardLayout)/operations/planner/_components/AiCostDrawer.tsx`**:

**SUBSTITUIR `runAllSpecialists`:**

```typescript
const { analyze, loading: aiLoading } = useAiAnalysis();

const runAllSpecialists = useCallback(async () => {
  if (!result) return;
  setAnalysisRunning(true);
  const fresh = buildSpecialists(result);
  setSpecialists(fresh.map(s => ({ ...s, loading: true, analysis: undefined })));
  
  for (let i = 0; i < fresh.length; i++) {
    const sp = fresh[i];
    try {
      // Chamar backend ao invés de Ollama
      const prompt = `${buildSystemPrompt(result)}\n\n${sp.prompt}`;
      // Para cada especialista, chama análise customizada
      const analysis = await analyze(result); // Simplificado — pode customizar prompt
      setSpecialists(prev => prev.map((s, j) => 
        j === i ? { ...s, analysis, loading: false } : s
      ));
    } catch (err) {
      // Fallback: análise honesta (ruleBasedAnalysis)
      const fb = ruleBasedAnalysis(result, sp.key);
      setSpecialists(prev => prev.map((s, j) => 
        j === i ? { ...s, analysis: fb, loading: false } : s
      ));
    }
  }
  setAnalysisRunning(false);
}, [result, analyze]);
```

**SUBSTITUIR `handleSend`:**

```typescript
async function handleSend() {
  if (!input.trim() || !result || sending) return;
  const question = input.trim();
  setInput('');
  setSending(true);
  setMessages(prev => [...prev, { role: 'user', content: question, ts: Date.now() }]);

  const aiMsg: ChatMessage = { role: 'assistant', content: '', ts: Date.now() };
  setMessages(prev => [...prev, aiMsg]);
  
  try {
    // Chamar backend ao invés de Ollama
    const resp = await fetch('/api/ai/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        result,
        question, // Adicionar pergunta se backend suportar
      }),
    });
    if (resp.ok) {
      const data = await resp.json();
      setMessages(prev => {
        const u = [...prev];
        u[u.length - 1] = { ...u[u.length - 1], content: data.analysis };
        return u;
      });
    } else {
      throw new Error(`${resp.status}`);
    }
  } catch (err) {
    // Fallback: análise honesta
    const analysis = fallbackChat(question, result);
    setMessages(prev => {
      const u = [...prev];
      u[u.length - 1] = { ...u[u.length - 1], content: analysis };
      return u;
    });
  }
  setSending(false);
}
```

---

## FASE 4: Validar OpenRouter API Key (1 hora)

### 4.1 Confirmar Variável de Ambiente

```bash
# Em optimizer/.env:
OPENROUTER_API_KEY=sk_...

# Verificar se já está lá:
grep OPENROUTER_API_KEY /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer/.env
```

### 4.2 Se Não Existir, Adicionar

```bash
echo "OPENROUTER_API_KEY=sk_..." >> /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer/.env
```

### 4.3 Restart Services

```bash
# Terminal 1: Backend
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/backend
pnpm run start:dev

# Terminal 2: Frontend  
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/frontend
pnpm run dev

# Terminal 3: Optimizer (se necessário)
cd /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer
source venv/bin/activate
python -m uvicorn src.main:app --reload --port 8000
```

---

## FASE 5: Clarificar Descanso vs Intervalo (Esta Semana)

### 5.1 Documentar Parâmetros CCT

**Novo arquivo**: `backend/docs/CCT_PARAMETERS.md`

```markdown
# Parâmetros CCT — Descanso vs Intervalo

## Legislação Brasil (CLT + Convenção Coletiva)

### Intervalo (Art. 71 CLT)
- Duração: 1h (ou conforme CCT)
- Obrigatoriedade: NÃO é obrigatório SOLVER programar
- Gerenciamento: Despachante/Gestor operacional
- Local: Tipicamente no terminal

Configuração: `min_interval_minutes` (novo nome, ou documentar `min_break_minutes`)

### Descanso Interjornada (Art. 66 CLT)
- Duração: 11h mínima entre jornadas
- Obrigatoriedade: OBRIGATÓRIO — solver DEVE respeitar
- Gerenciamento: Solver programa na escala

Configuração: `inter_shift_rest_minutes` (11h = 660 min)

### Descanso Intra-Jornada (Art. 71 CCT)
- Duração: 30min após dirigir 4h contínuo
- Obrigatoriedade: OBRIGATÓRIO — solver DEVE programar
- Gerenciamento: Solver (como "relief point" ou pausa)

Configuração: `mandatory_break_after_minutes` (240 min dirigido → 30 min pausa)

## Como Solver Usa

1. Solver calcula blocos de viagens
2. Se um motorista ultrapassar `mandatory_break_after_minutes` de direção:
   → Insere pausa de ~30 minutos (honra `min_interval_minutes`)
3. Entre uma jornada e outra:
   → Garante `inter_shift_rest_minutes` (11h)
4. Intervalo entre blocos:
   → Gerenciador humano aloca conforme operação real
```

### 5.2 Validar Solver Respeita Descansos

**Buscar em**: `optimizer/src/algorithms/*/duty.py`

```bash
grep -n "mandatory_break_after\|inter_shift_rest\|relief" \
  /home/edvanilson/Área\ de\ trabalho/Novo_OTIMIZ/optimizer/src/algorithms/*/duty.py
```

Se não encontrar → **BUG**: Solver não está programando descansos obrigatórios!

---

## Checklist de Implementação

- [ ] FASE 1: Remover Ollama do Frontend (4 mudanças)
- [ ] FASE 2: Criar Módulo AI Backend (3 arquivos + 1 import)
- [ ] FASE 3: Integrar Frontend com Backend (1 hook + 2 métodos atualizados)
- [ ] FASE 4: Validar OpenRouter API Key (confirmar variável + restart)
- [ ] FASE 5: Documentar Descanso vs Intervalo (doc + validação solver)

**Tempo total**: ~10-12 horas
**Risco**: BAIXO — mudanças são isoladas, fallback é honesto

---

## Testes Após Implementação

1. **Frontend**: Abrir Planejador → clicar "Analisar tudo" → deve chamar backend (não Ollama)
2. **Backend**: POST `/api/ai/analyze` → deve retornar análise OpenRouter (ou fallback)
3. **Dados**: Verificar valores em análise são REAIS (não inventados)
4. **Offline**: Se OpenRouter cair → fallback `ruleBasedAnalysis()` ativa (sem erros)
5. **CCT**: Validar escala respeita descansos obrigatórios

