# Gym OS

> Plataforma SaaS de gestão de academias com operação web, aplicativo do aluno, controle de acesso, biometria, pagamentos, comunicação e inteligência operacional.

**Release atual:** `v6.0.0` · **Schema:** `27` · **Backend:** Python 3.11 / Flask · **Banco recomendado:** PostgreSQL 17 · **Mobile:** React Native + Expo

## Visão geral

O Gym OS reúne em um único produto a rotina administrativa da academia e a experiência do aluno. A aplicação foi construída para operar em modelo multiacademia/multiunidade, mantendo isolamento de tenant e separando o plano de controle SaaS da operação de cada cliente.

### Destaques

- **SaaS e multiacademia:** Super Admin, planos, assinaturas, cupons, feature flags, onboarding e branding por academia.
- **Gestão operacional:** alunos, professores, exercícios, fichas, avaliações, financeiro, dashboards e permissões.
- **Controle de acesso:** Agent local, catraca, cache offline, sincronização, comandos remotos e reconhecimento facial.
- **Storage privado e biometria:** arquivos fora de `/static`, URLs temporárias e sincronização biométrica mínima para o Agent.
- **Aplicativo do aluno:** treinos, histórico, evolução, financeiro, notificações, metas e experiência offline básica.
- **Comunicação:** comunicados segmentados, central de notificações, preferências, push e deep links.
- **Inteligência operacional:** sinais explicáveis de inatividade, queda de frequência e risco financeiro, com ações assistidas.
- **Hardening:** rate limiting, eventos de segurança, headers defensivos, auditoria, health/readiness e validações de produção.

## Arquitetura

```text
                         ┌──────────────────────┐
                         │   Portal / SaaS      │
                         │   Super Admin        │
                         └──────────┬───────────┘
                                    │
┌──────────────┐          ┌─────────▼──────────┐          ┌─────────────────┐
│ Web / PWA    │─────────▶│ Flask / REST API   │◀─────────│ App React Native │
└──────────────┘          │ Services + Tenant  │          └─────────────────┘
                          └──────┬───────┬─────┘
                                 │       │
                       ┌─────────▼─┐   ┌─▼──────────────┐
                       │PostgreSQL │   │ Storage privado│
                       └───────────┘   └────────────────┘
                                 ▲
                                 │ HTTPS / sync
                          ┌──────┴────────┐
                          │ Agent local   │
                          │ câmera/catraca│
                          └───────────────┘
```

Detalhes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Estrutura

```text
agent/       Agent local e operação offline
core/        settings, banco, logging e infraestrutura
routes/      páginas web e APIs
services/    regras de negócio e integrações
templates/   interfaces Jinja2
static/      CSS, JS e assets públicos
storage/     storage privado local (conteúdo não versionado)
mobile/      aplicativo React Native / Expo
tests/       suíte automatizada
docs/        documentação técnica e operacional
```

## Instalação rápida — Windows

Pré-requisitos: **Python 3.11 64-bit**, Git e, para PostgreSQL local, Docker Desktop.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
.\install_windows.ps1
Copy-Item .env.example .env
```

Para desenvolvimento com PostgreSQL:

```powershell
docker compose -f compose.postgres.yml up -d
python manage.py init-db
python -m pytest -q
python app.py
```

A aplicação local fica em `http://127.0.0.1:5000`.

> O arquivo `.env` contém segredos e **não deve ser commitado**. O pacote de release contém somente `.env.example`.

Guia completo: [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## Configuração

Os principais grupos de variáveis estão documentados em `.env.example`:

- runtime: `APP_ENV`, `APP_ROLE`, `SECRET_KEY`;
- banco: `DATABASE_BACKEND`, `DATABASE_URL`;
- storage: `STORAGE_BACKEND` e credenciais do object storage;
- Agent: `AGENT_*`;
- pagamentos: `ASAAS_*`;
- SaaS: `SAAS_ADMIN_*`, `SAAS_CHECKOUT_MODE`.

Em produção, use PostgreSQL, HTTPS, cookies seguros, credenciais fortes e um secret manager. Execute `python manage.py check-config` antes do deploy.

## Testes

Instale as ferramentas de desenvolvimento:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

A release candidate foi preparada sobre uma base que possuía **82 testes automatizados passando** antes da limpeza de release. Rode a suíte novamente no ambiente de destino antes de criar a tag.

## Mobile

```powershell
cd mobile
npm ci
npx expo start
```

Configuração e observações: [`docs/MOBILE.md`](docs/MOBILE.md).

## Agent local

O Agent mantém hardware e biometria fora do backend cloud. Ele possui heartbeat, cache de acesso, fila offline, sincronização e comandos controlados.

```powershell
python -m agent.main --diagnose
python -m agent.main --once --sync
```

Veja [`docs/AGENT.md`](docs/AGENT.md).

## Produção

O Flask development server não é o servidor de produção. A configuração Linux/cloud inclui `wsgi.py` e dependências WSGI em `requirements-prod.txt`.

Checklist completo: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Endpoints operacionais:

- `/health/live` — processo ativo;
- `/health/ready` — dependências/configuração prontas;
- `/health` — compatibilidade.

## Segurança e privacidade

O sistema pode processar CPF, informações financeiras, fotos e dados biométricos. Não publique bancos, uploads, encodings, logs, backups ou credenciais. Leia [`SECURITY.md`](SECURITY.md) antes de qualquer implantação pública.

## Histórico

O desenvolvimento da linha V6 introduziu, em sequência, API/mobile, PostgreSQL, Agent local, storage/biometria, multiacademia, SaaS, comunicação, inteligência e hardening. O histórico detalhado está em [`CHANGELOG.md`](CHANGELOG.md).

## Release v6.0.0

Esta é a primeira consolidação da arquitetura V6 como release. O schema de dados permanece em **27**; `6.0.0` é a versão do produto e não reinicia a numeração das migrations.

## Licenciamento

Este repositório não declara automaticamente uma licença de código aberto. Antes de distribuição pública ou uso por terceiros, o mantenedor deve escolher e adicionar o arquivo `LICENSE` apropriado.
