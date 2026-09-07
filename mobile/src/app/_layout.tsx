import { useEffect } from 'react';
import * as Notifications from 'expo-notifications';
import { Href, router, Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { AuthProvider } from '@/context/auth-context';

function useNotificationNavigation() {
  useEffect(() => {
    const abrir = (notification: Notifications.Notification) => {
      const url = notification.request.content.data?.url;
      if (typeof url === 'string' && url.startsWith('/')) router.push(url as Href);
    };
    const last = Notifications.getLastNotificationResponse();
    if (last?.notification) abrir(last.notification);
    const sub = Notifications.addNotificationResponseReceivedListener((r) => abrir(r.notification));
    return () => sub.remove();
  }, []);
}

export default function RootLayout() {
  useNotificationNavigation();
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          animation: 'fade',
        }}
      />
    </AuthProvider>
  );
}