# MONOTOFOBIA
Projeto Django da campanha de RPG de mesa "MONOTOFOBIA", dirigida por Samuel Veríssimo.

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
python manage.py createsuperuser
```

O usuário `admin` criado para desenvolvimento anteriormente usa uma senha temporária conhecida. Troque-a com `python manage.py changepassword admin` e não reutilize essa conta/senha em produção.

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
python manage.py test
python manage.py check --deploy
pip-audit -r requirements.txt
bandit -r . -x ./.venv,./tests
pre-commit install
```

O `check --deploy` deve ser executado com `DEBUG=False` e valores reais de produção no ambiente. Os hooks locais incluem Gitleaks e Bandit; o GitHub Actions também executa testes e auditorias.

## Checklist de deploy

- [ ] `DEBUG=False` e `SECRET_KEY` forte, exclusiva e mantida fora do Git.
- [ ] HTTPS obrigatório; configure hosts e origens CSRF exatos.
- [ ] Use banco de produção em vez de SQLite e mantenha backups testados.
- [ ] Troque a senha temporária do superusuário `admin` antes de publicar.
- [ ] Revise proxy confiável, HSTS e o domínio antes de habilitar preload.
- [ ] Ative Dependabot e secret scanning nas configurações do repositório GitHub.

A recuperação de senha por e-mail fica para uma próxima etapa, depois de configurar e validar um serviço de e-mail.
