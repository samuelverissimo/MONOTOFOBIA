# Relatório de Continuidade

Atualizado em 2026-11-04. Este documento resume o estado conhecido do projeto para a próxima IA ou pessoa desenvolvedora. Leia também `docs/DECISOES.md`, `docs/MODELOS.md` e `docs/COBERTURA.md` antes de alterar regras ou modelos.

## Estado do repositório

- Projeto: Django, campanha privada de Ordem Paranormal RPG, workspace `MONOTOFOBIA`.
- Branch: `main`. No último estado conferido, `HEAD` e `origin/main` apontavam para `f62d0fc`; working tree limpa antes da criação deste relatório.
- Últimos commits de fase:
  - `62783a4` `feat(fichas): add rules core and PDF prep`
  - `9c85fcf` `feat(rules): load core catalogs and origins`
  - `1ac6932` `feat(fichas): implement character creation and sheet UI`
  - `3e87251` `feat(fichas): add NEX advancement workflow`
  - `71ab982` `feat(fichas): add manual inventory management`
  - `f62d0fc` `feat(fichas): add table settings and active sheet limits`
- Os commits de fase passaram pelos hooks Gitleaks e Bandit. Não faça push sem pedido explícito.
- O remoto GitHub foi verificado como **público**. Recomenda-se torná-lo privado antes de armazenar dados da mesa ou materiais internos.

## Ambiente local

- Windows, PowerShell, Python 3.13.17, Django 6.1.3.
- Dependências de runtime estão pinadas em `requirements.txt`; ferramentas, PyMuPDF e dependências de desenvolvimento em `requirements-dev.txt`.
- A aplicação exige `SECRET_KEY` do ambiente ou de `.env`; nunca copie o segredo para este relatório, para arquivos rastreados ou para uma conversa.
- `.env`, `db.sqlite3`, `logs/*.log`, `.venv/`, PDFs em `docs/`, textos extraídos e `docs/ARQUIVOS SECRETOS/` são ignorados pelo Git.
- **Atenção à troca de máquina:** `.env`, `db.sqlite3` e os PDFs não vêm do clone. Gere um `.env` novo com chave exclusiva na nova máquina. Se precisar preservar contas/fichas locais, faça backup e transferência segura do SQLite fora do Git. Copie os PDFs para a nova máquina por meio autorizado; não os envie ao remoto.
- O usuário de desenvolvimento `admin` foi criado anteriormente com senha temporária conhecida. Troque-a com `python manage.py changepassword admin`; não reutilize essa conta/senha em produção. `samukamestre` não deve ser promovido automaticamente: crie/confirme a conta manualmente e rode `python manage.py definir_mestre samukamestre` quando autorizado.

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

Para Linux/macOS, ative com `source .venv/bin/activate`; os demais comandos Django são iguais. Se os PDFs autorizados estiverem presentes, a extração local é `python tools/extrair_pdf.py`; requer as dependências dev.

## Arquitetura

- `accounts`: autenticação Django nativa e cadastro seguro. O cadastro normaliza usuário/e-mail, bloqueia os nomes reservados e o banco tem índice funcional case-insensitive para username.
- `core`: home autenticada, lista fichas visíveis conforme permissões.
- `fichas/models.py`: catálogos, configuração singleton, ficha e relações para perícias, condições, inventário, pendências, rolagens e auditoria.
- `fichas/regras.py`: funções puras de atributos, recursos, carga, testes, dano e pendências de NEX. As regras estão ancoradas em `fonte` nas páginas impressas dos livros.
- `fichas/permissions.py`: `is_mestre`, `pode_ver_ficha`, `pode_editar_ficha` e querysets filtrados por usuário. Views devem sempre buscar fichas pelo queryset permitido para produzir 404 em IDOR.
- `fichas/forms.py`: whitelists para wizard, edição, inventário, configuração e progressão.
- `fichas/views.py` e `fichas/urls.py`: wizard, detalhe, edição, JSON POST e operações recentes da mesa.
- `templates/` e `static/`: interface em português, CSS e JavaScript próprios. CSP não permite `unsafe-inline`; não adicionar script, estilo inline, CDN ou fonte externa. O JavaScript lê o token CSRF de campo hidden, pois o cookie é HttpOnly.

## Fases concluídas

- **Fase 0:** `tools/extrair_pdf.py` cria um TXT UTF-8 por página; PDFs estavam na raiz de `docs/`, mas o extrator aceita também `docs/regras/`. Foram extraídas 332 páginas do OPRPG e 226 do SaH para pastas ignoradas. A ordenação de colunas foi comparada visualmente em uma página amostral. Páginas image-only estão listadas em `docs/DECISOES.md`; não use TXT vazio como prova de que a página não contém regra.
- **Fase 1:** app `fichas`, modelos, cálculo puro, permissões, comando `definir_mestre`, reserva de usernames e configurações base.
- **Fase 2:** 126 registros carregados via `python manage.py carregar_regras`: 5 atributos, 28 perícias, 4 classes, 38 condições, 5 patentes, 26 origens básicas e 20 origens SaH. O comando é idempotente por slug.
- **Fase 3:** wizard de seis etapas, tela Status/Perícias, edição limitada por formulário, recursos com clamp/transação, condições, rolagens, auditoria, CSRF e rate limit.
- **Fase 4:** avanço de NEX padrão para Combatente/Especialista/Ocultista, pendências por marcos, controle otimista por versão e auditoria. Jogadores só avançam se a opção da mesa permitir; mestre é identificado apenas por `is_superuser`. Sobrevivente não usa NEX.
- **Fase 5:** inventário manual com adicionar/atualizar/remover, cálculo de carga, aviso de sobrecarga, isolamento por ficha e log sem registrar notas privadas.
- **Fase 6:** formulário de configuração da mesa exclusivo do mestre, modo Padrão/PD, toggle de jogador subir NEX, limite de fichas ativas, bloqueio no início/fim do wizard e arquivamento/restauração respeitando limite e versão.

## Regras e decisões importantes

- O OPRPG p.11 prevalece sobre o resumo inicial para penalidades que reduziriam a pool abaixo de 1 dado: inverte-se a penalidade e escolhe-se o pior resultado. A decisão está registrada em `docs/DECISOES.md`.
- No miolo do OPRPG, as amostras confirmam página impressa = página PDF − 10. Não aplique esse deslocamento ao SaH.
- Ao inserir dados de regra, use apenas texto extraído localmente ou conferência visual e inclua página impressa no campo `fonte`. Faça paráfrases mecânicas curtas; não copie capítulos ou descrições longas.
- A Ficha usa o User nativo. Nunca conceda privilégio pelo username; mestre é apenas `request.user.is_superuser`.
- Edições de texto do jogador são escapadas pelo autoescape. Não usar `safe`, `mark_safe`, SQL cru ou `csrf_exempt`.
- Atualizações JSON são POST, com CSRF e allowlists estritas. Preserve `@login_required`, rate limit e 404 para fichas alheias.
- Não registrar conteúdo de anotações privadas. O versionamento otimista evita sobrescrita silenciosa; alterações de recursos e NEX devem continuar atômicas e auditáveis.

## Lacunas e próximos passos

1. Revisar a UI em celular e acessibilidade; a Ficha de status/perícias está funcional, mas ainda é uma base compacta. O servidor usa polling/WebSocket? **Nenhuma atualização em tempo real foi implementada**.
2. Completar combate: armas, ataques, dano/crítico, proteções e reações.
3. Completar catálogo de itens/equipamentos das páginas OPRPG 50-67 e SaH 37-45, além de poderes e rituais. Antes, conferir tabelas e fontes; páginas image-only precisam de conferência visual.
4. Resolver pendências da ficha (trilha, poder, atributo, treinamento, ritual) com validações completas. No momento, o avanço cria e mostra pendências, mas não permite resolvê-las.
5. Completar o painel da mesa: cards de todas as fichas, ações rápidas em lote, cena nova, rolagens públicas/secretas, histórico e polling.
6. Implementar os modos opcionais restantes: Nível de Experiência, evolução por patentes e Ferimentos Debilitantes, incluindo regras e testes.
7. Cobrir integralmente IDOR em edição, rolagem, arquivamento/status, limites de taxa, concorrência/atomicidade, logs e mudança do modo PD sem perda de dados.
8. Criar `docs/COMO_USAR.md`; atualizar cobertura conforme os novos catálogos e validar o fluxo do mestre/jogadores em um ambiente limpo.
9. Na fase final, rodar `python manage.py check --deploy` com ambiente de produção, `python manage.py test`, Bandit, pip-audit e revisão de acessibilidade/mobile. Não afirmar segurança absoluta.
10. Tornar o repositório privado antes de guardar dados confidenciais da mesa. Apesar das regras de ignore, os arquivos em `docs/ARQUIVOS SECRETOS/` e os PDFs existem localmente.

## Checks e commits

Último estado de validação antes deste relatório: `manage.py check` passou, migrações sem alterações pendentes, **53 testes passaram**, Bandit sem achados, pip-audit sem vulnerabilidades conhecidas. Os commits de fase executaram Gitleaks e Bandit via pre-commit.

Os commits atuais incluem as Fases 0-6; confira `git log --oneline` para hashes atuais. O fluxo combinado foi commit local ao fim de cada fase, sem push nesta sequência. Continue com commits pequenos por fase, rode os gates antes do commit e nunca inclua `.env`, SQLite, PDFs, TXT extraídos ou material secreto.
