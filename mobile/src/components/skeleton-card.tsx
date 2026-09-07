import { StyleSheet, View } from 'react-native';
import { studentTheme as t } from '@/constants/student-theme';

export function SkeletonCard({ linhas = 3 }: { linhas?: number }) {
  return <View style={s.card}>
    <View style={[s.line, { width: '35%' }]} />
    {Array.from({ length: linhas }).map((_, i) => <View key={i} style={[s.line, { width: i === 0 ? '76%' : i === 1 ? '58%' : '88%' }]} />)}
  </View>;
}

const s = StyleSheet.create({
  card: { backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, padding: 16, marginBottom: 10, gap: 10 },
  line: { height: 10, borderRadius: 6, backgroundColor: '#e9e5df' },
});
