import { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Href, router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { studentTheme as t } from '@/constants/student-theme';
import { useAuth } from '@/context/auth-context';
import { ApiError, getApiUrl } from '@/services/api';
import { loginAluno } from '@/services/auth';

const mark = require('../../../assets/images/panobianco-mark-laranja.png');

export default function LoginScreen() {
  const { recarregarAluno } = useAuth();
  const [login, setLogin] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);

  async function entrar() {
    if (!login.trim() || !senha) { setErro('Informe seu usuário ou CPF e sua senha.'); return; }
    setEnviando(true); setErro('');
    try {
      await loginAluno(login.trim(), senha);
      const aluno = await recarregarAluno();
      if (!aluno) throw new Error('Não foi possível carregar os dados do aluno.');
      router.replace('/home' as Href);
    } catch (error) {
      setErro(error instanceof ApiError ? error.message : 'Não foi possível entrar. Tente novamente.');
    } finally { setEnviando(false); }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.brandRow}>
            <Image source={mark} style={styles.mark} resizeMode="contain" />
            <View><Text style={styles.brand}>PANOBIANCO</Text><Text style={styles.brandSub}>MEU APP</Text></View>
          </View>

          <View style={styles.hero}>
            <Text style={styles.eyebrow}>ÁREA DO ALUNO</Text>
            <Text style={styles.title}>Seu treino. Sua evolução.</Text>
            <Text style={styles.description}>Acesse sua ficha, acompanhe seus resultados e mantenha sua rotina em dia.</Text>
          </View>

          <View style={styles.formCard}>
            <Text style={styles.label}>Usuário ou CPF</Text>
            <TextInput value={login} onChangeText={setLogin} autoCapitalize="none" autoCorrect={false} placeholder="Digite seu usuário ou CPF" placeholderTextColor="#9a9691" style={styles.input} />
            <Text style={styles.label}>Senha</Text>
            <TextInput value={senha} onChangeText={setSenha} secureTextEntry placeholder="Digite sua senha" placeholderTextColor="#9a9691" style={styles.input} onSubmitEditing={entrar} />
            {erro ? <Text style={styles.error}>{erro}</Text> : null}
            <Pressable style={({ pressed }) => [styles.button, pressed && styles.pressed, enviando && styles.disabled]} onPress={entrar} disabled={enviando}><Text style={styles.buttonText}>{enviando ? 'Entrando...' : 'Entrar'}</Text></Pressable>
          </View>
          {!getApiUrl() ? <Text style={styles.configWarning}>Configure EXPO_PUBLIC_API_URL em mobile/.env.local.</Text> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 }, safe: { flex: 1, backgroundColor: t.dark }, container: { flexGrow: 1, backgroundColor: t.background, paddingBottom: 34 },
  brandRow: { height: 74, backgroundColor: t.dark, paddingHorizontal: 22, flexDirection: 'row', alignItems: 'center', gap: 10 }, mark: { width: 32, height: 39 }, brand: { color: '#fff', fontSize: 14, fontWeight: '900', letterSpacing: 1 }, brandSub: { color: t.orange, fontSize: 8, fontWeight: '900', letterSpacing: 1.6, marginTop: 2 },
  hero: { paddingHorizontal: 22, paddingTop: 48, paddingBottom: 30 }, eyebrow: { color: t.orange, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 }, title: { color: t.text, fontSize: 35, lineHeight: 39, fontWeight: '900', marginTop: 7, maxWidth: 340 }, description: { color: t.muted, fontSize: 12, lineHeight: 19, marginTop: 11, maxWidth: 340 },
  formCard: { marginHorizontal: 12, backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: 18, padding: 18 }, label: { color: t.text, fontSize: 10, fontWeight: '800', marginBottom: 6, marginTop: 5 }, input: { height: 50, borderWidth: 1, borderColor: t.line, borderRadius: 11, backgroundColor: '#faf9f7', color: t.text, paddingHorizontal: 13, fontSize: 14, marginBottom: 8 },
  error: { color: t.danger, fontSize: 10, lineHeight: 15, marginTop: 2 }, button: { minHeight: 48, borderRadius: 12, backgroundColor: t.orange, alignItems: 'center', justifyContent: 'center', marginTop: 10 }, pressed: { opacity: 0.88 }, disabled: { opacity: 0.55 }, buttonText: { color: '#fff', fontSize: 12, fontWeight: '900' }, configWarning: { color: '#9a6514', fontSize: 10, lineHeight: 15, marginTop: 16, textAlign: 'center', paddingHorizontal: 20 },
});
