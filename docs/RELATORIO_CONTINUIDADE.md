# Relatório de Continuidade

Atualizado em 2026-11-04. Este documento resume o estado conhecido do projeto para a próxima IA ou pessoa desenvolvedora. Leia também `docs/DECISOES.md`, `docs/MODELOS.md` e `docs/COBERTURA.md` antes de alterar regras ou modelos.

## Estado do repositório

- Projeto: Django para campanha de Ordem Paranormal RPG, workspace `MONOTOFOBIA`.
- Branch: `main`; checklist reavaliada sobre o estado publicado `8dddfff` em `origin/main`.
- Commits publicados nesta rodada:
  - `8dddfff` `docs: record combat condition restrictions release`
  - `d854d28` `feat: enforce condition action restrictions in combat`
  - `fc283ba` `docs: record timed condition release`
  - `2e38cc9` `feat: add per-condition combat turn durations`
  - `611d27b` `fix: validate condition effects when loading rules`
  - `7ec7639` `feat: validate power prerequisites and expire scene conditions`
  - `4faacfc` `feat: complete campaign management foundations`
- Commits anteriores de fase:
  - `62783a4` `feat(fichas): add rules core and PDF prep`
  - `9c85fcf` `feat(rules): load core catalogs and origins`
  - `1ac6932` `feat(fichas): implement character creation and sheet UI`
  - `3e87251` `feat(fichas): add NEX advancement workflow`
  - `71ab982` `feat(fichas): add manual inventory management`
  - `f62d0fc` `feat(fichas): add table settings and active sheet limits`
- Os commits publicados passaram pelos hooks Gitleaks e Bandit. O usuário solicitou commit e push para esta rodada; dados locais e catálogos licenciados continuam fora do Git.
- Em 2026-11-04, o proprietário informou que tornou o remoto GitHub privado. Ainda não armazene conteúdo de terceiros sem autorização; acesso privado não altera direitos autorais.

## Checklist das fases (revisada em 2026-11-04)

**Legenda:** ✅ concluída no escopo descrito; 🟡 parcial; ⬜ pendente. “Concluída” refere-se aos recursos enumerados, não a uma garantia de segurança ou prontidão de produção.

| Fase | Status | Já feito no sistema | Ainda falta |
|---|---|---|---|
| 0 — Correções e fundações | ✅ | Autenticação/permissões, base de fichas, rolagens físicas/digitais, recursos auditados, verificações de migração e correções de fluxo. | Revalidações contínuas de segurança e produção estão na Fase 12. |
| 1 — Catálogos de regras | 🟡 | Atributos, perícias, classes/progressões, condições, patentes e origens carregados; carregador idempotente; schema cumulativo e validação de pré-requisitos; validação dos efeitos das condições. | `trilhas.json`, `poderes.json`, `rituais.json`, `itens_oprgp.json` e `itens_sah.json` estão vazios. Faltam curadoria autorizada, validação dos dados e conferência visual das páginas-imagem marcadas “a conferir”. |
| 2 — Motor de condições e efeitos | 🟡 | Modificadores numéricos em testes/Defesa, escaladas e auditoria; expiração no fim da cena; duração opcional de 1–99 turnos por ficha; bloqueios diretos para Atordoado/Pasmo, Enjoado e Inconsciente. | Resolver efeitos que dependem de contexto (ações mentais, alvos, deslocamento, percepção, início/fim de rodada), composição/interações e durações específicas do catálogo ainda não automatizadas. |
| 3 — Modo Presencial | ✅ | Fluxos físicos para rolagens/iniciativa/dano, modo de sessão com contraste/fonte e tentativa de Screen Wake Lock; combate assistido presencialmente. | Testar usabilidade e compatibilidade em aparelhos reais. Não é um tabuleiro virtual. |
| 4 — Painel do mestre e turnos | ✅ | Painel unificado para mesas, fichas inscritas, cenas/pistas, histórico filtrado de rolagens e configuração; cards e polling, condição em grupo e rastreador com participantes, ordem, ações, reações e gastos PE/PD por turno. Jogadores encontram mesas separadamente. | Automatizações de combate descritas nas Fases 2 e 5 permanecem fora deste painel básico. |
| 5 — Poderes, rituais e combate/paranormal | 🟡 | Ficha registra escolhas personalizadas ou de catálogo; pré-requisitos estruturados filtram e revalidam escolhas. Teste de ataque, dano físico informado e aplicação auditada a fichas estão disponíveis. | Catálogos ainda vazios; faltam execução/custo/efeitos automáticos de poderes e rituais, combate completo, reações e resolução paranormal automatizada. |
| 6 — Evolução e campanha | 🟡 | NEX, níveis, estágios, patentes/prestígio, escolhas pendentes, configuração global adaptável após criação de fichas, sessão, arquivamento e histórico/auditoria. Ficha informa patente, prestígio, deslocamento e mesas associadas. | Ainda não há gestão completa de campanhas/projetos separados; catálogos impedem algumas escolhas padrão, e gatilhos de dano massivo/recuperação contextual seguem manuais. |
| 7 — Equipamento | 🟡 | Inventário manual, espaços/carga, estado de itens, penalidades de sobrecarga e escolha de kit. Modelos aceitam dados de catálogo. | Catálogos de armas, proteções, equipamentos e itens amaldiçoados estão vazios; falta aplicar automaticamente propriedades e efeitos de equipamento. |
| 8 — Cenas | ✅ | Cenas com estado público/oculto, descrição para jogadores/notas privadas, pistas reveláveis e operações do mestre auditadas. | Recursos narrativos além do fluxo de cenas/pistas ainda entram nas fases 9 e 10. |
| 9 — Bestiário, geradores, mural/mensagens, Ficha de Série e regras da casa | 🟡 | Bestiário privado do mestre, campos editáveis/auditados e vínculo de ameaça ao combate. | Geradores, mural/mensagens, Ficha de Série e regras da casa não implementados; bestiário não gerencia PV atual nem automatiza ações/dano. |
| 10 — Utilidades e PWA | 🟡 | Manifesto, service worker, instalação e fallback offline genérico; cache limitado a recursos estáticos, sem dados autenticados. | Utilidades extras não estão especificadas/implementadas; validar instalação e offline em dispositivos/navegadores reais e HTTPS de produção. |
| 11 — Contas e segurança | ✅ | Cadastro/login com normalização, validação, rate limit/bloqueio, CSRF, permissões, filtragem de fichas, proteção de notas e auditoria, cobertos por testes. | Revisão contínua continua necessária; configuração real de produção e resposta operacional a incidentes não foram validadas nesta máquina. |
| 12 — Revisão final | 🟡 | 130 testes passam; `check`, migrações e `git diff --check` verificados; hooks Gitleaks/Bandit, pip-audit e `check --deploy` foram executados anteriormente em contexto local/CI simulado. | Deploy real, acessibilidade e mobile em aparelho, teste completo de vazamento mestre/jogador, concorrência/IDOR abrangentes e repetição documentada de todas as ferramentas no estado atual. |

**Resumo:** 5 fases concluídas (0, 3, 4, 8, 11), 8 parciais (1, 2, 5, 6, 7, 9, 10, 12) e nenhuma totalmente pendente. As maiores dependências são completar catálogos com fontes autorizadas e terminar regras/combate contextual; tornar o repositório privado não equivale a licença para redistribuir conteúdo.

## Ambiente local

- Windows, PowerShell, Python 3.13.17, Django 6.1.3.
- Dependências de runtime estão pinadas em `requirements.txt`; Bandit, pip-audit e pre-commit ficam em `requirements-dev.txt`; PyMuPDF, usado só pelo extrator, fica em `requirements-pdf.txt`.
- A aplicação exige `SECRET_KEY` do ambiente ou de `.env`; nunca copie o segredo para este relatório, para arquivos rastreados ou para uma conversa.
- `.env`, `db.sqlite3`, `logs/*.log`, `.venv/`, PDFs em `docs/`, textos extraídos e `docs/ARQUIVOS SECRETOS/` são ignorados pelo Git.
- **Atenção à troca de máquina:** `.env`, `db.sqlite3` e os PDFs não vêm do clone. Gere um `.env` novo com chave exclusiva na nova máquina. Se precisar preservar contas/fichas locais, faça backup e transferência segura do SQLite fora do Git. Copie os PDFs para a nova máquina por meio autorizado; não os envie ao remoto.
- O usuário de desenvolvimento `admin` foi criado anteriormente com senha temporária conhecida. Troque-a com `python manage.py changepassword admin`; não reutilize essa conta/senha em produção. `samukamestre` não deve ser promovido automaticamente: crie/confirme a conta manualmente e rode `python manage.py definir_mestre samukamestre` quando autorizado.

## Registro histórico de transferência (antes dos commits `4faacfc` e `7ec7639`)

- As alterações desta sessão foram gravadas diretamente nos arquivos do workspace. `git status` confirma mudanças locais; não há alterações staged e nenhum commit ou push foi feito. Portanto, não há uma fila pendente de “Keep” do editor para estas mudanças.
- Um clone novo ou `git pull` em outra máquina **não** recebe alterações locais não commitadas. Para continuar sem commit/push, copie o projeto inteiro com as mudanças, incluindo arquivos novos e não rastreados. Não copie `.venv/`, `.env`, `db.sqlite3`, PDFs, textos extraídos ou dados secretos; transfira banco/PDFs apenas por meio privado e autorizado se forem realmente necessários.
- Na máquina de destino, confirme o estado com `git status --short`, prepare o ambiente conforme “Preparar outra máquina Windows” e rode `python manage.py migrate`, `python manage.py carregar_regras` e a suíte de testes. Não sobrescreva alterações do destino ao copiar; se já houver mudanças lá, compare e integre antes.
- No snapshot desta transferência, o remoto ainda era descrito como público e não havia autorização para commit/push; ambos os pontos foram supersedidos pelas instruções posteriores do proprietário/usuário.

### Preparar outra máquina Windows

Na raiz do clone, instale Python 3.13 se necessário e execute:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Siga `README.md` para criar `.env` e gerar uma `SECRET_KEY` nova. Em seguida:

```powershell
python manage.py migrate
python manage.py carregar_regras
python manage.py createsuperuser
python manage.py definir_mestre samukamestre
python manage.py runserver
```

`definir_mestre` só deve ser executado depois que o usuário `samukamestre` existir. Não rode `createsuperuser` com dados fictícios em produção. Acesse `http://127.0.0.1:8000/`.

Para Linux/macOS, ative com `source .venv/bin/activate`; os demais comandos Django são iguais. Se os PDFs autorizados estiverem presentes, instale `requirements-pdf.txt` e execute `python tools/extrair_pdf.py`.

## Arquitetura

- `accounts`: autenticação Django nativa e cadastro seguro. O cadastro normaliza usuário/e-mail, bloqueia os nomes reservados e o banco tem índice funcional case-insensitive para username.
- `core`: home autenticada, lista fichas visíveis conforme permissões.
- `fichas/models.py`: catálogos, configuração singleton, ficha e relações para perícias, condições, inventário, pendências, rolagens e auditoria.
- `fichas/regras.py`: funções puras de atributos, recursos, carga, testes, dano e pendências de NEX. As regras estão ancoradas em `fonte` nas páginas impressas dos livros.
- `fichas/permissions.py`: `is_mestre`, `pode_ver_ficha`, `pode_editar_ficha` e querysets filtrados por usuário. Views devem sempre buscar fichas pelo queryset permitido para produzir 404 em IDOR.
- `fichas/forms.py`: whitelists para wizard, edição, inventário, configuração e progressão.
- `fichas/views.py` e `fichas/urls.py`: wizard, detalhe, edição, JSON POST e operações recentes da mesa.
- `templates/` e `static/`: interface em português, CSS e JavaScript próprios. CSP não permite `unsafe-inline`; não adicionar script, estilo inline, CDN ou fonte externa. O JavaScript lê o token CSRF do meta tag da página base; o cookie continua HttpOnly.

## Funcionalidades implementadas

- **Fundação e segurança:** apps `accounts`, `core` e `fichas`; autenticação Django, permissões por dono/mestre, nome de usuário reservado e índice case-insensitive, rate limits, CSRF, auditoria e bloqueio de edição pelo dono em fichas inativas. Mestre é sempre identificado por `is_superuser`, nunca pelo nome de usuário.
- **Criação e ficha:** wizard de seis etapas, ficha com atributos/perícias/recursos, edição por allowlist, registro de condições, testes físicos ou digitais, dano com resultados físicos/digitais e histórico público/secretos conforme permissão. Alterações de recursos têm limite inferior zero, transação e auditoria; excedentes acima do máximo são temporários e danos consomem primeiro o excedente de PV.
- **Regras e catálogos:** `carregar_regras` é idempotente por slug e carrega atributos, perícias, classes, condições, patentes e origens (126 registros atuais). Também aceita JSONs de trilhas, poderes, rituais e itens OPRPG/SaH; esses arquivos adicionais estão vazios à espera de curadoria. Efeitos estruturados de condições só aceitam modificadores numéricos validados; escaladas são explícitas e auditadas.
- **Progressão:** NEX padrão para Combatente/Especialista/Ocultista com pendências e controle de versão; Sobrevivente avança por estágio por ação do mestre, criando pendências para escolhas previstas. A mesa pode escolher antes da primeira ficha Nível de Experiência/Nível de Exposição ou progressão por patentes. A opção de nível mantém NEX separado da competência; patentes registram prestígio por missão, promovem sem rebaixamento e atualizam recursos, pendências e recuperação. Patentes exigem modo Sem Sanidade (PV/PD).
- **Inventário e mesa:** inventário manual com cálculo de carga, kits e penalidades; configuração da mesa exclusiva do mestre, limite de fichas ativas, arquivamento/restauração e opções de compartilhamento. Cicatrizado e Ferimentos Debilitantes são suportados; o gatilho de dano massivo continua manual.
- **Combate:** painel do mestre para cenas, participantes (ficha opcional), Iniciativa física, surpresa, ordem de turnos, ações e reações defensivas. Ataques podem ser avaliados como testes de Luta/Pontaria contra uma DT informada; dano informado fisicamente pode ser aplicado a uma ficha vinculada. PV reduzido a zero ativa Inconsciente/Morrendo; o mestre confirma estabilização e três turnos iniciados Morrendo na cena marcam a ficha como morta. Não há mapa, cálculo automático de alcance/ataques ou resolução automática de reações.
- **Operação e interface:** polling autenticado a cada 30 segundos, interface responsiva e acessível por teclado, CSP sem scripts/estilos inline, dependências de PDF separadas e CI com testes, auditorias e verificação de migrações/configuração de produção.

## Regras e decisões importantes

- O OPRPG p.11 prevalece sobre o resumo inicial para penalidades que reduziriam a pool abaixo de 1 dado: inverte-se a penalidade e escolhe-se o pior resultado. A decisão está registrada em `docs/DECISOES.md`.
- No miolo do OPRPG, as amostras confirmam página impressa = página PDF − 10. Não aplique esse deslocamento ao SaH.
- Ao inserir dados de regra, use apenas texto extraído localmente ou conferência visual e inclua página impressa no campo `fonte`. Faça paráfrases mecânicas curtas; não copie capítulos ou descrições longas. Páginas image-only e limitações da extração estão documentadas em `docs/DECISOES.md`.
- Atualizações JSON devem continuar em POST com CSRF e allowlists estritas. Preserve autenticação, rate limit, filtragem de fichas autorizadas (404 para ficha alheia) e auditoria.
- Não registrar conteúdo de anotações privadas. O versionamento otimista evita sobrescrita silenciosa; alterações de recursos e progressão devem continuar atômicas e auditáveis.
- Não use `safe`, `mark_safe`, SQL cru ou `csrf_exempt`. CSP não permite `unsafe-inline`; não adicionar CDN ou fontes externas.

## Lacunas e próximos passos

1. Continuar curadoria dos catálogos de trilhas, poderes, rituais, itens, armas e proteções. Os JSONs novos estão vazios; inserir apenas dados concisos, revisados e próprios/autorizados. O proprietário informou que o repositório foi tornado privado em 2026-11-04.
2. O rastreador agora contabiliza gastos de PE/PD por turno e impõe os limites de progressão/patente. Ainda falta conferir a regra completa de custo mínimo e exceções com fontes autorizadas antes de automatizá-las.
3. Combate continua assistido, não automatizado: sem mapa, alcance, resolução de ataques, aplicação automática de dano ou validação de reações; o mestre informa dano físico já calculado. O gatilho de dano massivo também é manual.
4. Fazer validação visual de interface mobile/acessibilidade em aparelho real.
5. Continuar cobrindo autorização/IDOR, concorrência, limites de taxa, auditoria, mudanças de configuração e fluxos de combate; não afirmar segurança absoluta.
6. `check --deploy` foi executado anteriormente em configuração simulada e reportou avisos esperados para desenvolvimento (`DEBUG`, HTTPS e cookies seguros). Ainda não há validação de deploy em ambiente real.
7. O repositório está privado conforme informado pelo proprietário; mantenha dados confidenciais da mesa fora do Git. PDFs e arquivos de `docs/ARQUIVOS SECRETOS/` existem localmente, mas são ignorados pelo Git e não devem ser enviados ao remoto.

## Estado para continuar em outra máquina — 2026-11-04

- O proprietário confirmou que o repositório está privado. O trabalho desta atualização será publicado na `main`; depois do push, na outra máquina use `git pull` para obter código, testes, documentação e migrations.
- Esta rodada inclui gestão de mesas públicas/privadas com código, inscrição/remoção de fichas, painel unificado do mestre, habilidades personalizadas na ficha, atualização da ficha após mudanças de configuração da mesa, campos e escolhas iniciais de progressão/treinamento/trilha, perfil de conta e padronização visual/transições.
- Recursos atuais PV/PE/SAN/PD podem exceder o máximo; a diferença é temporária no próprio recurso. Ajustes nunca reduzem abaixo de zero e dano consome primeiro o excedente de PV. A migration `fichas.0016_recurso_temporario_em_excesso_e_prerequisitos_trilha` soma o antigo `pv_temporario` a `pv_atual` e adiciona `Trilha.pre_requisitos`.
- O erro ocorrido ao abrir a etapa final de criação foi causado pela migration 0016 ainda pendente no SQLite local. Ela foi aplicada e verificada nesta máquina. Em outra máquina, execute `python manage.py migrate` antes de iniciar o servidor.
- Validação desta atualização: **130 testes passaram**, `manage.py check` sem problemas, `makemigrations --check --dry-run` sem alterações e `git diff --check` sem erros.
- O Git transfere somente código versionado; não transfere o SQLite local (`db.sqlite3`), `.env`, usuários, fichas ou outros dados locais. O clone na outra máquina terá banco separado. Mantenha `.env`, `SECRET_KEY`, credenciais e cópias do banco fora do Git; gere uma chave própria para cada ambiente. Se precisar das fichas/dados da máquina atual, faça backup e transporte seguro do banco separadamente.
- Na máquina de destino: atualize a branch `main`, prepare o ambiente conforme `README.md`, instale as dependências do projeto, configure o `.env`, execute `python manage.py migrate`, `python manage.py carregar_regras` e `python manage.py test`. Confirme/crie contas nessa instalação separadamente; não presuma que a conta mestre ou usuários do SQLite local foram enviados ao remoto.

Consulte também `docs/COMO_USAR.md` para os fluxos de jogadores e mestre, `docs/MODELOS.md` para os modelos e `docs/COBERTURA.md` para o estado detalhado dos catálogos.

## Avanço após o grupo 4

- Condições marcadas para terminar com a cena agora são removidas e auditadas ao encerrar o combate; condições persistentes não são removidas.
- `Poder.pre_requisitos` usa schema estruturado e cumulativo, com validação no carregador, filtragem de escolhas pela ficha e revalidação no POST.
- O carregador também rejeita efeitos de condição com campos desconhecidos, booleanos ou valores fora do limite, abortando a transação. Não incluiu dados de catálogo licenciados.
- Validação deste avanço: **111 testes passaram**, `check` sem problemas, `makemigrations --check --dry-run` sem alterações e `git diff --check` sem erros. Gitleaks e Bandit passaram nos hooks do commit.
- As lacunas de efeitos dependentes de rodada/ação, catálogo de regras, automação completa de combate e validação em aparelho real continuam pendentes.
- O proprietário informou que tornou o repositório privado em 2026-11-04; conteúdo de terceiros continua sujeito a direitos autorais e autorização.

## Continuação do avanço parcial

- Incremento publicado em `2e38cc9` na `main`; `fichas.0014` foi aplicada ao SQLite local e a branch ficou sincronizada com `origin/main`.
- Condições agora aceitam duração opcional de 1 a 99 turnos por ficha. O contador diminui no início do turno do personagem afetado, expira e registra auditoria ao chegar a zero; a duração é mantida ao escalar uma condição. Condições sem duração permanecem sem temporizador.
- Morrendo permanece sob o contador letal da cena e não usa o temporizador genérico.
- Esta funcionalidade não presume duração de nenhum efeito do catálogo: o mestre/jogador autorizado informa a duração da instância. Ainda falta automatizar efeitos dependentes de ação e validação de regras específicas.
- Verificação desta continuação: **114 testes passaram**, incluindo validação dos limites, decremento/expiração, auditoria, polling, escalada, restrições de ação e separação do contador de Morrendo. `check`, `makemigrations --check --dry-run` e `git diff --check` sem problemas.
- O rastreador agora também aplica no servidor as restrições de ação de Atordoado/Pasmo, Enjoado e Inconsciente. Restrições dependentes de contexto (ações mentais, alvos, alcance, etc.) seguem pendentes.
- Essas restrições foram publicadas em `d854d28`; `main` está sincronizada com `origin/main`.

## Rechecagem anterior em 2026-11-04

O relatório foi comparado com as views, modelos, templates, JSONs e testes atuais, não apenas com o histórico descrito acima:

- Confirmado no código: painel/histórico do mestre, rastreador de combate, inventário manual, progressão NEX/estágio/nível/patentes, testes físicos, dano avaliado, polling e condições com escalada/auditoria estão presentes, com cobertura em `core/tests.py` e `fichas/tests.py`.
- Confirmado como lacuna: o carregador aceita trilhas, poderes, rituais e itens, mas `trilhas.json`, `poderes.json`, `rituais.json`, `itens_oprgp.json` e `itens_sah.json` continuam vazios. As condições só aplicam os modificadores numéricos presentes em `Condicao.efeitos`; composição, restrições de ação, durações por rodada, automáticas e efeitos temporários ainda não têm o motor completo.
- Na rechecagem de 2026-11-04, o repositório ainda constava como público. Depois dessa rechecagem, o proprietário informou que o tornou privado; a curadoria de catálogos segue pendente e conteúdo de terceiros permanece sujeito a autorização.
- A interface da ficha agora oferece botões de recurso −5/−1/+1/+5 e ajuste digitado; PV, PE, SAN e PD podem exceder seus máximos como temporários, com limite inferior zero, auditoria e polling. Há também controles client-side de contraste/fonte e Screen Wake Lock. Eles não são preferências de conta, e o comportamento em aparelhos reais permanece por validar.
- O motor puro `fichas/efeitos.py` agora detalha por linha os dados-base, modificadores de cada condição, treinamento e bônus situacionais; a view de rolagem usa essa explicação e mantém `parametros_teste` como fonte de quantidade/ordem, inclusive para pools negativas.
- No painel do mestre, o polling agora ocorre a cada 5 segundos; a aplicação de condição em grupo atende até 50 fichas ativas, exclusiva do mestre, limitada por taxa e auditada ficha a ficha.
- O rastreador agora contabiliza gastos de PE/PD por turno, aplica o limite de PE por progressão ou de PD por patente, desconta recursos e reseta os contadores no turno seguinte. Isso exige a nova migration `fichas.0012_participantecombate_pd_gasto_turno_and_more`.
- Na execução desta sessão, `migrate` aplicou as migrations `fichas.0006`–`0011`, que estavam pendentes. O banco SQLite local foi limpo a pedido do proprietário, o comando `carregar_regras` foi executado e a conta mestre `samukamestre` foi criada. Nenhuma senha foi registrada neste documento. Não extrapolar esse estado local para produção.
- Validação final deste grupo: `check` sem problemas; `makemigrations --check --dry-run` sem alterações; **99 testes passaram**; Bandit sem achados; pip-audit sem vulnerabilidades conhecidas; `git diff --check` sem erros. A interface de login foi aberta no navegador local e `ficha.js` foi carregado com sucesso; a validação visual em aparelhos reais continua pendente.

## Atualização em 2026-11-04 — avanço das fases parciais

- Ao encerrar uma cena de combate, condições com `termina_fim_cena=True` agora são removidas das fichas participantes e cada remoção gera auditoria; condições persistentes permanecem. A regra usa o sinalizador já existente no catálogo, sem inferir duração para condições sem metadados.
- O teste focal confirma remoção, preservação e auditoria. As próximas lacunas continuam sendo os catálogos autorizados, efeitos contextuais/durações ainda não modelados e automações de combate que dependem de regras ou decisões do mestre.
- O campo de pré-requisitos de Poder ganhou um schema estruturado, validação no carregador, filtragem das opções por classe/trilha/progressão/atributos/perícias/poderes e revalidação no servidor. Nenhum dado de catálogo de livros foi criado; os arquivos seguem vazios enquanto não houver curadoria autorizada.
- A validação local do PWA confirmou cache somente de CSS, ícone, manifesto e página offline genérica; navegando sem conexão, o login/home privados não foram armazenados e foi apresentada a tela de reconexão.
- Validação deste avanço: **110 testes passaram**, `check` e migrações sem problemas, Gitleaks e Bandit sem achados, pip-audit sem vulnerabilidades conhecidas e `git diff --check` sem erros.

## Atualização em 2026-11-04 — grupo 3 (fases 7–9)

- O inventário manual já permitia cadastrar equipamento na ficha, sem precisar replicar um catálogo licenciado. O catálogo de equipamentos/armas/proteções continua pendente de curadoria autorizada; nenhum conteúdo de livro foi adicionado.
- Foram implementadas cenas de mesa para investigação/interlúdio/medo/furtividade/perseguição. Cada cena separa descrição pública e notas do mestre, começa oculta e pode ser publicada pelo mestre. Pistas têm estados oculta/revelada/anotada; jogadores recebem somente pistas visíveis. Escrita e mudanças de estado são exclusivas do superusuário, protegidas por POST/CSRF e limites de taxa, e registradas sem copiar notas privadas para o log.
- Foi implementado um bestiário privado do mestre com campos mecânicos editáveis, arquivamento e auditoria. As ameaças ativas podem ser vinculadas ao roster de combate, que mostra os dados somente ao mestre. O bestiário está vazio por padrão e deve receber apenas dados próprios/autorizados.
- Limitações preservadas explicitamente: não há catálogo pré-carregado de livros; PV do bestiário são referência, sem PV atual, ataques ou dano de ameaça automatizados; o mestre ainda informa dano manualmente às fichas.
- Foram adicionados testes de autorização, filtragem de segredos, criação/edição/auditoria e vínculo de ameaça no combate. Validação do grupo: **105 testes passaram**, `check` sem problemas, `makemigrations --check --dry-run` sem alterações e `git diff --check` sem erros. As migrations `core.0001`, `core.0002` e `fichas.0013` foram aplicadas ao banco local.

## Atualização em 2026-11-04 — grupo 4 (fases 10–12)

- O site ganhou manifesto PWA e service worker com escopo de raiz. O cache mantém somente recursos estáticos; páginas autenticadas, APIs e dados da campanha nunca são armazenados. Sem conexão, o service worker serve uma página genérica que pede reconexão. `STATIC_URL` foi normalizado para caminho absoluto para que assets funcionem também em rotas aninhadas.
- A revisão de contas confirmou cadastro com normalização NFKC, nomes reservados, e-mail único sem distinção de caixa, Argon2, validação de senha e rate limit; o login usa mensagem genérica e bloqueio após falhas repetidas. Os testes existentes cobrem esses controles, portanto não foi necessário alterar o fluxo de contas.
- Revisão final: **106 testes passaram**, `check` sem problemas, `makemigrations --check --dry-run` sem alterações, Bandit sem achados, pip-audit sem vulnerabilidades conhecidas, `findstatic` localizou os três assets PWA e `git diff --check` sem erros.
- Limitações finais: a página offline não disponibiliza dados da mesa. Catálogos licenciados continuam vazios até curadoria autorizada, ameaças não têm controle automatizado de PV/dano e deploy real não foi testado. Uma verificação posterior em navegador integrado confirmou registro do service worker, ausência de overflow horizontal em viewport de 390 px e fallback offline; validação em aparelho real e HTTPS de produção ainda falta.
- Nenhum commit ou push foi feito. O banco SQLite local recebeu somente as migrations aditivas deste grupo e permanece distinto de produção.

## Atualização de continuidade — alterações finais desta rodada

- A ficha não tem mais um campo separado para PV temporários; a migration `fichas.0016` preserva os valores antigos somando-os aos PV atuais antes de remover a coluna. PE, SAN e PD também aceitam excedente temporário.
- O perfil permite alterar nome, username e e-mail, trocar senha, sair e consultar/alterar o papel conforme a permissão. Jogadores não podem conceder a si mesmos papel de mestre, e o último superusuário não pode se rebaixar.
- A criação da ficha valida os pré-requisitos estruturados da trilha e limita avanços de grau de perícia conforme os marcos de NEX e classe; Sobreviventes não recebem avanços automáticos de grau na criação.
- Documentação e testes relacionados foram atualizados. A verificação completa mais recente executou 130 testes com sucesso; `check`, migrações e diff-check também passaram.
- Ainda falta validar visualmente em dispositivos reais. Catálogos de habilidades/equipamentos não foram preenchidos com conteúdo de livros; continuar essa curadoria somente com conteúdo autorizado. Combate permanece assistido, com danos informados pelo mestre.
