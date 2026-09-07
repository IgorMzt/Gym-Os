# Changelog

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

# Changelog

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
