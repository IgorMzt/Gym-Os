# Gym OS Local Agent — base V6.9

A V6.9 cria apenas o canal de comunicacao entre o backend central e o futuro agente local.
Camera, reconhecimento facial e catraca continuam no processo Flask local atual ate a V6.11.

Teste de conectividade:

```powershell
$env:AGENT_SERVER_URL="http://127.0.0.1:5000"
$env:AGENT_API_TOKEN="mesmo-token-do-backend"
$env:AGENT_ID="academia-principal"
python -m agent.main
```

Na V6.11 este processo recebera os adaptadores de camera, biometria e catraca.
