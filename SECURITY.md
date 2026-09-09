# Segurança

## Dados tratados

A aplicação pode armazenar dados pessoais e biométricos. Banco SQLite, fotos, encodings faciais, backups, logs e credenciais devem ser tratados como dados sensíveis de operação e nunca devem ser publicados no repositório.

## Arquivos que não devem ser commitados

- `.env`
- `perfis.db` e qualquer outro `*.db`
- `static/uploads/*`
- `backups/`
- logs de produção
- chaves de API, tokens e senhas

O `.gitignore` já cobre esses itens, mas ele não protege um segredo que tenha sido commitado anteriormente. Nesse caso, remova-o do histórico e revogue/rotacione a credencial.

## Produção

Antes de implantar em produção:

1. defina `SECRET_KEY`, `ADMIN_USER` e uma senha administrativa forte;
2. não utilize credenciais padrão;
3. utilize HTTPS permanente;
4. configure credenciais do Asaas por variáveis de ambiente/secret manager;
5. restrinja acesso aos backups e ao banco;
6. revise retenção e autorização de dados pessoais/biométricos;
7. utilize um servidor de aplicação apropriado em vez do servidor de desenvolvimento do Flask;
8. substitua/fortaleça a prova de vida heurística caso o nível de risco exija anti-spoofing dedicado;
9. mantenha dependências atualizadas e execute testes antes do deploy.

## Reporte de vulnerabilidades

Se este repositório se tornar público, configure um canal privado de contato para relatos de segurança e substitua esta seção pelo endereço oficial escolhido. Não publique detalhes de uma vulnerabilidade explorável em uma issue pública antes da correção.

## Variáveis de ambiente

A aplicação carrega `.env` localmente com `python-dotenv`. O arquivo real deve permanecer fora do controle de versão. Publique apenas `.env.example`, sem chaves, tokens ou senhas reais.

## V6.9 — produção e separação local/cloud

- `APP_ENV=production` rejeita `SECRET_KEY` insegura, `ADMIN_PASSWORD` padrão e debug ativo.
- Em produção, use HTTPS e `SESSION_COOKIE_SECURE=1`; ao operar atrás de proxy confiável, habilite `TRUST_PROXY=1` apenas para a quantidade real de proxies em `PROXY_HOPS`.
- `AGENT_API_TOKEN` é um segredo de **bootstrap** e nunca deve ser versionado. Use-o somente para registrar/rotacionar agentes autorizados.
- Na V6.11 cada agente recebe um token individual; o backend armazena apenas SHA-256. Revogue o agente no painel se o PC for substituído ou comprometido.
- `DATABASE_URL` e credenciais de object storage nunca devem entrar no Git; o `.env.example` contém somente placeholders.
- `/health/ready` não expõe segredos e deve permanecer útil para orquestração/monitoramento.
- O papel `cloud` não deve executar câmera, reconhecimento facial nem acionar catraca. Esses componentes permanecem no agente/PC local da academia.
## PostgreSQL e migração de dados — V6.10

- `DATABASE_URL` é segredo e nunca deve ser commitada.
- Prefira TLS/SSL exigido pelo provedor no ambiente cloud.
- Migre para um banco vazio e mantenha um backup verificável do SQLite antes da troca.
- O comando `migrate-sqlite` preserva IDs; não execute `--allow-existing` sem revisar conflitos de dados.
- Em PostgreSQL, o botão de backup `.db` não é utilizado. Configure snapshots/backup gerenciado e política de retenção no provedor.
- Bancos com biometria, CPF e dados financeiros exigem controle de acesso mínimo, logs e segregação entre desenvolvimento e produção.


## Agente local — V6.11

- Em produção, `AGENT_SERVER_URL` deve usar **HTTPS**; encodings biométricos não devem trafegar em HTTP público.
- `agent_state.db` contém cache operacional e biométrico e deve receber as mesmas proteções de disco/usuário aplicadas ao banco principal.
- O cache offline é limitado por tempo e falha fechado ao expirar para reduzir o risco de autorização com dados antigos.
- Eventos usam UUID e o servidor aplica idempotência para evitar duplicação após reconexão.
- Tokens individuais devem ser revogados quando uma máquina for perdida, formatada ou transferida.
- Comandos cloud → agente são restritos a uma lista permitida; não existe execução arbitrária de shell.
- Não exponha a API do agente diretamente à internet sem autenticação/reverse proxy apropriados.
- A V6.12 revisará armazenamento, retenção e distribuição dos dados biométricos em profundidade.
