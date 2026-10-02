# Auditoria de release — v6.0.0

## Resultado

A árvore de distribuição foi reduzida de aproximadamente **448 MB / 8.701 arquivos** para aproximadamente **3,7 MB / ~270 arquivos**, sem incluir dados locais ou dependências instaladas.

## Removido do pacote público

- `.git/` — histórico não faz parte do artefato distribuível;
- `.venv/` — ambiente local (~440 MB);
- `.env` — continha credenciais/segredos de desenvolvimento;
- `.pytest_cache/`, `__pycache__/`, `*.pyc`;
- bancos, logs, backups e arquivos de runtime;
- conteúdo privado de `storage/private/` e uploads locais;
- listas temporárias `V6.*-ARQUIVOS.txt`;
- metadados duplicados dentro de `mobile/src/` (`app.json`, `eas.json`, `package.json`);
- `mobile/LICENSE` herdado do template Expo, que poderia sugerir incorretamente o licenciamento do Gym OS.

## Ajustado

- runtime do produto: `6.0.0`;
- versão do app mobile: `6.0.0`;
- README refeito para apresentação pública;
- documentação separada de arquitetura, instalação, deploy, mobile e Agent;
- `.gitignore` e `.dockerignore` reforçados;
- `requirements-dev.txt` criado para testes;
- changelog consolidado com a release;
- checklist de release criado;
- rótulo interno `V6.16` removido da interface de Inteligência.

## Segurança

O `.env` recebido **não foi incluído** no artefato final. Como ele continha credenciais de desenvolvimento, mantenha-o somente local. Se qualquer valor desse arquivo tiver sido reutilizado fora do ambiente local ou publicado anteriormente, rotacione-o.

Não foram encontrados no pacote final os valores locais conhecidos usados no `.env` recebido.

## Validação executada neste ambiente

- compilação sintática de todos os arquivos Python: aprovada;
- verificação de ausência de `.env`, bancos, logs, bytecode e caches no pacote: aprovada;
- verificação da versão runtime/mobile: `6.0.0`;
- suíte Flask completa: **não executada neste ambiente**, pois ele não possui todas as dependências nativas/backend instaladas.

Antes da tag, execute no ambiente Windows validado:

```powershell
python -m pip install -r requirements-dev.txt
python manage.py init-db
python -m pytest -q
```

O resultado esperado, mantendo a suíte atual, é **82 passed**.
