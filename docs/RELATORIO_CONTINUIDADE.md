# Relatório de Continuidade

Atualizado em 2026-11-04. Este documento resume o estado conhecido do projeto para a próxima IA ou pessoa desenvolvedora. Leia também `docs/DECISOES.md`, `docs/MODELOS.md` e `docs/COBERTURA.md` antes de alterar regras ou modelos.

## Estado do repositório

- Projeto: Django para campanha de Ordem Paranormal RPG, workspace `MONOTOFOBIA`.
- Branch: `main`; no estado de 2026-11-04, `HEAD` e `origin/main` apontam para `7a2f676`. Há alterações locais acumuladas de várias fases, inclusive arquivos novos ainda não rastreados; consulte “Estado de transferência” abaixo.
- Últimos commits de fase:
  - `62783a4` `feat(fichas): add rules core and PDF prep`
  - `9c85fcf` `feat(rules): load core catalogs and origins`
  - `1ac6932` `feat(fichas): implement character creation and sheet UI`
  - `3e87251` `feat(fichas): add NEX advancement workflow`
  - `71ab982` `feat(fichas): add manual inventory management`
  - `f62d0fc` `feat(fichas): add table settings and active sheet limits`
- Os commits de fase passaram pelos hooks Gitleaks e Bandit. Não faça push sem pedido explícito.
- O remoto GitHub foi verificado como **público**. Não armazene dados da mesa nem material licenciado nele; a privatização depende do proprietário.

## Ambiente local

- Windows, PowerShell, Python 3.13.17, Django 6.1.3.
- Dependências de runtime estão pinadas em `requirements.txt`; Bandit, pip-audit e pre-commit ficam em `requirements-dev.txt`; PyMuPDF, usado só pelo extrator, fica em `requirements-pdf.txt`.
- A aplicação exige `SECRET_KEY` do ambiente ou de `.env`; nunca copie o segredo para este relatório, para arquivos rastreados ou para uma conversa.
- `.env`, `db.sqlite3`, `logs/*.log`, `.venv/`, PDFs em `docs/`, textos extraídos e `docs/ARQUIVOS SECRETOS/` são ignorados pelo Git.
- **Atenção à troca de máquina:** `.env`, `db.sqlite3` e os PDFs não vêm do clone. Gere um `.env` novo com chave exclusiva na nova máquina. Se precisar preservar contas/fichas locais, faça backup e transferência segura do SQLite fora do Git. Copie os PDFs para a nova máquina por meio autorizado; não os envie ao remoto.
- O usuário de desenvolvimento `admin` foi criado anteriormente com senha temporária conhecida. Troque-a com `python manage.py changepassword admin`; não reutilize essa conta/senha em produção. `samukamestre` não deve ser promovido automaticamente: crie/confirme a conta manualmente e rode `python manage.py definir_mestre samukamestre` quando autorizado.

## Estado de transferência (2026-11-04)

- As alterações desta sessão foram gravadas diretamente nos arquivos do workspace. `git status` confirma mudanças locais; não há alterações staged e nenhum commit ou push foi feito. Portanto, não há uma fila pendente de “Keep” do editor para estas mudanças.
- Um clone novo ou `git pull` em outra máquina **não** recebe alterações locais não commitadas. Para continuar sem commit/push, copie o projeto inteiro com as mudanças, incluindo arquivos novos e não rastreados. Não copie `.venv/`, `.env`, `db.sqlite3`, PDFs, textos extraídos ou dados secretos; transfira banco/PDFs apenas por meio privado e autorizado se forem realmente necessários.
- Na máquina de destino, confirme o estado com `git status --short`, prepare o ambiente conforme “Preparar outra máquina Windows” e rode `python manage.py migrate`, `python manage.py carregar_regras` e a suíte de testes. Não sobrescreva alterações do destino ao copiar; se já houver mudanças lá, compare e integre antes.
- Se a transferência for feita somente por GitHub, será necessário criar e enviar um commit das alterações; isso não foi autorizado nem realizado. Não faça isso sem autorização expressa. O remoto é público, então mantenha dados de campanha e material licenciado fora dele.

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
- **Criação e ficha:** wizard de seis etapas, ficha com atributos/perícias/recursos, edição por allowlist, registro de condições, testes físicos ou digitais, dano com resultados físicos/digitais e histórico público/secretos conforme permissão. Alterações de recursos têm clamps, transação e auditoria; PV temporários absorvem dano antes de PV.
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

1. Continuar curadoria dos catálogos de trilhas, poderes, rituais, itens, armas e proteções. Os JSONs novos estão vazios; inserir apenas dados concisos, revisados e próprios/autorizados. O repositório GitHub é público.
2. O limite cumulativo de PD por turno da patente é exibido, mas não imposto: o rastreador não registra gastos de PD por turno. Modelar gastos em ações e reações antes de impor o limite e considerar a exceção de custo mínimo descrita em OPRPG p.23.
3. Combate continua assistido, não automatizado: sem mapa, alcance, resolução de ataques, aplicação automática de dano ou validação de reações; o mestre informa dano físico já calculado. O gatilho de dano massivo também é manual.
4. Fazer validação visual de interface mobile/acessibilidade em aparelho real.
5. Continuar cobrindo autorização/IDOR, concorrência, limites de taxa, auditoria, mudanças de configuração e fluxos de combate; não afirmar segurança absoluta.
6. `check --deploy` foi executado anteriormente em configuração simulada e reportou avisos esperados para desenvolvimento (`DEBUG`, HTTPS e cookies seguros). Ainda não há validação de deploy em ambiente real.
7. O proprietário deve privatizar o repositório antes de guardar dados confidenciais da mesa ou material licenciado. PDFs e arquivos de `docs/ARQUIVOS SECRETOS/` existem localmente, mas são ignorados pelo Git.

## Verificação atual e transferência

- Em 2026-11-04, `main` e `origin/main` apontam para `7a2f676`. O worktree contém alterações locais rastreadas e arquivos novos não rastreados, sem alterações staged; não foi feito commit nem push. Uma cópia/clone limpo ou `git pull` **não** inclui esse trabalho.
- A suíte foi executada novamente neste estado: **97 testes passaram** e o system check do Django não encontrou problemas. `git diff --check` não encontrou erros; Git apenas avisou sobre normalização CRLF/LF.
- Para continuar em outra máquina sem commit/push, transfira o projeto completo com alterações rastreadas e não rastreadas. Não transfira `.venv/`; mantenha `.env`, `db.sqlite3`, logs, PDFs, textos extraídos e dados da mesa fora do Git. Se precisar manter as fichas locais, faça backup e transferência segura do SQLite. Não sobrescreva trabalho já existente no destino.
- Na máquina de destino, prepare o ambiente conforme `README.md`, crie um `.env` com `SECRET_KEY` nova e execute `python manage.py migrate`, `python manage.py carregar_regras` e `python manage.py test`. Crie/confirme as contas manualmente; `definir_mestre samukamestre` só depois de a conta existir e com autorização. Troque a senha temporária conhecida do usuário de desenvolvimento `admin`; nunca a use em produção.
- Se a transferência for feita via GitHub, será necessário criar e enviar commit das mudanças, o que não foi autorizado nem realizado. Como o remoto está público, não envie dados de campanha nem conteúdo licenciado.

Consulte também `docs/COMO_USAR.md` para os fluxos de jogadores e mestre, `docs/MODELOS.md` para os modelos e `docs/COBERTURA.md` para o estado detalhado dos catálogos.

## Rechecagem em 2026-11-04

O relatório foi comparado com as views, modelos, templates, JSONs e testes atuais, não apenas com o histórico descrito acima:

- Confirmado no código: painel/histórico do mestre, rastreador de combate, inventário manual, progressão NEX/estágio/nível/patentes, testes físicos, dano avaliado, polling e condições com escalada/auditoria estão presentes, com cobertura em `core/tests.py` e `fichas/tests.py`.
- Confirmado como lacuna: o carregador aceita trilhas, poderes, rituais e itens, mas `trilhas.json`, `poderes.json`, `rituais.json`, `itens_oprgp.json` e `itens_sah.json` continuam vazios. As condições só aplicam os modificadores numéricos presentes em `Condicao.efeitos`; composição, restrições de ação, durações por rodada, automáticas e efeitos temporários ainda não têm o motor completo.
- O repositório segue público conforme a verificação já registrada. Não inserir conteúdo de livro ou dados privados da campanha em arquivos versionáveis enquanto ele permanecer público; a curadoria dos catálogos permanece pendente.
- A interface da ficha agora oferece botões de recurso −5/−1/+1/+5 e ajuste digitado, incluindo PV temporários com clamp, auditoria e polling. Há também controles client-side de contraste/fonte e Screen Wake Lock. Eles não são preferências de conta, e o comportamento em aparelhos reais permanece por validar.
- O motor puro `fichas/efeitos.py` agora detalha por linha os dados-base, modificadores de cada condição, treinamento e bônus situacionais; a view de rolagem usa essa explicação e mantém `parametros_teste` como fonte de quantidade/ordem, inclusive para pools negativas.
- No painel do mestre, o polling agora ocorre a cada 5 segundos; a aplicação de condição em grupo atende até 50 fichas ativas, exclusiva do mestre, limitada por taxa e auditada ficha a ficha.
- O rastreador agora contabiliza gastos de PE/PD por turno, aplica o limite de PE por progressão ou de PD por patente, desconta recursos e reseta os contadores no turno seguinte. Isso exige a nova migration `fichas.0012_participantecombate_pd_gasto_turno_and_more`.
- Na execução desta sessão, `migrate` aplicou as migrations `fichas.0006`–`0011`, que estavam pendentes. O banco SQLite local foi limpo a pedido do proprietário, o comando `carregar_regras` foi executado e a conta mestre `samukamestre` foi criada. Nenhuma senha foi registrada neste documento. Não extrapolar esse estado local para produção.
- Validação final deste grupo: `check` sem problemas; `makemigrations --check --dry-run` sem alterações; **99 testes passaram**; Bandit sem achados; pip-audit sem vulnerabilidades conhecidas; `git diff --check` sem erros. A interface de login foi aberta no navegador local e `ficha.js` foi carregado com sucesso; a validação visual em aparelhos reais continua pendente.

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
- Limitações finais: instalação e funcionamento offline ainda requerem validação visual em aparelho/navegador real e HTTPS; a página offline não disponibiliza dados da mesa. Catálogos licenciados continuam vazios até curadoria autorizada, ameaças não têm controle automatizado de PV/dano e deploy real não foi testado.
- Nenhum commit ou push foi feito. O banco SQLite local recebeu somente as migrations aditivas deste grupo e permanece distinto de produção.
