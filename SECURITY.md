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
