# Panobianco Gym OS

Sistema web para operação de academia, reunindo **controle de acesso por reconhecimento facial**, gestão de alunos e professores, prescrição e execução de treinos, avaliações físicas, financeiro integrado ao Asaas e um **PWA para o aluno**.

> **Status:** V5.9.1 permanece como release estável; a V6 está em desenvolvimento no branch `develop`, com app mobile React Native/Expo e API v1.

## Visão geral

O projeto começou como um verificador facial para catraca e evoluiu para uma plataforma de gestão de academia. Hoje há interfaces separadas por papel e regras de permissão para **Administração**, **Recepção**, **Professor** e **Aluno**.

### Principais recursos

- **Controle de acesso** com OpenCV + `face_recognition`, múltiplas amostras faciais, prova de vida heurística por movimento e histórico de liberações/bloqueios.
- **Gestão de alunos** com CPF, matrícula, plano, vencimento, foto, situação financeira, bloqueio/liberação e histórico.
- **Matrícula aleatória** para novos alunos, mantendo compatibilidade com matrículas legadas.
- **Professores** com cadastro, conta de acesso e vínculo exclusivo com alunos.
- **Banco de exercícios** com grupo muscular, equipamento, dificuldade, instruções, imagem e vídeo.
- **Fichas de treino** com treinos, exercícios, séries, repetições, carga, descanso e observações do professor.
- **Execução e histórico** de treinos com snapshot da prescrição, carga anterior, cronômetro de descanso e evolução por exercício.
- **Avaliações físicas** com peso, altura, IMC, composição corporal, medidas, fotos e evolução histórica.
- **Financeiro** com planos, vencimentos, tolerância configurável e cobrança PIX via Asaas Sandbox/webhook.
- **PWA do aluno** com primeiro acesso, treino, histórico, evolução, financeiro, perfil e alteração de senha.
- **App mobile do aluno** em React Native/Expo com autenticação por token, treino real, histórico, evolução, financeiro, notificações, metas semanais, feedback pós-treino e experiência offline básica.
- **Dashboard operacional** com indicadores, alertas e busca global de alunos.
- **Segurança operacional** com papéis/permissões, sessões, CSRF, rate limiting de login, logs administrativos, backups, diagnóstico e verificações de integridade.

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | Python 3.11 + Flask |
| Banco | SQLite |
| Visão computacional | OpenCV + face_recognition + dlib |
| Frontend | HTML, CSS e JavaScript vanilla |
| PWA | Web App Manifest + Service Worker |
| Pagamentos | Asaas API / PIX |
| Relatórios | ReportLab |

## Estrutura do projeto

```text
.
├── app.py                     # Aplicação Flask, páginas e endpoints
├── database.py                # Schema, migrations e persistência SQLite
├── config_service.py          # Configurações operacionais
├── device_manager.py          # Integração/abstração dos dispositivos de acesso
├── face_index.py              # Índice em memória dos encodings faciais
├── validators.py              # Validações compartilhadas
├── services/
│   ├── auth_service.py
│   ├── permissions.py
│   ├── dashboard_service.py
│   ├── professor_service.py
│   ├── exercise_service.py
│   ├── workout_service.py
│   ├── execution_service.py
│   ├── assessment_service.py
│   └── payments/
│       └── asaas_gateway.py
├── templates/                 # Templates Jinja2
├── static/
│   ├── assets/                # Identidade visual
│   ├── css/
│   ├── js/
│   ├── uploads/               # Dados de runtime; não versionados
│   ├── manifest.webmanifest
│   └── sw.js
├── tests/                     # Testes automatizados do núcleo
├── requirements.txt
├── install_windows.ps1
├── .env.example              # Modelo público, sem segredos
├── .env                      # Local e ignorado pelo Git
├── .gitignore
├── CHANGELOG.md
└── SECURITY.md
```

## Instalação no Windows

O ambiente validado usa **Python 3.11 64-bit**. No Windows, o projeto usa `dlib-bin` para evitar compilação local do dlib.

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install face-recognition==1.3.0 --no-deps
```

Ou execute o instalador incluído:

```powershell
.\install_windows.ps1
```

Valide as dependências principais:

```powershell
python -c "import dlib, face_recognition, cv2, numpy; print('dlib:', dlib.__version__); print('face_recognition: OK'); print('OpenCV:', cv2.__version__); print('NumPy:', numpy.__version__)"
```

## Configuração

O projeto carrega automaticamente o arquivo `.env` da raiz usando `python-dotenv`. No pacote local há um `.env` pronto para edição e o Git o ignora; no repositório deve existir apenas o `.env.example`.

Edite estas variáveis antes de usar:

```env
SECRET_KEY=uma-chave-aleatoria-longa
ADMIN_USER=admin
ADMIN_PASSWORD=sua-senha-forte
FLASK_DEBUG=0
PORT=5000

ASAAS_BASE_URL=https://api-sandbox.asaas.com/v3
ASAAS_API_KEY=sua-chave-sandbox
ASAAS_WEBHOOK_TOKEN=seu-token-de-webhook
```

`SECRET_KEY` e `ASAAS_WEBHOOK_TOKEN` já podem ser gerados aleatoriamente no seu `.env` local. Você deve trocar `ADMIN_PASSWORD` e preencher `ASAAS_API_KEY`. Se preferir recriar o arquivo a partir do modelo:

```powershell
Copy-Item .env.example .env
```

> **Importante:** `.env`, `perfis.db`, `static/uploads/` e backups são dados locais e não devem ser commitados. O `.gitignore` já protege esses caminhos, mas sempre confira `git status` antes do primeiro push.

## Executando

Com o ambiente virtual ativo:

```powershell
python app.py
```

A aplicação local fica disponível em:

```text
http://localhost:5000
```

A primeira inicialização cria/migra o banco `perfis.db` automaticamente.

## Perfis de acesso

| Papel | Área principal |
| --- | --- |
| Admin | Dashboard, alunos, professores, usuários, treinos, avaliações, financeiro, configurações e diagnóstico |
| Recepção | Dashboard, alunos, financeiro e operação da catraca |
| Professor | Minha Área, alunos vinculados, exercícios, fichas, execuções e avaliações |
| Aluno | PWA com treino, histórico, evolução, financeiro e perfil |

O aluno pode ativar o primeiro acesso usando os dados previamente cadastrados pela academia. A ativação não cria uma matrícula de academia: ela cria apenas a credencial do aplicativo para um aluno existente.

## PWA do aluno

O PWA pode ser aberto em `/app` depois da autenticação. Para instalação em celular fora de `localhost`, use HTTPS. O Service Worker fornece cache dos recursos essenciais e a navegação inferior prioriza Início, Histórico, Treino, Evolução e Perfil.

## Integração Asaas

A integração financeira está preparada para **Asaas Sandbox**. O fluxo atual contempla criação de cobrança PIX, QR Code/copia-e-cola, webhook, idempotência, histórico de eventos e atualização do estado financeiro do aluno.

Para receber webhooks durante desenvolvimento local, exponha a aplicação por HTTPS (por exemplo, usando um túnel) e configure no Asaas o endpoint:

```text
/webhooks/asaas
```

O token configurado no Asaas deve ser o mesmo de `ASAAS_WEBHOOK_TOKEN`.

## Testes

Os testes do núcleo ficam em `tests/`:

```powershell
python -m unittest discover -s tests -v
```

Antes de publicar uma nova versão, também é recomendável validar:

```powershell
python -m compileall .
```

No banco de desenvolvimento, as verificações importantes são `PRAGMA quick_check` e `PRAGMA foreign_key_check`.

## Dados sensíveis e privacidade

Este sistema pode tratar **dados pessoais e biométricos**, incluindo CPF, fotos e encodings faciais. Por isso:

- `perfis.db` não é versionado;
- `static/uploads/` não é versionado;
- `.env` não é versionado;
- backups devem ser armazenados fora do repositório e protegidos;
- produção deve utilizar HTTPS, credenciais fortes e política adequada de acesso/retenção;
- a base de demonstração/publicação não deve conter dados reais de alunos.

Consulte [SECURITY.md](SECURITY.md) antes de qualquer implantação real.

## Limitações da versão atual

A V5.9.1 ainda é uma arquitetura local/monolítica. Antes de operação pública em escala, a V6 deverá priorizar separação de rotas/repositórios, PostgreSQL, configuração de produção, servidor WSGI, domínio/HTTPS permanente, observabilidade, estratégia de backup e revisão específica do tratamento biométrico.

A prova de vida atual é heurística e **não substitui um mecanismo dedicado de anti-spoofing/liveness** em um cenário de segurança elevado.

## Roadmap

### V6

- modularização do backend em Blueprints e repositories;
- migração SQLite → PostgreSQL;
- configuração de produção e deploy;
- API mais bem delimitada;
- domínio e HTTPS permanentes;
- observabilidade e backups de produção;
- preparação para múltiplas unidades/SaaS.

## Identidade visual

O repositório contém assets com identidade Panobianco. Antes de tornar o projeto público, confirme que você possui autorização para publicar e redistribuir esses arquivos e o uso da marca. Caso contrário, substitua-os por uma identidade própria antes de publicar o repositório.

## Licença

Nenhuma licença de código aberto foi definida neste repositório. Se a intenção for torná-lo público e permitir reutilização por terceiros, escolha uma licença antes da publicação.
