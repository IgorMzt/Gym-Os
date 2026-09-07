import { PropsWithChildren } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Href, router, usePathname } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/context/auth-context';
import { studentTheme as t } from '@/constants/student-theme';

const mark = require('../../assets/images/panobianco-mark-laranja.png');

type Tab = { label: string; route: Href; icon: string; central?: boolean };
const tabs: Tab[] = [
  { label: 'Início', route: '/home' as Href, icon: '⌂' },
  { label: 'Histórico', route: '/historico' as Href, icon: '↶' },
  { label: 'Treino', route: '/treino' as Href, icon: '↔', central: true },
  { label: 'Evolução', route: '/evolucao' as Href, icon: '↗' },
  { label: 'Perfil', route: '/perfil' as Href, icon: '●' },
];

export function StudentShell({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const { aluno } = useAuth();
  const primeiroNome = (aluno?.nome || 'Aluno').trim().split(/\s+/)[0];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable style={styles.brand} onPress={() => router.replace('/home' as Href)}>
          <Image source={mark} style={styles.mark} resizeMode="contain" />
          <View>
            <Text style={styles.brandName}>PANOBIANCO</Text>
            <Text style={styles.brandSub}>MEU APP</Text>
          </View>
        </Pressable>
        <Text style={styles.userName}>{primeiroNome}</Text>
      </View>

      <View style={styles.body}>{children}</View>

      <SafeAreaView style={styles.navSafe} edges={['bottom']}>
        <View style={styles.nav}>
          {tabs.map((tab) => {
            const active = pathname === String(tab.route);
            return (
              <Pressable key={tab.label} onPress={() => router.replace(tab.route)} style={[styles.tab, tab.central && styles.centralTab]}>
                {tab.central ? (
                  <View style={[styles.centralButton, active && styles.centralButtonActive]}><Text style={styles.centralIcon}>{tab.icon}</Text></View>
                ) : (
                  <Text style={[styles.icon, active && styles.active]}>{tab.icon}</Text>
                )}
                <Text style={[styles.tabLabel, active && styles.active]}>{tab.label}</Text>
                {!tab.central && active ? <View style={styles.indicator} /> : null}
              </Pressable>
            );
          })}
        </View>
      </SafeAreaView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: t.dark },
  header: { height: 66, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: t.dark },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  mark: { width: 30, height: 36 },
  brandName: { color: '#fff', fontSize: 13, fontWeight: '900', letterSpacing: 0.7 },
  brandSub: { color: t.orange, fontSize: 8, fontWeight: '900', letterSpacing: 1.5, marginTop: 1 },
  userName: { color: '#c2c2c2', fontSize: 11, fontWeight: '700' },
  body: { flex: 1, backgroundColor: t.background },
  navSafe: { backgroundColor: t.dark },
  nav: { height: 72, flexDirection: 'row', backgroundColor: 'rgba(17,17,17,0.99)', overflow: 'visible' },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 3, position: 'relative' },
  centralTab: { transform: [{ translateY: -10 }] },
  icon: { color: '#8f8f8f', fontSize: 22, fontWeight: '800', height: 25 },
  tabLabel: { color: '#8f8f8f', fontSize: 8, fontWeight: '800' },
  active: { color: '#fff' },
  indicator: { position: 'absolute', bottom: 7, width: 18, height: 2, borderRadius: 2, backgroundColor: t.orange },
  centralButton: { width: 52, height: 52, borderRadius: 26, backgroundColor: t.orange, alignItems: 'center', justifyContent: 'center', shadowColor: '#f45a20', shadowOpacity: 0.28, shadowRadius: 11, shadowOffset: { width: 0, height: 8 }, elevation: 8 },
  centralButtonActive: { transform: [{ scale: 1.04 }] },
  centralIcon: { color: '#fff', fontSize: 28, fontWeight: '900', transform: [{ rotate: '90deg' }] },
});
