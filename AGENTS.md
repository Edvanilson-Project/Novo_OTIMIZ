# AGENTS.md

Instrucoes obrigatorias para Codex neste repositorio OTIMIZ/OTTrans.

## Memoria operacional obrigatoria

Antes de fazer qualquer coisa neste repositorio, leia:

1. `CLAUDE.md`
2. `CLAUDE_OPERATIONAL_MEMORY.md`
3. `CLAUDE_OPERATIONAL_STATUS.md`

Esses arquivos definem o protocolo real de validacao operacional. Eles valem para
Codex tambem, nao apenas para Claude Code.

## Regra principal

Nao trate o sistema como CRUD simples. O OTIMIZ e um sistema operacional de transporte
coletivo, multiempresa, com usuarios, funcionarios, permissoes, dados historicos,
otimizacao, backend, frontend, banco, APIs, auditoria e UI real.

Antes de alterar codigo, dados, layout, seed, migracao, configuracao ou teste, execute
a validacao previa por area definida em `CLAUDE_OPERATIONAL_MEMORY.md`.

## Protocolo por tela/modulo

Para cada tela, rota, aba ou modulo:

- rode o sistema em ambiente web real quando a tarefa envolver UI;
- informe as URLs ativas para o usuario acompanhar;
- nao avance para outra tela sem esgotar a tela atual;
- inventarie todos os botoes, campos, filtros, menus, abas, tabelas, modais, acoes e
  estados visiveis;
- execute todos os CRUDs e variacoes que o sistema permitir;
- teste criacao, edicao, exclusao/inativacao, cancelamento, duplicidade, dados invalidos,
  refresh, logout/login, permissoes, filtros, ordenacao e paginacao;
- valide frontend, backend, banco, API, auth/RBAC, logs, console, rede, persistencia,
  historico, auditoria, multiempresa e funcionarios/perfis quando aplicavel;
- corrija bugs e melhorias necessarias dentro do modulo atual antes de seguir;
- reteste tudo que foi corrigido.

## Interacao obrigatoria

Toda validacao deve simular e registrar a mesa operacional OTTrans:

- 5 usuarios operacionais descritos em `CLAUDE_OPERATIONAL_MEMORY.md`;
- matriz de funcionarios/perfis quando aplicavel;
- ronda dos 17 especialistas descritos em `CLAUDE_OPERATIONAL_MEMORY.md`;
- validacao previa por area antes de mexer;
- QA tentando quebrar o fluxo;
- parecer final dos usuarios e especialistas;
- gate final de tela.

Nao produza fala generica. Cada participacao precisa gerar evidencia, decisao ou acao.
Sem evidencia, marque como `nao verificado`.

## Dados, historico e remocao

Dados operacionais importantes nao podem sumir. Preserve historico, auditoria,
rastreabilidade e integridade entre empresas, funcionarios, usuarios, linhas, viagens,
veiculos, escalas, blocos, parametros e ocorrencias.

Remova ou simplifique algo somente quando houver evidencia, consenso dos papeis
afetados, avaliacao de impacto, plano de preservacao/exclusao auditavel e reteste.

## Gate de pronto

Uma tela/modulo so esta pronto quando:

- todos os controles visiveis foram testados;
- CRUDs e fluxos alternativos foram validados;
- persistencia e historico foram confirmados;
- multiempresa/funcionarios/perfis foram validados quando aplicavel;
- bugs P0/P1 foram corrigidos ou bloqueados com motivo aceito;
- testes relevantes foram executados;
- os 5 usuarios e 17 especialistas deram parecer;
- `CLAUDE_OPERATIONAL_STATUS.md` foi atualizado.

Siga tambem as instrucoes especificas de subdiretorios, como `frontend/AGENTS.md`,
quando trabalhar dentro deles.

## Otimizador (VSP/CSP) — roadmap e invariantes (LER antes de mexer no optimizer)

Antes de tocar em qualquer algoritmo de otimizacao (`optimizer/src/algorithms/**`,
`optimizer/src/services/optimizer_service.py`) ou na comparacao com o Optibus, leia:

- `ROADMAP_SUPERAR_OPTIBUS.md` — estado atual, o que JA esta feito (nao refazer),
  backlog priorizado com COMO FAZER, playbook de validacao e pitfalls. **Mantenha-o
  atualizado** (instrucoes de manutencao no §8 do proprio arquivo).
- `artifacts/RELATORIO_OTIMIZ_vs_OPTIBUS_2026-06-04.md` — a comparacao real medida.
- `CLAUDE.md §5` — invariantes do otimizador.

Invariantes que NAO podem ser quebrados (cada um ja foi bug; ha testes que os protegem):
`max_block_span`(1440, veiculo) ≠ `max_vehicle_shift`(960, motorista); gap=0 so no mesmo
terminal com `required<=0`; particao `==1`; deadhead escalado/haversine. Detalhes e
file:line em `ROADMAP_SUPERAR_OPTIBUS.md §2`.

Estado atual (2026-06-04): Mussurunga 36 = Optibus 36; Mirantes 86 vs Optibus 82 (+4,9%);
suite 684 passed/0 failed/5 skipped. Unico caminho honesto para superar no Mirantes =
matriz de deadhead geografica real (tarefa T1 do roadmap).
