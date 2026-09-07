import { Href, Redirect } from 'expo-router';
import { ActivityIndicator, Image, StyleSheet, Text, View } from 'react-native';

import { studentTheme as t } from '@/constants/student-theme';
import { useAuth } from '@/context/auth-context';

const mark = require('../../assets/images/panobianco-mark-laranja.png');

export default function Index() {
  const { carregando, autenticado } = useAuth();
  if (carregando) {
    return (
      <View style={styles.container}>
        <Image source={mark} style={styles.mark} resizeMode="contain" />
        <Text style={styles.brand}>PANOBIANCO</Text><Text style={styles.sub}>MEU APP</Text>
        <ActivityIndicator size="large" color={t.orange} style={styles.loader} />
      </View>
    );
  }
  return <Redirect href={(autenticado ? '/home' : '/login') as Href} />;
}

const styles = StyleSheet.create({ container: { flex: 1, backgroundColor: t.dark, alignItems: 'center', justifyContent: 'center' }, mark: { width: 58, height: 72 }, brand: { color: '#fff', fontSize: 18, fontWeight: '900', letterSpacing: 2, marginTop: 8 }, sub: { color: t.orange, fontSize: 9, fontWeight: '900', letterSpacing: 2.2, marginTop: 3 }, loader: { marginTop: 28 } });
