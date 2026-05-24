# AUDITORIA IMPORTAR VIAGENS — 2026-05-24

## Contexto
- **Tela**: `/operations/data`
- **Módulo**: Gestão de Dados Operacionais — Importar Viagens (CSV)
- **Objetivo**: Validar import, validação, persistência, CRUD de viagens
- **Ambiente**: Frontend (localhost:3000), Backend (localhost:3001)
- **Data**: 2026-05-24
- **Usuário**: admin@empresa.com (Super Admin)

---

## 1. INVENTÁRIO VISUAL

### Header
| Elemento | Status |
|---|---|
| Breadcrumb "Operações > Importar Viagens" | ✅ |
| Título "Gestão de Dados Operacionais" | ✅ |
| Subtítulo "Gerencie viagens e motoristas..." | ✅ |

### Abas
| Aba | Status | Descrição |
|---|---|---|
| Viagens | ✅ Ativa | Grid principal com 10 viagens |
| Motoristas | ✅ Disponível | Não testado ainda |

### Botões de Ação
| Botão | Cor | Status | Ícone |
|---|---|---|---|
| Recarregar | - | ✅ | Refresh |
| + Nova Viagem | Azul | ✅ | Plus |
| Importar (10) | Vermelho | ✅ | Mostra quantidade de viagens |
| Importar GTFS | Azul | ✅ | Upload |
| Exportar Layout | Azul | ✅ | Download |
| Importar Viagens | Azul (principal) | ✅ | Upload |

### Grid de Viagens Carregadas (10)

**Título**: "Viagens Carregadas (10)"

**Colunas Visíveis**:
| Coluna | Tipo | Exemplo | Status |
|---|---|---|---|
| Trip ID | Texto | 1, 2 | ✅ |
| Linha | Badge | 1201 (all) | ✅ |
| Par | Texto | – (vazio) | ✅ |
| Sentido | Badge | IDA / VOLTA | ✅ |
| Início | Hora | 06:00, 06:40, 07:00... | ✅ |
| Fim | Hora | 06:30, 07:10, 07:30... | ✅ |
| Dur(min) | Número | 30 (todas) | ✅ |
| Origem | Número | 3, 4 | ✅ |
| Destino | Número | 4, 3 | ✅ |
| Km | Número | 15 (todas) | ✅ |
| Ações | Ícones | Editar, Deletar | ✅ |

### Dados Visíveis
- 8 viagens renderizadas (com scroll para mais)
- Total: 10 viagens (indicado em "Importar (10)" e título)
- Padrão: Linha 1201, sensido IDA/VOLTA alternado, 30 min cada, origem 3/4, destino 4/3

### Problemas Visuais
- ❌ Nenhum detectado até agora
- Layout limpo, legível em dark theme
- Grid scrollável, sem quebras

---

## 2. TESTES PLANEJADOS

### 2.1 Funcionalidades Import/Export
- [ ] Clique em "Importar Viagens" — abrir upload dialog
- [ ] Clique em "Exportar Layout" — baixar arquivo
- [ ] Clique em "Importar GTFS" — abrir GTFS dialog
- [ ] Clique em "Importar (10)" — ação de reimportar existentes?

### 2.2 CRUD de Viagens
- [ ] Clique em ícone Editar (lápis) em uma viagem
- [ ] Clique em ícone Deletar (lixo) em uma viagem
- [ ] Clique em "+ Nova Viagem" — novo form
- [ ] Salvar nova viagem — persistência

### 2.3 Grid Interativo
- [ ] Scroll horizontal — todos os dados visíveis
- [ ] Scroll vertical — todas as 10 viagens carregam
- [ ] Recarregar (refresh) — dados persistem?
- [ ] Filtros/Busca (se existir) — funciona?

### 2.4 Aba Motoristas
- [ ] Clique na aba "Motoristas"
- [ ] Listar motoristas cadastrados
- [ ] Editar motorista
- [ ] Deletar motorista

### 2.5 Persistência
- [ ] Refresh F5 — dados mantêm 10 viagens?
- [ ] Logout/Login — dados persistem?
- [ ] Multiempresa — dados isolados?

---

## 3. OBSERVAÇÕES INICIAIS

### Positivas ✅
- Grid carrega com 10 viagens corretamente
- Layout limpo e intuitivo
- Botões bem posicionados e nomeados
- Dados aparecem estruturados (Linha, Sentido, Horários, etc.)
- Dark theme legível

### Questões ❓
- Campo "Par" está vazio (–) para todas as viagens — é esperado?
- "Importar (10)" é um botão ou link? Qual a ação?
- Como funciona "Importar GTFS" vs "Importar Viagens"?

---

## 4. PRÓXIMOS PASSOS

1. Executar testes de clique nos botões principais
2. Testar edição/deleção de viagem
3. Verificar persistência após refresh
4. Aba Motoristas
5. Ronda dos 5 usuários OTTrans
6. Ronda dos 17 especialistas
7. Gate final

---

**Status Atual**: ✅ Inventário visual concluído, grid carrega 10 viagens  
**Próximo**: Testes de funcionalidade (cliques, edição, CRUD)
