import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { apiAutenticada } from '@/services/api';
import * as SecureStore from 'expo-secure-store';

const PUSH_KEY = 'gymos_expo_push_token';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function registrarPushNoBackend() {
  if (!Device.isDevice) return null;
  const atual = await Notifications.getPermissionsAsync();
  let status = atual.status;
  if (status !== 'granted') status = (await Notifications.requestPermissionsAsync()).status;
  if (status !== 'granted') return null;

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) return null;
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  await apiAutenticada('/api/v1/aluno/notificacoes/device', {
    method: 'POST',
    body: JSON.stringify({
      expo_push_token: token,
      plataforma: Platform.OS,
      device_name: Device.deviceName ?? null,
      app_version: Constants.expoConfig?.version ?? null,
    }),
  });
  await SecureStore.setItemAsync(PUSH_KEY, token);
  return token;
}

export async function removerPushDoBackend() {
  const token = await SecureStore.getItemAsync(PUSH_KEY);
  if (!token) return;
  try {
    await apiAutenticada('/api/v1/aluno/notificacoes/device', {
      method: 'DELETE', body: JSON.stringify({ expo_push_token: token }),
    });
  } finally {
    await SecureStore.deleteItemAsync(PUSH_KEY);
  }
}

export async function enviarPushTeste() {
  return apiAutenticada('/api/v1/aluno/notificacoes/teste', { method: 'POST', body: '{}' });
}
