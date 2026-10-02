# Deploy e checklist de produção

## Antes do deploy

- use `APP_ENV=production` e, no backend central, `APP_ROLE=cloud`;
- use PostgreSQL e storage privado/object storage apropriado;
- gere `SECRET_KEY`, `ADMIN_PASSWORD`, `SAAS_ADMIN_PASSWORD` e `AGENT_API_TOKEN` fortes;
- mantenha chaves Asaas e storage em secret manager/variáveis protegidas;
- habilite HTTPS e `SESSION_COOKIE_SECURE=1`;
- configure `TRUST_PROXY`/`PROXY_HOPS` apenas conforme a topologia real;
- mantenha `FLASK_DEBUG=0` e `AUTO_INIT_DB=0`;
- faça backup verificável antes de migration;
- execute a suíte de testes e `python manage.py check-config`;
- confirme `/health/live` e `/health/ready`.

## Processo sugerido

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-prod.txt
python manage.py check-config
python manage.py init-db
gunicorn --bind 0.0.0.0:8000 wsgi:app
```

Use reverse proxy/TLS na frente do Gunicorn e não exponha diretamente serviços internos, PostgreSQL ou o Agent.

## Dados persistentes

Não trate container filesystem como armazenamento permanente. Banco, object storage, logs necessários e backups devem usar serviços/volumes apropriados.

## Pós-deploy

- smoke test de login e tenant;
- validar Super Admin e uma academia de teste;
- validar upload privado e URL assinada;
- validar Agent/heartbeat em ambiente controlado;
- validar webhook/pagamento em sandbox antes de produção;
- acompanhar eventos de segurança e readiness.

## Rollback

Mantenha a imagem/artefato anterior e backup compatível. Não faça downgrade de schema sem procedimento explícito e testado.
