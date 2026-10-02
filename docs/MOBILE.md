# Aplicativo mobile

O aplicativo do aluno fica em `mobile/` e usa React Native, Expo Router e SecureStore.

## Desenvolvimento

```powershell
cd mobile
npm ci
npx expo start
```

A versão de release do app está alinhada em `6.0.0`. Antes de publicar builds, revise identificadores iOS/Android, projeto EAS, ícones, permissões, URL da API e configuração de push para a conta de distribuição correta.

## Segurança

Access tokens têm vida curta; refresh tokens são rotativos. Não persista tokens em armazenamento não seguro. Builds de produção devem consumir API HTTPS.

## Push

Push remoto depende das credenciais/configurações do provedor e das contas Apple/Google/Expo. A infraestrutura do Gym OS não substitui essas credenciais externas.
