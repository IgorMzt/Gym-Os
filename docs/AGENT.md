# Agent local

O Agent conecta a instalação física da academia ao Gym OS sem mover a responsabilidade de câmera/catraca para o backend cloud.

## Capacidades

- heartbeat autenticado;
- cache local de acesso e biometria mínima;
- fila offline com retry/idempotência;
- sincronização de configuração/acesso/biometria;
- comandos permitidos como diagnóstico e sincronização;
- integração com hardware por abstrações locais.

## Comandos

```powershell
python -m agent.main --diagnose
python -m agent.main --once --sync
python manage.py agent-status
```

## Produção

Use HTTPS para `AGENT_SERVER_URL`, proteja o estado local da máquina e revogue tokens quando um equipamento for perdido, substituído ou transferido. Não exponha uma interface de execução arbitrária de comandos.
