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
