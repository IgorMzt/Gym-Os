import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { StudentShell } from '@/components/student-shell';
import { studentTheme as t } from '@/constants/student-theme';

type Props = { eyebrow: string; title: string; description: string; cardTitle: string; cardText: string };

export function StudentPlaceholder({ eyebrow, title, description, cardTitle, cardText }: Props) {
  return (
    <StudentShell>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.head}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.description}>{description}</Text>
        </View>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{cardTitle}</Text>
          <Text style={styles.cardText}>{cardText}</Text>
        </View>
      </ScrollView>
    </StudentShell>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 12, paddingTop: 18, paddingBottom: 30 },
  head: { paddingHorizontal: 2, paddingBottom: 18 },
  eyebrow: { color: t.orange, fontSize: 9, fontWeight: '900', letterSpacing: 1.1 },
  title: { color: t.text, fontSize: 29, lineHeight: 31, fontWeight: '900', marginTop: 5 },
  description: { color: t.muted, fontSize: 11, lineHeight: 17, marginTop: 7, maxWidth: 340 },
  card: { backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, padding: 24, alignItems: 'center' },
  cardTitle: { color: t.text, fontSize: 16, fontWeight: '900', textAlign: 'center' },
  cardText: { color: t.muted, fontSize: 10, lineHeight: 16, textAlign: 'center', marginTop: 8, maxWidth: 310 },
});
