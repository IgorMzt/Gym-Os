import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { StudentShell } from '@/components/student-shell';
import { studentTheme as t } from '@/constants/student-theme';
import { useAuth } from '@/context/auth-context';

function primeiroNome(nome?: string | null) { return (nome || 'Aluno').trim().split(/\s+/)[0]; }
function formatarStatus(status?: string | null) {
  if (!status) return 'Status não informado';
  return status.split('_').join(' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
function dataBr(data?: string | null) {
  if (!data) return '—';
  const [a, m, d] = data.split('-');
  return a && m && d ? `${d}/${m}/${a}` : data;
}

export default function HomeScreen() {
  const { aluno } = useAuth();

  return (
    <StudentShell>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.hello}>
          <View style={styles.flex}>
            <Text style={styles.eyebrow}>OLÁ, {primeiroNome(aluno?.nome).toUpperCase()}</Text>
            <Text style={styles.title}>Pronto para evoluir?</Text>
            <Text style={styles.subtitle}>{aluno?.plano || 'Plano não informado'} · {formatarStatus(aluno?.status_financeiro)}</Text>
          </View>
          <View style={styles.avatar}><Text style={styles.avatarText}>{primeiroNome(aluno?.nome).charAt(0).toUpperCase()}</Text></View>
        </View>

        <View style={styles.nextCard}>
          <Text style={styles.eyebrow}>PRÓXIMO TREINO</Text>
          <Text style={styles.nextTitle}>Seu próximo treino</Text>
          <Text style={styles.nextText}>Ficha e exercícios serão conectados na próxima etapa da API mobile.</Text>
          <View style={styles.nextButton}><Text style={styles.nextButtonText}>Treinos em breve</Text></View>
        </View>

        <View style={styles.grid}>
          <View style={[styles.stat, styles.statWide]}><Text style={styles.statLabel}>TREINOS RECENTES</Text><Text style={styles.statValue}>—</Text><Text style={styles.statHint}>concluídos</Text></View>
          <View style={styles.stat}><Text style={styles.statLabel}>PROFESSOR</Text><Text style={styles.statValueSmall}>A definir</Text><Text style={styles.statHint}>responsável</Text></View>
          <View style={styles.stat}><Text style={styles.statLabel}>ÚLTIMO PESO</Text><Text style={styles.statValueSmall}>—</Text><Text style={styles.statHint}>avaliação física</Text></View>
        </View>

        <View style={styles.financeCard}>
          <View>
            <Text style={styles.eyebrow}>FINANCEIRO</Text>
            <Text style={styles.financeTitle}>{formatarStatus(aluno?.status_financeiro)}</Text>
            <Text style={styles.financeText}>Vencimento {dataBr(aluno?.data_vencimento)}</Text>
          </View>
          <Text style={styles.arrow}>→</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.eyebrow}>ATIVIDADE</Text>
          <Text style={styles.sectionTitle}>Treinos recentes</Text>
          <View style={styles.empty}><Text style={styles.emptyTitle}>Seu histórico aparecerá aqui</Text><Text style={styles.emptyText}>Assim que conectarmos os treinos à API, as últimas sessões ficarão disponíveis nesta área.</Text></View>
        </View>
      </ScrollView>
    </StudentShell>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 12, paddingTop: 20, paddingBottom: 28 }, flex: { flex: 1 },
  hello: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 2, paddingBottom: 20 },
  eyebrow: { color: t.orange, fontSize: 9, fontWeight: '900', letterSpacing: 1.1 },
  title: { color: t.text, fontSize: 29, lineHeight: 31, fontWeight: '900', marginTop: 5 },
  subtitle: { color: t.muted, fontSize: 11, marginTop: 7 },
  avatar: { width: 58, height: 58, borderRadius: 16, backgroundColor: t.dark, alignItems: 'center', justifyContent: 'center', marginLeft: 12 },
  avatarText: { color: t.orange, fontSize: 24, fontWeight: '900' },
  nextCard: { backgroundColor: '#191919', borderRadius: 18, padding: 18, marginBottom: 12 },
  nextTitle: { color: '#fff', fontSize: 19, fontWeight: '900', marginTop: 5 }, nextText: { color: '#bdbdbd', fontSize: 11, lineHeight: 17, marginTop: 6 },
  nextButton: { alignSelf: 'flex-start', minHeight: 44, borderRadius: 12, paddingHorizontal: 16, marginTop: 14, backgroundColor: '#303030', alignItems: 'center', justifyContent: 'center' },
  nextButtonText: { color: '#aaa', fontSize: 11, fontWeight: '800' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 11 },
  stat: { flexGrow: 1, flexBasis: '47%', minHeight: 93, backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 15, padding: 13 },
  statWide: { flexBasis: '100%' }, statLabel: { color: t.muted, fontSize: 8, fontWeight: '700' }, statValue: { color: t.text, fontSize: 22, fontWeight: '900', marginTop: 6 }, statValueSmall: { color: t.text, fontSize: 14, fontWeight: '900', marginTop: 7 }, statHint: { color: t.muted, fontSize: 9, marginTop: 4 },
  financeCard: { minHeight: 84, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, padding: 16, marginBottom: 11 },
  financeTitle: { color: t.text, fontSize: 15, fontWeight: '900', marginTop: 4 }, financeText: { color: t.muted, fontSize: 9, marginTop: 3 }, arrow: { color: t.text, fontSize: 20, fontWeight: '700' },
  section: { backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, padding: 16 }, sectionTitle: { color: t.text, fontSize: 17, fontWeight: '900', marginTop: 3, marginBottom: 9 },
  empty: { paddingVertical: 18, alignItems: 'center' }, emptyTitle: { color: t.text, fontSize: 13, fontWeight: '800' }, emptyText: { color: t.muted, fontSize: 10, lineHeight: 15, textAlign: 'center', marginTop: 6, maxWidth: 310 },
});
