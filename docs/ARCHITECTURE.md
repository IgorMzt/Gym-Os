# Arquitetura

## Princípios

O Gym OS separa o **plano de controle SaaS** da **operação da academia** e mantém hardware local fora do backend cloud. A aplicação web é organizada em rotas Flask e serviços; persistência passa pela camada de banco compatível com PostgreSQL e, para cenários legados/desenvolvimento, SQLite.

## Componentes

### Backend
`app.py` cria a aplicação; `core/` concentra settings, logging e adaptação de banco; `routes/` expõe interfaces web/API; `services/` concentra regras de negócio. `database.py` mantém a camada de persistência e migrations do schema 27.

### Multi-tenant
Academias e unidades formam o contexto de tenant. Recursos operacionais devem sempre ser consultados e alterados no tenant autenticado. O Super Admin é um plano de controle separado e não deve reutilizar autorização operacional.

### Agent local
`agent/` executa próximo ao hardware. Câmera, biometria e catraca permanecem locais; o Agent sincroniza somente o necessário com o servidor e mantém cache/fila para operação temporariamente offline.

### Storage
Arquivos privados não são servidos diretamente por `/static`. O backend suporta storage local privado e object storage S3/MinIO compatível, com referências persistidas e URLs temporárias quando aplicável.

### Mobile
`mobile/` contém o aplicativo Expo/React Native. A autenticação usa access token de curta duração e refresh token rotativo; tokens sensíveis ficam no SecureStore.

### Comunicação e inteligência
A central de comunicação persiste notificações e comunicados segmentados. A camada de inteligência produz sinais explicáveis e ações assistidas; não deve executar decisões irreversíveis sem autorização explícita do fluxo de negócio.

## Fluxo simplificado

`Cliente → Web/Mobile → Flask → Services → PostgreSQL/Storage`

`Agent local ↔ API autenticada ↔ Flask`

`Super Admin → plano de controle SaaS → academias/planos/assinaturas`

## Banco e migrations

A versão de schema da release é **27**. `python manage.py init-db` deve ser executado de forma controlada antes da troca de tráfego em produção. Faça backup verificável antes de migrations.
