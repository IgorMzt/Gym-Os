import * as SecureStore from 'expo-secure-store';

const ACCESS_KEY = 'gym_os_access_token';
const REFRESH_KEY = 'gym_os_refresh_token';

export async function salvarTokens(accessToken: string, refreshToken: string) {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_KEY, refreshToken),
  ]);
}

export async function obterAccessToken() {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

export async function obterRefreshToken() {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export async function limparTokens() {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}
