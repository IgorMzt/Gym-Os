# Gym OS Local Agent — V6.11

O agente roda **na academia**. Camera, reconhecimento facial e acionamento da
catraca permanecem locais; o backend cloud centraliza cadastro, regras, logs e
comandos.

## Fluxo

1. O agente se registra uma vez com `AGENT_API_TOKEN` (segredo de bootstrap).
2. O servidor emite um token individual e armazena somente o hash.
3. O agente sincroniza um cache minimo de alunos/encodings/catracas.
4. Acesso online usa a decisao do cloud; sem internet, o cache pode decidir por
   uma janela limitada (`AGENT_OFFLINE_CACHE_MAX_MINUTES`).
5. Eventos ficam em uma outbox SQLite e sao reenviados idempotentemente.
6. O cloud pode enviar `PING`, `SYNC_ACCESS` e `TEST_TURNSTILE`.

## Teste local

```powershell
$env:AGENT_SERVER_URL="http://127.0.0.1:5000"
$env:AGENT_API_TOKEN="mesmo-bootstrap-do-backend"
$env:AGENT_UID="academia-principal-pc01"
python -m agent.main --once --sync
python -m agent.main --diagnose
```

O arquivo `agent_state.db` e runtime local e **nao deve ser commitado**.
