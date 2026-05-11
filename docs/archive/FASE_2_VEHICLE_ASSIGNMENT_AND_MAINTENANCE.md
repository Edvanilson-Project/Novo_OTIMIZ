# FASE 2 - Atribuição de Veículos e Restrições de Manutenção

## 📋 Objetivo
Implementar sistema completo de atribuição de veículos específicos aos blocos (não apenas tipos) com suporte a constraints de manutenção, permitindo otimização mais realista das operações.

## 🎯 Scope FASE 2

### FASE 2.1: Vehicle-to-Block Assignment Database Schema
**Objetivo:** Permitir atribuição de veículos específicos aos blocos, com histórico de alocações.

**Tarefas:**
- [ ] Adicionar `vehicleId` (FK) a BlockAssignment (já existe, apenas documentar)
- [ ] Criar tabela `vehicle_maintenance` com campos:
  - `id` (PK)
  - `vehicleId` (FK)
  - `maintenanceDate` (DATE)
  - `maintenanceType` (enum: preventive, corrective, inspection)
  - `estimatedDurationHours` (int)
  - `cost` (decimal)
  - `status` (enum: scheduled, in_progress, completed, cancelled)
- [ ] Criar tabela `vehicle_availability_windows` com campos:
  - `id` (PK)
  - `vehicleId` (FK)
  - `startTime` (DATETIME)
  - `endTime` (DATETIME)
  - `reason` (string: maintenance, inspection, fuel, etc)
- [ ] Relacionamentos OneToMany: Vehicle → Maintenance, Vehicle → AvailabilityWindows
- [ ] Migrations TypeORM

**Validações:**
- ✅ Tabelas criadas com índices
- ✅ Relacionamentos funcionam
- ✅ Dados persistem após reinicialização

---

### FASE 2.2: Backend API para Manutenção de Veículos
**Objetivo:** Endpoints para gerenciar manutenção e disponibilidade de veículos.

**Tarefas:**
- [ ] VehicleMaintenanceController com endpoints:
  - `POST /vehicles/:id/maintenance` - Agendar manutenção
  - `GET /vehicles/:id/maintenance` - Listar histórico
  - `PATCH /vehicles/:id/maintenance/:maintenanceId` - Atualizar status
  - `DELETE /vehicles/:id/maintenance/:maintenanceId` - Cancelar manutenção
- [ ] VehicleMaintenanceService com métodos:
  - `scheduleMaintenance(vehicleId, maintenanceData)`
  - `getMaintenanceHistory(vehicleId)`
  - `getUnavailablePeriods(vehicleId)`
  - `checkVehicleAvailability(vehicleId, startTime, endTime)`
- [ ] Validações:
  - Não permitir manutenção em mesmo período
  - Validar duração mínima
  - Não permitir agendar no passado

**Testes Unitários:**
- [ ] VehicleMaintenanceService: 15+ testes
- [ ] Validação de conflitos de manutenção
- [ ] Cálculo de períodos indisponíveis

**Validações:**
- ✅ API endpoints funcionam
- ✅ Todas as validações passam
- ✅ 15+/15 testes unitários

---

### FASE 2.3: Optimizer Integration - Maintenance Constraints
**Objetivo:** Python optimizer respeita restrições de manutenção.

**Tarefas:**
- [ ] Modificar `mcnf.py`:
  - Adicionar `vehicle_availability` ao payload
  - Verificar disponibilidade antes de atribuir veículo
  - Penalizar alocações que requerem manutenção durante turno
- [ ] Modificar `evaluator.py`:
  - Calcular custo de manutenção adiada
  - Verificar conflitos de manutenção
  - Retornar warnings se manutenção não pode ser realizada
- [ ] Adicionar `maintenance_report` ao output:
  - Veículos com manutenção pendente
  - Veículos indisponíveis em cada turno
  - Custos de manutenção adiada

**Testes Python:**
- [ ] test_vehicle_maintenance_constraints.py: 12+ testes
- [ ] Validar que veículos em manutenção não são atribuídos
- [ ] Validar custos de manutenção no resultado

**Validações:**
- ✅ Optimizer responde com maintenance_report
- ✅ Restrições de manutenção funcionam
- ✅ 12+/12 testes Python passam

---

### FASE 2.4: Frontend - Vehicle Assignment & Maintenance Dashboard
**Objetivo:** Interface para gerenciar atribuições de veículos e agendamentos de manutenção.

**Tarefas:**
- [ ] Criar `VehicleAssignmentPanel.tsx`:
  - Mostrar veículo atribuído a cada bloco
  - Dropdown para mudar veículo
  - Validação de disponibilidade em tempo real
  - Indicadores visuais de status
- [ ] Criar `MaintenanceScheduler.tsx`:
  - Calendário com datas de manutenção
  - Dialog para agendar manutenção
  - Histórico de manutenções
  - Status em tempo real
- [ ] Atualizar `VehicleAssignmentDashboard`:
  - Incorporar ambos componentes
  - Timeline mostrando blocos e manutenção
  - Alertas de conflitos
- [ ] Atualizar `TripDragDropEditor`:
  - Mostrar veículo atual do bloco
  - Validar compatibilidade ao mover trip
  - Avisar sobre manutenção programada

**Componentes:**
- [ ] VehicleAssignmentPanel (novo)
- [ ] MaintenanceScheduler (novo)
- [ ] MaintenanceCalendar (novo)
- [ ] VehicleHealthStatus (novo)

**Testes Frontend:**
- [ ] Components carregam sem erros
- [ ] Drag & drop respeta disponibilidade
- [ ] Maintenance calendar funciona
- [ ] Sem console errors

**Validações:**
- ✅ Dashboard carrega dados
- ✅ Operações CRUD funcionam
- ✅ UI responsivo (mobile-friendly)
- ✅ Sem TypeScript errors

---

### FASE 2.5: Advanced Vehicle Tracking Features
**Objetivo:** Melhorar rastreamento e análise de veículos.

**Tarefas:**
- [ ] Adicionar `VehicleMetrics`:
  - Quilometragem média por dia
  - Taxa de utilização (horas ativas / horas disponíveis)
  - Custo operacional por km
  - Próxima manutenção prevista
- [ ] Criar `VehicleHealthScore`:
  - Score de 0-100 baseado em:
    - Tempo desde última manutenção
    - Quilometragem acumulada
    - Histórico de problemas
    - Idade do veículo
- [ ] Dashboard `VehicleFleetAnalytics`:
  - Mostrar health score de cada veículo
  - Prever manutenções necessárias
  - Recomendações de reparos/substituição
  - ROI de cada veículo

**Testes:**
- [ ] Cálculos de métricas: 10+ testes
- [ ] Health score logic: 8+ testes

**Validações:**
- ✅ Métricas calculadas corretamente
- ✅ Health scores realistic
- ✅ Dashboard renderiza corretamente

---

### FASE 2.6: Integration Testing & Validation
**Objetivo:** Validar que todo sistema funciona com vehicle assignment e maintenance.

**Testes E2E:**
1. **Agendar manutenção e validar impacto**
   - Agendar manutenção para veículo
   - Rodar otimização
   - Validar que veículo não é atribuído durante manutenção
   - Validar cost impact

2. **Vehicle assignment com múltiplos cenários**
   - Mudar atribuição de veículo via UI
   - Validar cost recalculation
   - Validar que trips permanecem válidas

3. **Maintenance rescheduling impact**
   - Agendar manutenção que causa conflito
   - Sistema deve sugerir adiamento
   - Validar custos alternativos

4. **Fleet health analytics**
   - Rodar otimização
   - Verificar health scores
   - Validar recomendações de manutenção

**Validações:**
- ✅ 4/4 cenários validados
- ✅ Manutenção constraints funcionam
- ✅ Cost calculations corretos
- ✅ Zero regressões em FASE 1

---

## 📊 Métricas de Sucesso

| Métrica | Target | Status |
|---------|--------|--------|
| Database Schema | Completo | ⏳ Pendente |
| API Endpoints | 4+ endpoints | ⏳ Pendente |
| Unit Tests Backend | 15+/15 | ⏳ Pendente |
| Optimizer Integration | Constraints ok | ⏳ Pendente |
| Python Tests | 12+/12 | ⏳ Pendente |
| Frontend Components | 4 novos | ⏳ Pendente |
| E2E Tests | 4/4 cenários | ⏳ Pendente |

---

## 🔍 Checklist FASE 2

### FASE 2.1 Database
- [ ] Tabelas criadas (vehicle_maintenance, vehicle_availability_windows)
- [ ] Relacionamentos configurados
- [ ] Índices criados
- [ ] Migrations executadas

### FASE 2.2 Backend API
- [ ] Controllers criados
- [ ] Services implementados
- [ ] 15+ testes unitários passando
- [ ] Endpoints testados com curl

### FASE 2.3 Optimizer
- [ ] mcnf.py atualizado
- [ ] evaluator.py atualizado  
- [ ] 12+ testes Python passando
- [ ] maintenance_report no output

### FASE 2.4 Frontend
- [ ] VehicleAssignmentPanel funcional
- [ ] MaintenanceScheduler funcional
- [ ] Dashboard integrado
- [ ] Sem TypeScript errors

### FASE 2.5 Advanced Features
- [ ] Métricas calculadas
- [ ] Health scores funcionam
- [ ] Analytics dashboard renderiza

### FASE 2.6 Integration
- [ ] 4 cenários E2E validados
- [ ] Sem regressões FASE 1
- [ ] Sistema estável

---

## 📝 Notas

- **Data de Início FASE 2:** 2026-05-02
- **Duração Estimada:** ~50-60 horas de desenvolvimento
- **Componentes Novos:** 5+ backend, 4 frontend, 2 Python modules
- **Compatibilidade:** Todas mudanças mantêm compatibilidade com FASE 1
