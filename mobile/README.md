# Gym OS Mobile

Aplicativo do aluno do Gym OS, desenvolvido com React Native, TypeScript, Expo e Expo Router.

## Desenvolvimento local

1. Copie `.env.example` para `.env.local`.
2. Defina `EXPO_PUBLIC_API_URL` com o IPv4 do computador na rede local, por exemplo `http://192.168.0.15:5000`.
3. Inicie o backend Flask.
4. Execute `npx expo start` nesta pasta e abra pelo Expo Go.

Tokens de sessão são persistidos com Expo SecureStore. O PWA/web continua independente e usa a autenticação web existente.
