# FASE 1 - Plano de Testes de Integração e QA

## 📋 Objetivo
Validar que o sistema completo funciona de ponta a ponta com dados reais:
- Database → Backend API → Optimizer Python → Frontend Dashboard
- Edição de viagens via drag & drop
- Cálculo correto de custos

## 🧪 Teste de Integração E2E

### Teste 1: Fluxo Completo de Otimização Multi-Depot
**Requisitos:**
- 3 tipos de veículos configurados (BUS, MINIBUS, COACH)
- 5+ veículos ativos
- 20-30 viagens para otimizar
- 2+ depots com veículos distribuídos

**Passos:**
1. Cria r tipos de veículos via API `/vehicles/types`
2. Criar veículos via API `/vehicles`
3. Executar otimização via `/optimize`
4. Verificar se o custo reflete os tipos de veículos
5. Validar alocação de veículos nos blocos

**Validações:**
- ✅ Todos os tipos de veículos foram considerados no custo
- ✅ Veículos foram atribuídos aos blocos
- ✅ Custo total = soma de custos fixos de tipos + custos operacionais
- ✅ Sem viagens não alocadas (unassigned_trips = 0)

---

### Teste 2: Reatribuição de Viagem (Drag & Drop)
**Requisitos:**
- 1 schedule otimizado com 3+ blocos
- 3+ viagens em um bloco para reatribuir

**Passos:**
1. Buscar schedule otimizado via `GET /latest-schedule`
2. Usar `PATCH /reassign-trip` para mover viagem para outro bloco
3. Verificar resposta contém `isValid: true`
4. Buscar schedule novamente
5. Validar que viagem está no novo bloco
6. Verificar custo foi recalculado

**Validações:**
- ✅ Viagem foi movida para o bloco correto
- ✅ Custo foi atualizado
- ✅ Sem sobreposição temporal no bloco destino
- ✅ Cache foi invalidado (dados atualizados)

---

### Teste 3: Análise de Custos de Frota
**Requisitos:**
- Fleet management page carregando dados reais

**Passos:**
1. Acessar `/settings/fleet`
2. Verificar lista de tipos de veículos
3. Verificar lista de veículos
4. Validar totais de custo
5. Validar cálculo de custo por passageiro

**Validações:**
- ✅ Todos os tipos aparecem corretamente
- ✅ Total de veículos ativos está correto
- ✅ Custo total = sum(type.costPerDay)
- ✅ Custo por passageiro = costPerDay / capacity

---

### Teste 4: Impacto de Custos em Otimização
**Requisitos:**
- Dois cenários de otimização

**Cenário A:** Tipos de veículos caros
- BUS: R$ 800/dia, MINIBUS: R$ 300/dia

**Cenário B:** Tipos de veículos baratos
- BUS: R$ 400/dia, MINIBUS: R$ 150/dia

**Validações:**
- ✅ Cenário B resulta em menor custo total
- ✅ Preferência por MINIBUS no Cenário B
- ✅ Preferência por BUS no Cenário A (menos trocas)

---

## 📊 Métricas de Sucesso

| Métrica | Target | Status |
|---------|--------|--------|
| Build Frontend | 0 erros | ✅ Completo |
| Build Backend | 30/30 testes | ✅ Completo |
| API Endpoints | 7+ endpoints | ✅ Completo |
| Testes E2E | 4/4 cenários | 🔄 Em andamento |
| Latência API | < 500ms | ⏳ A validar |
| Custo cálculo | Precisão 100% | ⏳ A validar |

---

## 🔍 Checklist de Validação

### Backend
- [ ] Build compila sem erros
- [ ] 30/30 testes unitários passam
- [ ] Endpoints `/vehicles/*` funcionam
- [ ] Endpoint `PATCH /reassign-trip` funciona
- [ ] Cache é invalidado corretamente
- [ ] Transações mantêm integridade de dados

### Frontend
- [ ] Build compila sem erros
- [ ] Fleet Management page carrega dados
- [ ] FleetCostAnalysis mostra dados corretos
- [ ] TripDragDropEditor permite drag & drop
- [ ] Snackbars mostram feedback correto
- [ ] Sem console errors/warnings

### Optimizer
- [ ] Motor Python responde em < 2s
- [ ] Custos de tipo de veículo são considerados
- [ ] Multi-depot funciona corretamente
- [ ] What-if evaluation retorna custos atualizados

### Database
- [ ] Tabelas `vehicle_types` e `vehicles` criadas
- [ ] Relacionamentos funcionam
- [ ] BlockAssignment.vehicleId está preenchido
- [ ] Dados persistem após reinicialização

---

## 🚀 Próximos Passos Após QA

1. **Documentação**
   - Guia de uso do Fleet Management
   - API documentation para endpoints novos
   - Troubleshooting guide

2. **Performance**
   - Otimizar queries de veículos/tipos
   - Cache de tipos de veículos
   - Índices no banco de dados

3. **UX/Design**
   - Melhorar visual do Fleet Management
   - Adicionar confirmação antes de reatribuir
   - Histórico de mudanças de alocação

4. **Funcionalidades Adicionais**
   - Atribuição de veículos a blocos (não apenas tipos)
   - Constraints de manutenção de veículos
   - Relatórios de utilização de frota

---

## 📝 Anotações

- **Data de Início FASE 1:** 2026-04-17
- **Data de Conclusão Esperada:** 2026-05-15
- **Horas Investidas:** ~40 horas de desenvolvimento
- **Componentes Criados:** 15+ novos arquivos
- **Linhas de Código:** ~3000+ (backend + frontend)
