# Checklist — Gym OS v6.0.0

- [ ] `python manage.py check-config` aprovado no ambiente alvo
- [ ] `python manage.py init-db` conclui em schema 27
- [ ] suíte `python -m pytest -q` 100% verde
- [ ] login operacional e Super Admin validados
- [ ] isolamento entre academias/unidades validado
- [ ] comunicação e inteligência validadas
- [ ] storage privado validado
- [ ] Agent/heartbeat validado quando aplicável
- [ ] mobile inicia e autentica
- [ ] `.env`, bancos, uploads, logs e backups ausentes do Git
- [ ] credenciais de produção rotacionadas e armazenadas fora do repositório
- [ ] backup/rollback preparados
- [ ] `/health/live` e `/health/ready` verdes
- [ ] merge de `develop` para `main` revisado
- [ ] tag `v6.0.0` criada somente após validação final
