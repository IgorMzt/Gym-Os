# Changelog

## V6.14 — SaaS completo

- Super Admin separado do tenant em `/saas`, com dashboard comercial, academias, planos, assinaturas, cupons, checkouts, Agents, CMS e auditoria.
- Schema 24 com planos SaaS, recursos/feature flags, assinaturas, cupons, conteúdo do site, checkouts e branding por academia.
- Portal comercial em `/site`, `/site/recursos` e `/site/planos`, com visual preto/azul-marinho/azul-bebê, efeitos de glow e microinterações.
- Fluxo de aquisição: escolha de plano → cadastro → checkout → provisionamento automático da academia, unidade principal, admin e assinatura.
- Planos dinâmicos com preço mensal/anual, trial, limites e recursos liberados pelo backend.
- Limites de alunos, unidades, professores e Agents aplicados aos tenants SaaS; tenants legados permanecem compatíveis até receberem assinatura.
- Feature flags efetivos para mobile, financeiro, PIX, catraca, biometria, relatórios, Agents e branding.
- Branding/white label por academia com cores, logo, favicon, banner, imagem de login e preview.
- Login pode ser aberto com `?academia=<slug>` para carregar a identidade visual do tenant antes da autenticação.
- CMS do site comercial permite alterar textos e imagens sem redeploy.
- Migração SQLite→PostgreSQL atualizada para transportar as tabelas SaaS da V6.14.
- Novos testes de regressão para schema, checkout/provisionamento, feature flags, limites, cupons, CMS, branding e troca de plano.

## V6.13 — Multiacademia + multiunidade

- Schema atualizado para **23** com `academias` e `unidades`; instalações existentes são absorvidas automaticamente por `principal/principal`.
- Contexto tenant-aware no backend para isolar alunos, usuários, professores, catracas, Agents, logs, storage e configurações.
- Planos e exercícios passam a pertencer à academia; novas academias recebem planos padrão e unidade/catraca iniciais.
- Login web e primeiro acesso aceitam código de academia/unidade.
- Login mobile envia academia/unidade; access/refresh tokens preservam o tenant durante toda a sessão.
- Agents passam a registrar `AGENT_ACADEMIA` e `AGENT_UNIDADE`, sincronizando somente a unidade associada.
- Configurações operacionais usam namespace por academia/unidade para impedir vazamento entre tenants.
- Migração SQLite → PostgreSQL inclui as entidades V6.13, backfill de dados legados e sequences das novas tabelas.
- CLI ganha `tenant-status`, `tenant-create-academia`, `tenant-create-unidade` e `tenant-create-admin`.
- Consultas de fichas, sessões, avaliações e vínculos professor/aluno passam a validar o contexto da unidade nas leituras principais.
- **4 novos testes** específicos de schema, isolamento, refresh mobile e Agent multiunidade; suíte projetada passa de 59 para **63 testes**.

## V6.12 — Storage privado + biometria

- Schema atualizado para **22** com `storage_objects` e `biometric_profiles`.
- Novos uploads deixam de ser públicos em `static/uploads`: no desenvolvimento/piloto são gravados em `storage/private`; em cloud usam object storage S3/MinIO compatível.
- Referências persistidas usam `private://` ou `object://`; caminhos legados continuam compatíveis durante a transição.
- `python manage.py storage-migrate-legacy --dry-run` identifica fotos antigas em `static/uploads`; a execução sem `--dry-run` move os arquivos para o storage privado, atualiza o banco e remove a cópia pública.
- Fotos de alunos, professores, exercícios e avaliações passam pela camada de storage e são exibidas por URL temporária/assinada.
- Metadados de arquivo no PostgreSQL/SQLite incluem categoria, tipo MIME, tamanho, SHA-256, titular lógico, estado de exclusão e data opcional de retenção.
- Exclusão física atualiza o metadado para `DELETED`; `python manage.py storage-purge --dry-run` permite revisar retenções vencidas antes da remoção.
- `python manage.py storage-status` valida o backend de storage e mostra objetos ativos/excluídos.
- Biometria passa a ter versão e quantidade de amostras por aluno; alterações incrementam `biometric_version`.
- Snapshot Cloud → Agent transporta somente encodings necessários e versão biométrica, sem depender da foto para reconhecer o aluno offline.
- Cache SQLite do Agent armazena `biometric_version` e `biometric_sync_version`; novo comando `SYNC_BIOMETRICS` força sincronização controlada.
- Object storage suporta endpoint customizado, região, SSE e URLs pré-assinadas; `boto3` adicionado às dependências.
- Migração SQLite → PostgreSQL inclui as novas tabelas e realinha a sequence de `storage_objects`.
- Preparação LGPD: storage privado por padrão, cache biométrico mínimo no Agent, trilha de metadados, retenção e exclusão.
- **8 novos testes** de schema, storage local/object, migração legada, retenção, versionamento biométrico e sincronização do Agent, levando o repositório a **59 testes**.

## V6.11 — Agente local da academia

- Schema atualizado para **21** com `agentes_locais`, `agente_comandos` e `agente_eventos`.
- Registro seguro de agente usando `AGENT_API_TOKEN` apenas como segredo de bootstrap.
- Cada máquina recebe token individual; o backend armazena somente SHA-256 e permite revogação/rotação.
- Heartbeat persistente com hostname, machine id, versão, capacidades, fila offline e idade do cache.
- Sincronização autenticada do cache mínimo de acesso (alunos, encodings, configurações e catracas).
- Motor local de reconhecimento/autorização com decisão cloud quando online e fallback fail-closed por cache expirado.
- Outbox SQLite persistente no agente para reenviar eventos quando a internet retornar, com idempotência por UUID.
- Comandos cloud → agente: `PING`, `SYNC_ACCESS`, `REFRESH_CONFIG` e `TEST_TURNSTILE`, com ACK/FAILED.
- Painel administrativo `/agentes` para status online/offline, fila, cache e comandos operacionais.
- `python -m agent.main --once --sync` e `--diagnose` adicionados para instalação/diagnóstico.
- `python manage.py agent-status` adicionado no backend.
- Migração SQLite → PostgreSQL passa a incluir as tabelas de agentes.
- **8 novos testes**, levando a suíte para **51 testes**.

## V6.10 — PostgreSQL + persistência cloud

- Schema atualizado para **20** com auditoria `database_migrations`.
- `DATABASE_BACKEND=postgresql` passa a ser efetivo; SQLite continua suportado.
- Driver `psycopg` e pool de conexões configurável por ambiente.
- Adapter preserva a API histórica `conn.execute()` e placeholders `?` no código existente.
- DDL PostgreSQL equivalente ao domínio atual, incluindo índices e unicidade case-insensitive para logins/exercícios.
- Queries de dashboard, histórico, avaliações e duração de treino ajustadas para SQL portátil.
- `manage.py migrate-sqlite` valida e migra `perfis.db` para um PostgreSQL vazio, preservando IDs e sincronizando sequences.
- `manage.py db-status`, `compose.postgres.yml` e smoke test PostgreSQL adicionados.
- Health/readiness agora reporta dinamicamente SQLite ou PostgreSQL.
- Backup/restauração `.db` permanecem exclusivos do SQLite; PostgreSQL deve usar snapshot/pg_dump/pg_restore do ambiente.
- 7 testes adicionais de schema, configuração, tradutor SQL e inspeção de origem SQLite.

## V6.8 — Experiência Mobile

- Schema 19 com preferências do aluno e feedback pós-treino.
- Home inteligente com meta semanal, streak, volume, recordes e conquistas.
- Próximo treino e sessão em andamento conectados diretamente à Home.
- Resumo pós-treino com duração, volume e percepção de esforço de 1 a 5.
- Meta semanal configurável e lembrete local diário de treino.
- Indicador offline e cache em memória para GETs já carregados durante a sessão.
- Skeletons, pull-to-refresh e estados de erro/sem conexão aprimorados.
- Perfil com Preferências e informações da versão mobile.
- Quatro novos testes automatizados da experiência mobile.

## V6.7 — Notificações Push

- Schema 18 com dispositivos push por aluno.
- Registro e remoção de Expo Push Token via API mobile.
- Expo Notifications + Development Build/EAS.
- Deep links de notificações para Treino e Financeiro.
- Push automático para nova ficha ativa, pagamento confirmado e mensalidade vencida.
- Endpoint e botão de teste no Perfil.



## V6.6 — Financeiro completo no mobile

- API bearer-token do financeiro do aluno com status efetivo, plano, vencimento, tolerância e histórico de cobranças.
- Geração/reutilização de cobrança PIX via integração Asaas já existente.
- Tela nativa Financeiro com QR Code, PIX copia e cola selecionável e histórico.
- Atalhos para Financeiro na Home e no Perfil.
- Mantém o schema 17; nenhuma migração de banco é necessária.
- Novos testes da API financeira mobile.

## V6.5 — Histórico e evolução no mobile

- API mobile de histórico de treinos, estatísticas e detalhe de sessão.
- API mobile de avaliações físicas, comparação com a avaliação anterior e detalhe.
- Tela nativa de Histórico com KPIs, sessões concluídas, cargas recentes e detalhe de cada treino.
- Tela nativa de Evolução com última avaliação, deltas, mini gráfico e linha do tempo de avaliações.
- Mantém o schema 17; nenhuma migração de banco é necessária.
- Novos testes de API mobile para histórico/evolução.

## V6.4 - em desenvolvimento
- Treinos reais expostos na API mobile com ficha ativa e próximo treino.
- Execução de treino no app com séries, repetições, carga, observações e última execução.
- Cronômetro de descanso com +15s e pular, conclusão e cancelamento de sessão.

## V6.3 - em desenvolvimento
- Início do aplicativo mobile do aluno com React Native, TypeScript, Expo e Expo Router.
- Login mobile conectado à API v1, com tokens persistidos no Expo SecureStore.
- Sessão persistente com renovação automática do access token via refresh token rotativo.
- Home inicial do aluno consumindo `GET /api/v1/aluno/me`.
- Logout mobile com revogação do refresh token e limpeza do armazenamento seguro.
- Servidor de desenvolvimento Flask preparado para acesso do celular na rede local.
- Interface mobile alinhada à identidade do PWA do aluno: fundo claro, cabeçalho preto, laranja Panobianco e navegação inferior de cinco áreas.
- Estrutura visual inicial de Histórico, Treino, Evolução e Perfil adicionada para receber os próximos endpoints da API.

## V6.2 - em desenvolvimento

- Adicionada base da API REST mobile em `/api/v1`.
- Login exclusivo de aluno com access token curto e refresh token rotativo.
- Refresh tokens persistidos apenas por hash, com revogação e rotação.
- Adicionado `GET /api/v1/aluno/me` para o perfil autenticado.
- CSRF web não é aplicado à API bearer-token; o PWA e sessões web permanecem inalterados.
- Schema atualizado para 17 com `mobile_refresh_tokens`.


## V6.1 - em desenvolvimento
- Modularização completa das rotas Flask em Blueprints por domínio.
- `app.py` reduzido ao bootstrap, segurança global, filtros e registro dos módulos.
- Helpers web compartilhados centralizados em `routes/common.py`.
- Endpoints internos e referências `url_for()` atualizados para os namespaces dos Blueprints.
- Sem alteração de regras de negócio, banco de dados ou interface.

## V6.1.1 - em desenvolvimento

- Início da modularização Flask com Blueprint dedicado à autenticação.
- Rotas de login, logout e primeiro acesso extraídas do `app.py`.
- Endpoints de autenticação atualizados sem alterar regras de negócio ou telas.

## 5.9.1

- Primeiro acesso do aluno por CPF, matrícula e data de nascimento.
- Matrículas aleatórias para novos alunos, preservando matrículas existentes.
- Login do aluno por usuário ou CPF e alteração de senha no PWA.
- Navegação do PWA reorganizada e Home com próximo treino sugerido.
- Última carga, orientação do professor, descanso e evolução por exercício.
- Indicadores operacionais adicionais para professores.
- Duplicação de fichas de treino.
- Busca global de alunos para Administração/Recepção.

## 5.9

- Financeiro dentro do PWA do aluno.
- PIX via Asaas, persistência do QR Code, histórico e atualização por webhook.

## 5.8

- PWA do aluno com treino, histórico, evolução e perfil.
- Credenciais próprias de aluno separadas das contas da equipe.

## 5.7

- Avaliações físicas, fotos e evolução corporal.

## 5.6

- Execução e histórico de treinos com snapshots da prescrição.

## 5.5

- Fichas e prescrição de treinos.
- Autogestão do vínculo professor/aluno.

## 5.4

- Banco de exercícios.

## 5.3

- Cadastro de professores e vínculo com alunos.

## 5.2

- Usuários, autenticação e papéis de acesso.

## 5.1

- Integração financeira com Asaas Sandbox e PIX.

## 5.0

- Dashboard executivo e consolidação do sistema como Gym OS.

## Preparação para GitHub

- carregamento local de `.env` com `python-dotenv`;
- `.env.example` sanitizado;
- segredos, banco, uploads e artefatos de runtime ignorados pelo Git.

## V6.9 — Preparação Cloud/Produção

- App factory `create_app()` mantendo compatibilidade com `python app.py`.
- Configuração central por `APP_ENV` e `APP_ROLE`.
- Validação fail-fast de segredos, senha administrativa e debug em produção.
- `ProxyFix`, cookie seguro/HSTS configuráveis e `X-Request-ID` em respostas.
- Logging central com stdout e rotação opcional em disco.
- `wsgi.py`, `requirements-prod.txt` e comandos `manage.py check-config/init-db`.
- Health checks `/health/live`, `/health/ready` e compatibilidade `/health`.
- Readiness explicita as pendências PostgreSQL/object storage antes do deploy cloud.
- Abstração inicial de uploads em `services/storage_service.py` sem alterar o formato existente `uploads/...`.
- `DATABASE_BACKEND`, `DATABASE_URL` e `SQLITE_PATH` preparados para a V6.10; SQLite continua efetivo nesta etapa.
- Operações de catraca/biometria marcadas como locais quando `APP_ROLE=cloud`.
- Base do agente local em `agent/`, com heartbeat autenticado em `/api/v1/agent/heartbeat`.
- Schema permanece **19**; V6.9 é arquitetural e não exige migração de dados.
- 5 testes adicionais para configuração de produção, readiness, storage e agente local.
