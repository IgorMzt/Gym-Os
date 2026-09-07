import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Href, router } from 'expo-router';

import { StudentShell } from '@/components/student-shell';
import { studentTheme as t } from '@/constants/student-theme';
import { useAuth } from '@/context/auth-context';
import { logoutAluno } from '@/services/auth';

function valor(v?: string | null) { return v || '—'; }

export default function PerfilScreen() {
  const { aluno, definirAluno } = useAuth();
  const [saindo, setSaindo] = useState(false);
  const inicial = (aluno?.nome || 'A').trim().charAt(0).toUpperCase();

  async function sair() {
    setSaindo(true);
    try { await logoutAluno(); } finally { definirAluno(null); setSaindo(false); router.replace('/login' as Href); }
  }

  return (
    <StudentShell>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profile}>
          <View style={styles.photo}><Text style={styles.photoText}>{inicial}</Text></View>
          <Text style={styles.name}>{valor(aluno?.nome)}</Text>
          <Text style={styles.meta}>Matrícula {valor(aluno?.matricula)}</Text>
        </View>
        <View style={styles.card}>
          <Row label="E-mail" value={valor(aluno?.email)} />
          <Row label="Telefone" value={valor(aluno?.telefone)} />
          <Row label="Plano" value={valor(aluno?.plano)} />
          <Row label="Vencimento" value={valor(aluno?.data_vencimento)} last />
        </View>
        <Pressable style={styles.logout} onPress={sair} disabled={saindo}><Text style={styles.logoutText}>{saindo ? 'Saindo...' : 'Sair da conta'}</Text></Pressable>
      </ScrollView>
    </StudentShell>
  );
}

function Row({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return <View style={[styles.row, last && styles.rowLast]}><Text style={styles.rowLabel}>{label}</Text><Text style={styles.rowValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 12, paddingTop: 16, paddingBottom: 28 },
  profile: { alignItems: 'center', paddingVertical: 12 }, photo: { width: 86, height: 86, borderRadius: 24, backgroundColor: t.dark, alignItems: 'center', justifyContent: 'center' }, photoText: { color: t.orange, fontSize: 30, fontWeight: '900' },
  name: { color: t.text, fontSize: 22, fontWeight: '900', marginTop: 10 }, meta: { color: t.muted, fontSize: 10, marginTop: 3 },
  card: { backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, paddingHorizontal: 16, marginTop: 10 },
  row: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: 1, borderBottomColor: t.line }, rowLast: { borderBottomWidth: 0 }, rowLabel: { color: t.muted, fontSize: 10 }, rowValue: { color: t.text, fontSize: 10, fontWeight: '800', textAlign: 'right', flexShrink: 1 },
  logout: { paddingVertical: 19, alignItems: 'center', marginTop: 7 }, logoutText: { color: t.danger, fontSize: 11, fontWeight: '900' },
});
