import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';

const LEMBRETE_KEY = 'gymos_lembrete_treino_local';

export async function cancelarLembreteTreinoLocal() {
  const id = await SecureStore.getItemAsync(LEMBRETE_KEY);
  if (id) {
    await Notifications.cancelScheduledNotificationAsync(id).catch(() => undefined);
    await SecureStore.deleteItemAsync(LEMBRETE_KEY);
  }
}

export async function sincronizarLembreteTreinoLocal(ativo: boolean, hora: string) {
  await cancelarLembreteTreinoLocal();
  if (!ativo) return { ativo: false };

  const atual = await Notifications.getPermissionsAsync();
  let status = atual.status;
  if (status !== 'granted') status = (await Notifications.requestPermissionsAsync()).status;
  if (status !== 'granted') throw new Error('Permissão de notificações não concedida.');

  const [hour, minute] = hora.split(':').map(Number);
  const id = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Hora do treino 💪',
      body: 'Sua meta da semana está te esperando no Gym OS.',
      data: { url: '/treino', tipo: 'LEMBRETE_LOCAL' },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour,
      minute,
    },
  });
  await SecureStore.setItemAsync(LEMBRETE_KEY, id);
  return { ativo: true, id };
}
