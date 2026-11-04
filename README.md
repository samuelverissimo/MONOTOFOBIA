# MONOTOFOBIA
Projeto Django da campanha de RPG de mesa "MONOTOFOBIA", dirigida por Samuel Veríssimo.

> **Aviso de privacidade:** o repositório GitHub está público. Não versione fichas com dados pessoais, segredos da campanha, PDFs, textos extraídos ou conteúdo licenciado. Peça ao proprietário do repositório para alterar a visibilidade para privado antes de armazenar qualquer dado da mesa.

## Ambiente local

No PowerShell, crie e ative o ambiente, instale os pacotes e prepare o `.env`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
$secret = python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
@"
SECRET_KEY=$secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
ADMIN_URL=gestao-interna/
"@ | Set-Content .env -Encoding Ascii
Remove-Variable secret
```

No Linux/macOS, ative com `source .venv/bin/activate`, copie `.env.example` para `.env` e gere a chave com:

```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Coloque a chave gerada em `SECRET_KEY` no `.env`, que não deve ser commitado. Configure também `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` e, se necessário, `ADMIN_URL`.

Variáveis já exportadas no processo têm precedência sobre `.env`. Se uma chave antiga sobrescrever a local no PowerShell, remova apenas a variável desta sessão com `Remove-Item Env:SECRET_KEY`; em produção, configure a chave no gerenciador de segredos do ambiente.

Inicialize o banco e crie o superusuário:

```powershell
python manage.py migrate
python manage.py carregar_regras
python manage.py createsuperuser
```

As dependências de desenvolvimento incluem Bandit, pip-audit e pre-commit, mas não as ferramentas de PDF. Para executar `tools/extrair_pdf.py`, instale à parte:

```powershell
python -m pip install -r requirements-pdf.txt
python tools/extrair_pdf.py
```

Mantenha os PDFs e os textos extraídos localmente; eles são ignorados pelo Git.

O usuário `admin` criado para desenvolvimento anteriormente usa uma senha temporária conhecida. Troque-a com `python manage.py changepassword admin` e não reutilize essa conta/senha em produção.

Durante a sessão presencial, a ficha prioriza instruir o teste, detalhar os modificadores linha a linha e avaliar os resultados dos d20 rolados fisicamente; a rolagem digital é opcional.
Na ficha, ajuste PV, PE, SAN/PD e PV temporários com −5/−1/+1/+5 ou informe um ajuste numérico. O modo sessão pode ampliar o texto e o contraste; a tela acesa depende do suporte do navegador a Screen Wake Lock.
Para combate, Luta/Pontaria podem ser comparadas à Defesa informada como DT; uma ferramenta de dano avalia dados físicos e mantém o rolamento digital como alternativa. O mestre pode aplicar dano informado fisicamente à ficha selecionada na cena.
O painel do mestre também registra cenas, Iniciativa física, ordem de turnos, surpresa, ações e reações defensivas, gastos de PE/PD dentro dos limites por turno e condições em grupo; a ficha lembra Morrendo e permite registrar estabilização. É um controle leve, sem mapa tático ou resolução automática de ataques.
Condições e sobrecarga atualizam os modificadores numéricos exibidos para testes e Defesa; consulte os resumos na ficha para efeitos situacionais que dependem do contexto.
O mestre pode resolver escolhas pendentes e avançar Sobreviventes por estágio; escolhas não disponíveis nos catálogos podem ser anotadas como opções personalizadas curtas.
O estágio 5 registra Cicatrizado e a ficha aplica a penalidade em testes de resistência contra o perigo escolhido; o mestre controla a sessão pelo painel.
Ferimentos Debilitantes são opcionais; o mestre os ativa nas configurações e registra efeito, tratamento e cura na ficha. O gatilho de dano massivo permanece manual.
Antes de criar fichas, o mestre escolhe a progressão da campanha: NEX, Nível de Experiência e Exposição, ou Patentes. A progressão por patentes exige modo Sem Sanidade (PV/PD), registra prestígio por missão e aplica promoções/recuperação conforme o suplemento. A escolha fica bloqueada depois da primeira ficha.

## Ligar e desligar o servidor

No Windows PowerShell, na pasta do projeto, ative o ambiente e inicie o servidor:

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

No Linux/macOS, use:

```bash
source .venv/bin/activate
python manage.py runserver
```

Acesse http://127.0.0.1:8000/. Para desligar, volte ao mesmo terminal onde o servidor está rodando e pressione `Ctrl+C` (ou `Ctrl+Break` no PowerShell).

## Testes e auditorias

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py check --deploy
pip-audit -r requirements.txt
bandit -r . -x ./.venv,./tests
pre-commit install
```

O `check --deploy` deve ser executado com `DEBUG=False` e valores de produção no ambiente. O GitHub Actions simula essa configuração usando `example.invalid`; não é um deploy. Os hooks locais incluem Gitleaks e Bandit; a CI executa testes, auditorias e verifica deriva de migrações.

## Checklist de deploy

- [ ] `DEBUG=False` e `SECRET_KEY` forte, exclusiva e mantida fora do Git.
- [ ] HTTPS obrigatório; configure hosts e origens CSRF exatos.
- [ ] Use banco de produção em vez de SQLite e mantenha backups testados.
- [ ] Troque a senha temporária do superusuário `admin` antes de publicar.
- [ ] Revise proxy confiável, HSTS e o domínio antes de habilitar preload.
- [ ] Ative Dependabot e secret scanning nas configurações do repositório GitHub.

A recuperação de senha por e-mail fica para uma próxima etapa, depois de configurar e validar um serviço de e-mail.

Consulte [docs/COMO_USAR.md](docs/COMO_USAR.md) para as instruções rápidas de jogadores e mestre.
