# CLAUDE_OPERATIONAL_MEMORY.md

Memoria operacional obrigatoria do projeto OTIMIZ/OTTrans.

## Regra de ativacao

Antes de qualquer tarefa neste repositorio, leia este arquivo junto com `CLAUDE.md`.
Durante trabalhos longos, leia e atualize tambem `CLAUDE_OPERATIONAL_STATUS.md`.

Esta memoria vale como protocolo de trabalho continuo. Nao comece um modulo novo sem
entender o estado atual, o que ja foi validado, o que ainda falta e quais bloqueios
continuam abertos.

## Principio central

O objetivo e amadurecer o sistema para producao com validacao operacional realista,
profunda e honesta. O trabalho deve simular o uso por pessoas de operacao da OTTrans,
com comportamento, cobrancas e feedbacks de usuarios reais, mas sem afirmar falsamente
que humanos reais executaram algo quando a validacao foi feita pelo Claude Code.

Nunca invente resultado, benchmark, comportamento do OptBus, regra operacional ou
evidencia. Quando algo nao puder ser comprovado, registre como `nao verificado`,
`pendente de fonte` ou `precisa de validacao humana`.

## Persistencia, historico e governanca de dados

Todos os dados importantes do sistema devem persistir corretamente. Dados operacionais,
historicos, auditoria, cadastros, vinculos e resultados de processamento nao podem se
perder silenciosamente.

Para cada modulo, valide explicitamente:

- dados salvos continuam existindo apos refresh, logout/login, reinicio do servico
  quando aplicavel e nova consulta pela API;
- edicoes preservam historico ou trilha de auditoria quando a informacao tiver valor
  operacional, legal, financeiro ou de diagnostico;
- exclusoes destrutivas so existem quando fizerem sentido real. Caso contrario,
  preferir inativacao, arquivamento, soft delete, status ou cancelamento auditavel;
- relacoes entre empresa, filial, usuarios, funcionarios, veiculos, linhas, viagens,
  escalas, blocos, parametros e ocorrencias permanecem integras;
- o sistema suporta cenario multiempresa/multitenant quando essa for uma premissa do
  modulo, impedindo vazamento ou mistura de dados entre empresas;
- funcionarios, perfis, permissoes e responsabilidades devem estar conectados de forma
  coerente aos fluxos operacionais;
- importacoes, otimizacoes, recalculos e correcoes nao podem apagar historico anterior
  sem decisao registrada;
- qualquer migracao, seed, limpeza ou ajuste de dados deve preservar informacao util
  ou registrar claramente o que foi removido e por que.

Se algo parecer inutil, duplicado, incorreto ou sem sentido para a operacao, a equipe
pode propor remover ou simplificar. Porem, a remocao so deve acontecer depois de:

1. evidencia do problema;
2. avaliacao de impacto em frontend, backend, banco, relatorios, otimizador e operacao;
3. concordancia registrada dos usuarios operacionais afetados;
4. parecer dos especialistas relevantes, incluindo Dados/Banco, Backend, Produto,
   QA, Seguranca/RBAC e Documentacao;
5. plano de preservacao, migracao, arquivamento ou exclusao auditavel;
6. reteste completo apos a mudanca.

O sistema deve caminhar para uma estrutura consolidada, consistente e pronta para
producao: dados confiaveis, contratos claros, modulos conectados, permissoes corretas,
historico preservado, operacao rastreavel e funcionalidades realmente necessarias.

## Trava obrigatoria de tela e modulo

E proibido passar para outra tela, rota, aba ou modulo antes de esgotar a tela atual.
O Claude Code deve tratar cada tela como uma unidade fechada de validacao.

Antes de sair da tela atual, deve existir uma evidencia registrada com:

- lista de todos os botoes, links, menus, abas, filtros, campos, tabelas, cards,
  modais, acoes em linha, acoes em massa e estados visiveis;
- status de cada controle: `testado e aprovado`, `falhou`, `nao aplicavel` ou
  `bloqueado`;
- CRUD completo quando a tela permitir cadastro, listagem, edicao, exclusao,
  detalhes, ativar/desativar, importar, exportar ou qualquer variacao equivalente;
- testes positivos, testes negativos, validacoes obrigatorias, dados invalidos,
  dados duplicados, cancelamento, confirmacao, recarregamento da pagina e persistencia;
- verificacao de console, rede, resposta da API, banco de dados quando aplicavel,
  permissao/autorizacao e comportamento visual;
- validacao de persistencia, historico, auditoria, multiempresa e vinculos com
  funcionarios quando aplicavel;
- parecer dos 5 usuarios operacionais e dos 17 especialistas, mesmo que algum diga
  `nao aplicavel para esta tela` com justificativa curta;
- bugs corrigidos e retestados, ou bloqueios documentados com motivo real.

So e permitido abrir outra tela temporariamente quando isso for necessario para
validar uma integracao da tela atual. Nesse caso, registre o motivo, faca a validacao
necessaria e volte para concluir a tela original.

Se uma tela tiver muitos recursos, divida em subfluxos e feche cada subfluxo antes de
avancar. Nao declare a tela como aprovada com botoes, filtros, menus ou CRUDs sem teste.

## Usuarios operacionais simulados

Use 5 papeis fixos de usuarios da OTTrans para validar o sistema como se estivessem
trabalhando no dia a dia:

1. Coordenador de Operacoes e Despacho: valida linhas, viagens, alocacoes, ocorrencias,
   quadro operacional, consistencia das decisoes e impacto no patio.
2. Planejador de Escala e Programacao: valida horarios, blocos, jornadas, escalas,
   restricoes trabalhistas, continuidade operacional e conflitos.
3. Fiscal de Terminal e Campo: valida terminais, pontos, partidas, chegadas,
   regularidade, atrasos, eventos reais de operacao e usabilidade em rotina rapida.
4. Analista de Frota e Manutencao: valida veiculos, disponibilidade, capacidade,
   restricoes, manutencao, substituicoes e compatibilidade com a programacao.
5. Administrativo, Controle e Auditoria: valida empresas, usuarios, permissoes,
   parametros, relatorios, rastreabilidade, cadastros e governanca.

Cada papel deve registrar feedback com: expectativa, acao feita, resultado observado,
problema encontrado, impacto operacional e decisao.

### Mesa operacional OTTrans obrigatoria

Em toda validacao de tela ou modulo, os 5 usuarios operacionais devem interagir entre
si e com os especialistas. Nao basta citar que eles existem. Cada um deve registrar
uma participacao objetiva no formato:

- Quem falou:
- Perfil OTTrans:
- Fluxo executado ou analisado:
- O que esperava na rotina real:
- O que encontrou no sistema:
- Risco para a operacao:
- Pedido para especialistas:
- Decisao: `aprovado`, `aprovado com observacao`, `reprovado` ou `nao aplicavel`.

Quando o modulo envolver funcionarios, usuarios, permissoes, jornadas, motoristas,
fiscais, operadores, administradores ou gestores, crie tambem uma matriz de funcionarios
e perfis envolvidos. Essa matriz deve mostrar:

- funcionario/persona operacional;
- empresa/filial/garagem vinculada;
- cargo ou funcao;
- perfil de acesso;
- o que pode fazer;
- o que nao pode fazer;
- dados que consegue ver;
- dados que nao pode ver;
- acoes testadas no sistema;
- resultado observado.

O sistema deve ser validado como multiempresa e multifuncionario sempre que o modulo
tocar usuarios, empresas, funcionarios, permissoes, dados operacionais ou relatorios.
Teste pelo menos estes cenarios quando aplicavel:

- usuario administrador da empresa principal;
- usuario operacional de uma empresa/filial;
- usuario sem permissao para o recurso;
- funcionario vinculado a uma funcao operacional;
- tentativa de acessar, editar ou excluir dado de outra empresa;
- troca de perfil/permissao e reteste do acesso.

Se a base ainda nao tiver funcionarios ou perfis suficientes, crie dados sinteticos
realistas ou registre o bloqueio e implemente o necessario dentro do modulo atual.

## Conselho de especialistas

Quando houver analise, validacao, bug, melhoria ou decisao tecnica, convoque os 17
especialistas abaixo. Eles devem responder com base em evidencia, testes e codigo,
sem exagero e sem certeza falsa:

1. Arquiteto de Sistema
2. Especialista de Produto em Operacao de Transporte
3. Matematico de Otimizacao Combinatoria
4. Estatistico e Analista de KPIs
5. Especialista em OptBus, VSP, CSP e benchmarks de mercado
6. Engenheiro Backend
7. Engenheiro Frontend
8. UI/UX Designer
9. QA Engineer e Especialista E2E
10. Engenheiro de Dados e Banco de Dados
11. DevOps e Infraestrutura
12. Especialista em Seguranca, Auth e RBAC
13. Especialista em Performance e Escala
14. Especialista em Integracoes e APIs
15. Especialista em Regras Trabalhistas e Compliance Operacional Brasil
16. Especialista em Observabilidade, Logs e Auditoria
17. Documentador Tecnico e Release Manager

O padrao esperado e maximo rigor profissional. Os especialistas nao devem "chutar".
Se faltar informacao, devem declarar a lacuna e pedir ou produzir a evidencia necessaria.

### Validacao previa obrigatoria por area

Antes de alterar codigo, dados, layout, configuracao, seed, migracao, regra de negocio
ou teste, a equipe deve fazer uma validacao previa da tela/modulo atual. Nenhuma
correcao deve ser feita por achismo.

Cada especialista deve primeiro validar o que ja existe na sua area, registrar a
evidencia e so entao propor ou executar mudanca. A validacao previa minima e:

- Backend: revisar endpoints, controllers, services, DTOs, validacoes, regras de
  negocio, status HTTP, erros, auth/RBAC, transacoes, persistencia e logs.
- Frontend: revisar componentes, estado, chamadas de API, loading, tratamento de erro,
  formularios, validacoes, navegacao, refresh e sincronizacao com backend.
- UI/UX Designer: revisar hierarquia visual, clareza do fluxo, textos, labels, botoes,
  estados vazios, estados de erro, responsividade, acessibilidade basica e consistencia.
- QA/E2E: mapear cenarios positivos, negativos, limites, regressao, CRUD completo,
  permissoes, refresh, duplo clique, cancelamento e reteste obrigatorio.
- Dados/Banco: revisar entidades, tabelas, relacoes, constraints, seeds, integridade,
  historico, auditoria, soft delete/inativacao e risco de perda de dados.
- Seguranca/Auth/RBAC: revisar login, token, permissoes, isolamento multiempresa,
  dados expostos, tentativa de acesso indevido e acoes proibidas.
- Performance/Escala: revisar consultas caras, paginacao, volume de dados, renderizacao,
  latencia, N+1, payloads grandes e riscos de travamento.
- Produto/Operacao: revisar se o fluxo corresponde a rotina real da OTTrans e se
  resolve o trabalho de usuarios e funcionarios envolvidos.
- Matematica/Otimizacao: revisar parametros, restricoes, calculos, consistencia dos
  resultados e impacto em VSP/CSP quando aplicavel.
- DevOps/Infra: revisar ambiente, containers, portas, variaveis, dependencias, logs
  de execucao e reproducibilidade local.
- Integracoes/APIs: revisar contratos, payloads, compatibilidade, erros e consumidores.
- Compliance Operacional Brasil: revisar jornadas, limites, regras trabalhistas e
  rastreabilidade quando aplicavel.
- Observabilidade: revisar se erro, acao importante e decisao operacional deixam
  log, auditoria ou evidencia suficiente para diagnostico.
- Documentacao/Release: revisar se a mudanca, evidencia, pendencia e decisao ficam
  registradas para continuidade.

Formato obrigatorio da validacao previa:

- Especialista:
- Obrigacoes da area nesta tela/modulo:
- Evidencia analisada:
- O que ja funciona:
- O que falha ou falta:
- Risco se nao corrigir:
- Acao recomendada:
- Pode mexer agora? `sim`, `nao` ou `precisa de mais evidencia`.

Se qualquer especialista responder `nao` ou `precisa de mais evidencia`, a equipe deve
buscar a evidencia, ajustar o plano ou corrigir o bloqueio antes de seguir para outra
tela. Quando a correcao for necessaria para obter evidencia, registre isso claramente.

### Participacao obrigatoria dos especialistas

Nenhum especialista pode ficar silencioso em uma validacao de tela ou modulo. Todos
devem participar com um parecer objetivo, baseado no papel de cada um:

- Arquiteto de Sistema: verifica coerencia entre modulo, dominio, contratos e limites.
- Produto em Operacao de Transporte: verifica se o fluxo resolve a rotina real da OTTrans.
- Matematico de Otimizacao: verifica restricoes, parametros, consistencia de calculos
  e impacto nos motores VSP/CSP quando aplicavel.
- Estatistico/KPIs: verifica indicadores, totais, contagens, filtros e interpretacao.
- OptBus/Benchmarks: compara somente com fonte ou conhecimento documentado; caso
  contrario marca como pendente.
- Backend: valida endpoints, DTOs, regras, erros, logs, transacoes e persistencia.
- Frontend: valida estado, integracao API, loading, erros, navegacao e componentes.
- UI/UX Designer: valida hierarquia visual, clareza, densidade, responsividade,
  acessibilidade basica, textos, botoes, espacamento, estados vazios e estados de erro.
- QA/E2E: tenta quebrar o fluxo, cobre caminhos felizes e alternativos, e define reteste.
- Dados/Banco: valida schema, chaves, relacionamentos, queries, seeds e integridade.
- DevOps/Infra: valida configuracao, ambiente, containers, portas, envs e execucao.
- Seguranca/Auth/RBAC: valida login, permissoes, bloqueios e exposicao indevida.
- Performance/Escala: valida latencia, paginacao, volume, renderizacao e consultas caras.
- Integracoes/APIs: valida contratos, formatos, status HTTP, payloads e compatibilidade.
- Compliance Operacional Brasil: valida regras trabalhistas, jornadas e limites aplicaveis.
- Observabilidade: valida logs, erros rastreaveis, auditoria e diagnostico.
- Documentacao/Release: registra o que mudou, evidencias, pendencias e readiness.

Cada especialista deve terminar com uma das decisoes: `aprovado`, `aprovado com
observacao`, `reprovado` ou `nao aplicavel`, sempre com motivo. Se reprovar, a equipe
deve corrigir ou registrar bloqueio antes de seguir.

### Ronda obrigatoria dos 17 especialistas

Em toda tela ou modulo, execute uma ronda explicita com os 17 especialistas. A tela
nao pode ser aprovada se algum especialista nao tiver parecer registrado.

Formato obrigatorio para cada especialista:

- Especialista:
- Area analisada:
- Evidencia vista: arquivo, tela, API, log, banco, teste ou comportamento observado;
- Problema encontrado:
- Correcao ou melhoria exigida:
- Responsavel tecnico pela correcao:
- Reteste exigido:
- Decisao: `aprovado`, `aprovado com observacao`, `reprovado` ou `nao aplicavel`.

Quando um especialista marcar `nao aplicavel`, deve explicar por que aquela area nao
se aplica a tela. `Nao aplicavel` sem motivo nao vale como parecer.

Se UI/UX reprovar, ajuste a interface antes de seguir. Se Backend reprovar, ajuste API,
regra ou persistencia antes de seguir. Se QA reprovar, corrija e reteste. Se Dados/Banco
reprovar, corrija integridade, relacionamento, schema, seed ou migracao. Se Seguranca
reprovar, corrija permissao, isolamento, autenticacao ou exposicao de dados. Se Produto
ou usuarios operacionais reprovarem, corrija o fluxo para refletir a rotina real.

## Comunicacao intensa obrigatoria

Durante a validacao, simule uma comunicacao continua entre usuarios operacionais e
especialistas. A comunicacao deve acontecer em ciclos curtos:

1. Usuario operacional executa ou descreve o fluxo real.
2. Especialistas analisam cada um sua parte.
3. Problemas viram tarefas imediatas de correcao dentro do mesmo modulo.
4. Backend, frontend, UI/UX, dados, QA e demais responsaveis corrigem suas partes.
5. QA retesta o fluxo quebrado.
6. Usuarios operacionais confirmam se a rotina real ficou correta.
7. Especialistas dao parecer final.

Nao aceite validacao passiva. O time deve procurar bugs ativamente: clicar em tudo,
testar campos obrigatorios, dados invalidos, dados extremos, acoes repetidas, duplo
clique em salvar, cancelar no meio do fluxo, editar todos os campos possiveis, excluir,
recriar, filtrar, ordenar, paginar, recarregar, voltar pelo navegador e verificar se
o sistema continua coerente.

### Registro minimo da interacao

Para cada tela, registre no `CLAUDE_OPERATIONAL_STATUS.md` ou em relatorio proprio:

- rodada dos 5 usuarios operacionais;
- matriz de funcionarios/perfis quando aplicavel;
- perguntas que os usuarios fizeram aos especialistas;
- respostas objetivas dos especialistas;
- bugs encontrados pela interacao;
- quem corrigiu cada problema: Frontend, Backend, UI/UX, Dados, QA, Seguranca etc.;
- evidencia do reteste;
- parecer final de cada usuario e de cada um dos 17 especialistas.

Sem esse registro de interacao, a tela continua `em andamento` mesmo que pareca
funcionar visualmente.

### Protocolo anti-teatro de reuniao

A interacao entre usuarios OTTrans e especialistas deve gerar evidencia, decisao e
acao. Nao vale produzir falas longas, genericas ou repetitivas sem teste real.

Cada participacao deve cumprir pelo menos uma destas funcoes:

- validar um comportamento observado na UI, API, banco, log ou teste;
- encontrar um bug, risco, lacuna, melhoria ou inconsistencia;
- confirmar que uma obrigacao da area foi atendida com evidencia;
- declarar `nao aplicavel` com motivo tecnico ou operacional;
- pedir uma correcao objetiva com responsavel e reteste.

Se a fala nao mudar nada na validacao, nao ajuda o projeto. Substitua por um parecer
curto, verificavel e acionavel.

### Ordem obrigatoria da interacao por tela

Use esta ordem para cada tela ou subfluxo:

1. Contexto da tela: objetivo, rota, modulo, dados usados e criterio de aprovacao.
2. Inventario visual: listar controles, campos, botoes, menus, tabelas e estados.
3. Rodada dos 5 usuarios OTTrans: cada usuario executa ou avalia sua rotina real.
4. Matriz de funcionarios/perfis: quando aplicavel, validar permissoes e isolamento.
5. Validacao previa dos especialistas: cada area valida suas obrigacoes antes de mexer.
6. Teste destrutivo controlado: QA tenta quebrar CRUD, filtros, permissoes e estados.
7. Correcao imediata: responsavel corrige bug ou implementa melhoria necessaria.
8. Reteste: QA, usuario afetado e especialista da area confirmam a correcao.
9. Ronda final dos 17 especialistas: parecer objetivo e decisao por area.
10. Gate final: tela fica `aprovada`, `aprovada com observacao`, `bloqueada` ou
    `reprovada`.

### Evidencias obrigatorias

Sempre que possivel, registre evidencias concretas:

- rota/tela testada;
- usuario/perfil usado;
- dados de entrada criados/editados/excluidos/inativados;
- IDs de registros, quando disponiveis;
- chamadas de API relevantes e status HTTP;
- resultado no banco ou resposta da API;
- erros de console/rede/logs;
- prints ou descricao objetiva do comportamento visual;
- comando de teste executado e resultado;
- arquivo alterado e motivo da alteracao;
- reteste que provou a correcao.

Sem evidencia, o item deve ficar como `nao verificado`.

### Severidade, dono e prazo tecnico

Todo problema encontrado deve receber classificacao:

- `P0 bloqueante`: impede uso do modulo, quebra dado, seguranca ou fluxo essencial.
- `P1 alto`: fluxo importante falha, mas existe contorno temporario.
- `P2 medio`: problema funcional, visual ou operacional que reduz confianca.
- `P3 baixo`: melhoria, polimento, texto, consistencia ou experiencia.

Todo problema deve ter:

- ID: `BUG-MODULO-XX`, `RISK-MODULO-XX`, `UX-MODULO-XX` ou `DATA-MODULO-XX`;
- dono: Backend, Frontend, UI/UX, QA, Dados, Seguranca, Produto, DevOps etc.;
- evidencia;
- correcao esperada;
- status: `aberto`, `corrigido`, `retestado`, `bloqueado` ou `adiado com motivo`;
- decisao de seguir ou nao seguir.

P0 e P1 impedem avancar para outra tela/modulo, salvo bloqueio externo documentado e
aceito explicitamente pelo usuario.

### Gate final de tela

A tela so pode sair de `em andamento` quando o gate final estiver preenchido:

- Tela/rota:
- Dados testados:
- Perfis testados:
- CRUD completo: `sim`, `nao aplicavel` ou `bloqueado`;
- Persistencia/historico validado:
- Multiempresa/funcionarios validado:
- Bugs P0/P1 abertos:
- Bugs P2/P3 abertos:
- Usuarios OTTrans: decisoes finais dos 5 papeis;
- Especialistas: decisoes finais dos 17 papeis;
- Testes executados:
- Evidencias principais:
- Decisao final:
- Proxima tela permitida:

Se qualquer campo obrigatorio estiver vazio, a tela continua `em andamento`.

## Ciclo obrigatorio por modulo

Para cada modulo do sistema:

1. Leia `CLAUDE_OPERATIONAL_STATUS.md` e confirme o estado atual.
2. Defina o escopo do modulo e os criterios de aprovacao.
3. Execute a validacao previa obrigatoria por area antes de mexer em codigo ou dados.
4. Rode o sistema em ambiente real de desenvolvimento, preferencialmente via navegador,
   para que o usuario possa acompanhar. Informe as URLs ativas quando iniciar servidor.
5. Entre na UI real e teste todos os botoes, links, abas, menus, filtros, buscas,
   paginacao, importacoes, exportacoes, salvar, cancelar, editar, excluir, confirmar,
   voltar, limpar, estados vazios, erros de validacao e permissoes.
6. Execute todos os CRUDs possiveis com dados realistas de operacao, nao com lorem ipsum.
7. Confirme integracao entre frontend, backend, banco, autenticacao, permissoes,
   parametros, logs e persistencia apos recarregar a pagina.
8. Verifique erros de console, rede, API, validacao, estado visual e comportamento
   responsivo quando isso fizer sentido para o modulo.
9. Compare com OptBus e sistemas similares somente quando houver fonte, documento,
   comportamento conhecido no projeto ou informacao fornecida pelo usuario. Caso
   contrario, marque a comparacao como pendente.
10. Registre o que funciona, o que nao funciona, o que falta, impacto operacional,
   evidencia usada e recomendacao.
11. Quando encontrar bug, quebra, ausencia de botao, CRUD incompleto, inconsistencia
    visual ou melhoria necessaria, corrija ou implemente imediatamente dentro do
    modulo atual.
12. Apos corrigir, rode testes automatizados, validacao manual no navegador e reteste
    o fluxo que falhou.
13. Nao mude para outro modulo enquanto o modulo atual nao estiver aprovado ou enquanto
    os bloqueios nao estiverem documentados de forma clara.
14. Quando o modulo estiver aprovado pelos papeis operacionais e especialistas
    relevantes, atualize a memoria de status e faca commit somente do que pertence
    ao modulo validado, se o usuario permitiu ou pediu commits.

## Checklist minimo por tela

Antes de declarar uma tela validada, execute e registre:

- carregamento inicial, estado vazio, estado com dados e estado de erro;
- criacao com dados validos;
- tentativa de criacao com campos obrigatorios vazios;
- tentativa de criacao com formatos invalidos e duplicidades;
- listagem, busca, filtros, ordenacao e paginacao;
- abertura de detalhes, quando existir;
- edicao de cada grupo de campos editaveis;
- cancelamento de edicao e confirmacao de que nada indevido foi salvo;
- exclusao ou inativacao, com confirmacao e cancelamento;
- recriacao ou reativacao quando o sistema permitir;
- persistencia apos refresh;
- permissao de acesso por perfil, quando existir RBAC;
- mensagens de sucesso, erro, loading e validacao;
- layout desktop e, quando aplicavel, responsivo;
- console do navegador sem erro relevante;
- chamadas de rede com status e payload corretos;
- banco ou API confirmando que o dado final esta correto.
- historico, auditoria, inativacao/exclusao e vinculos multiempresa/funcionarios
  verificados quando a tela envolver esses dados.

## Dados de teste

Use cadastros plausiveis e completos de uma operacao de transporte:

- empresas, filiais, garagens, usuarios e perfis;
- linhas, terminais, pontos, itinerarios e tabelas horarias;
- veiculos, capacidades, disponibilidade e restricoes;
- motoristas, jornadas, folgas, regras e conflitos;
- viagens, blocos, escalas, alocacoes, ocorrencias e relatorios.

Nao use dados pessoais reais sensiveis sem autorizacao. Quando criar massa de teste,
identifique como dado sintetico realista.

## Comunicacao obrigatoria

Mantenha comunicacao clara e continua entre usuarios operacionais e especialistas.
Use linguagem direta, realista e sincera. Nao dramatize, nao finja certeza e nao omita
problemas.

Formato recomendado para registros:

- Modulo:
- Papel ou especialista:
- Acao:
- Esperado:
- Observado:
- Evidencia:
- Status:
- Correcao feita:
- Reteste:
- Proxima decisao:

## Definicao de pronto

Um modulo so pode ser considerado pronto quando:

- todos os fluxos previstos no modulo foram percorridos;
- todos os botoes e controles visiveis foram testados;
- CRUDs principais e alternativos foram validados;
- cada tela do modulo teve checklist proprio, com controles inventariados e status;
- existe validacao previa registrada por area antes das alteracoes;
- os 5 usuarios operacionais deram feedback;
- os 17 especialistas deram parecer objetivo;
- existe registro de interacao entre usuarios OTTrans, funcionarios/perfis aplicaveis
  e os 17 especialistas;
- erros encontrados foram corrigidos ou documentados como bloqueio real;
- frontend, backend, banco, auth e permissoes respondem de forma coerente;
- dados persistem corretamente;
- historico, auditoria e dados operacionais importantes nao se perdem;
- multiempresa, funcionarios, perfis e permissoes estao coerentes quando aplicavel;
- qualquer remocao ou simplificacao de dados/funcionalidade teve consenso registrado
  e reteste completo;
- nao ha erro relevante no console, rede ou logs;
- testes automatizados pertinentes foram executados e registrados;
- validacao operacional realista foi registrada;
- `CLAUDE_OPERATIONAL_STATUS.md` foi atualizado.

## Memoria de status

`CLAUDE_OPERATIONAL_STATUS.md` deve ser mantido como log vivo com:

- modulo atual;
- fluxos validados;
- cadastros e massa de teste criados;
- bugs encontrados;
- correcoes feitas;
- testes e comandos executados;
- evidencias importantes;
- decisoes tomadas;
- pendencias;
- commit feito;
- proximo modulo.

Se o arquivo nao existir, crie antes de iniciar a primeira validacao operacional.
