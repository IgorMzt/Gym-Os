import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Href, router, useFocusEffect } from 'expo-router';

import { StudentShell } from '@/components/student-shell';
import { SkeletonCard } from '@/components/skeleton-card';
import { studentTheme as t } from '@/constants/student-theme';
import { useAuth } from '@/context/auth-context';
import { ExperienciaResponse, obterExperiencia } from '@/services/experiencia';
import { iniciarTreino } from '@/services/treinos';

const nome = (v?: string | null) => (v || 'Aluno').trim().split(/\s+/)[0];
const horas = (min: number) => min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}min` : `${min} min`;

export default function HomeScreen() {
  const { aluno } = useAuth();
  const [dados, setDados] = useState<ExperienciaResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [erro, setErro] = useState('');
  const [iniciando, setIniciando] = useState(false);

  const carregar = useCallback(async (refresh = false) => {
    try { if (refresh) setRefreshing(true); setErro(''); setDados(await obterExperiencia()); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível carregar a Home.'); }
    finally { setCarregando(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { setCarregando(true); carregar(); }, [carregar]));

  async function iniciarProximo() {
    if (!dados?.proximo_treino) return;
    try { setIniciando(true); const r = await iniciarTreino(dados.proximo_treino.id); router.push(`/execucao/${r.id}` as Href); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível iniciar o treino.'); }
    finally { setIniciando(false); }
  }

  return <StudentShell><ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => carregar(true)} />}>
    <View style={s.hello}><View style={{flex:1}}><Text style={s.eyebrow}>BOA SESSÃO, {nome(aluno?.nome).toUpperCase()}</Text><Text style={s.title}>Sua semana em foco.</Text><Text style={s.subtitle}>Treine com consistência e acompanhe sua evolução.</Text></View><View style={s.avatar}><Text style={s.avatarText}>{nome(aluno?.nome)[0].toUpperCase()}</Text></View></View>
    {erro ? <View style={s.error}><Text style={s.errorText}>{erro}</Text></View> : null}
    {carregando && !dados ? <><SkeletonCard linhas={3}/><SkeletonCard linhas={2}/><ActivityIndicator color={t.orange}/></> : null}
    {dados ? <>
      <View style={s.weekCard}><View style={s.weekHead}><View><Text style={s.darkEyebrow}>SUA SEMANA</Text><Text style={s.weekValue}>{dados.semana.realizados}/{dados.semana.meta} treinos</Text></View><Text style={s.percent}>{dados.semana.progresso_percentual}%</Text></View><View style={s.progress}><View style={[s.progressBar,{width:`${dados.semana.progresso_percentual}%`}]} /></View><View style={s.weekMeta}><Text style={s.weekMetaText}>🔥 {dados.streak_dias} dias de sequência</Text><Text style={s.weekMetaText}>{horas(dados.semana.duracao_minutos)}</Text></View></View>

      {dados.sessao_em_andamento ? <Pressable style={s.nextCard} onPress={() => router.push(`/execucao/${dados.sessao_em_andamento!.id}` as Href)}><Text style={s.eyebrow}>TREINO EM ANDAMENTO</Text><Text style={s.nextTitle}>{dados.sessao_em_andamento.treino_nome}</Text><Text style={s.nextText}>{dados.sessao_em_andamento.exercicios_concluidos}/{dados.sessao_em_andamento.total_exercicios} exercícios concluídos</Text><Text style={s.nextAction}>Continuar treino →</Text></Pressable> : dados.proximo_treino ? <View style={s.nextCard}><Text style={s.eyebrow}>PRÓXIMO TREINO</Text><Text style={s.nextTitle}>{dados.proximo_treino.nome}</Text><Text style={s.nextText}>{dados.proximo_treino.exercicios?.length || 0} exercícios · {dados.ficha?.nome || 'Ficha ativa'}</Text><Pressable style={s.start} onPress={iniciarProximo} disabled={iniciando}><Text style={s.startText}>{iniciando ? 'Iniciando...' : 'Iniciar treino'}</Text></Pressable></View> : null}

      <View style={s.grid}><View style={s.stat}><Text style={s.statLabel}>TEMPO NA SEMANA</Text><Text style={s.statValue}>{horas(dados.semana.duracao_minutos)}</Text></View><View style={s.stat}><Text style={s.statLabel}>VOLUME</Text><Text style={s.statValue}>{dados.semana.volume_kg.toLocaleString('pt-BR')} kg</Text></View><View style={s.stat}><Text style={s.statLabel}>RECORDES 30D</Text><Text style={s.statValue}>{dados.recordes_30_dias.length}</Text></View><View style={s.stat}><Text style={s.statLabel}>PROFESSOR</Text><Text style={s.statSmall}>{dados.professor?.professor_nome || dados.ficha?.professor_nome || 'A definir'}</Text></View></View>

      {dados.recordes_30_dias.length ? <View style={s.section}><Text style={s.eyebrow}>EVOLUÇÃO</Text><Text style={s.sectionTitle}>Recordes recentes</Text>{dados.recordes_30_dias.slice(0,3).map(r => <View key={`${r.exercicio_id}-${r.data}`} style={s.row}><Text style={s.rowName}>{r.exercicio_nome}</Text><Text style={s.record}>+ PR · {r.carga_kg} kg</Text></View>)}</View> : null}
      <View style={s.section}><Text style={s.eyebrow}>CONQUISTAS</Text><Text style={s.sectionTitle}>Seu progresso</Text><View style={s.badges}>{dados.conquistas.map(c => <View key={c.id} style={[s.badge,!c.desbloqueada&&s.badgeLocked]}><Text style={s.badgeIcon}>{c.desbloqueada?'✓':'○'}</Text><Text style={s.badgeTitle}>{c.titulo}</Text></View>)}</View></View>
      <Pressable style={s.financeCard} onPress={() => router.push('/financeiro' as Href)}><View><Text style={s.eyebrow}>FINANCEIRO</Text><Text style={s.financeTitle}>{aluno?.status_financeiro?.replaceAll('_',' ') || 'Consultar situação'}</Text></View><Text style={s.arrow}>→</Text></Pressable>
    </> : null}
  </ScrollView></StudentShell>;
}

const s=StyleSheet.create({
  content:{padding:14,paddingTop:20,paddingBottom:30},hello:{flexDirection:'row',alignItems:'center',gap:12,marginBottom:17},eyebrow:{color:t.orange,fontSize:9,fontWeight:'900',letterSpacing:1.1},title:{color:t.text,fontSize:29,lineHeight:31,fontWeight:'900',marginTop:5},subtitle:{color:t.muted,fontSize:10,lineHeight:15,marginTop:6},avatar:{width:56,height:56,borderRadius:17,backgroundColor:t.dark,alignItems:'center',justifyContent:'center'},avatarText:{color:t.orange,fontSize:23,fontWeight:'900'},error:{backgroundColor:'#fff0ed',padding:11,borderRadius:12,marginBottom:10},errorText:{color:t.danger,fontSize:10,fontWeight:'700'},weekCard:{backgroundColor:t.dark,borderRadius:19,padding:17,marginBottom:11},weekHead:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},darkEyebrow:{color:'#9f9f9f',fontSize:8,fontWeight:'900',letterSpacing:1},weekValue:{color:'#fff',fontSize:21,fontWeight:'900',marginTop:4},percent:{color:t.orange,fontSize:20,fontWeight:'900'},progress:{height:7,backgroundColor:'#333',borderRadius:5,overflow:'hidden',marginTop:14},progressBar:{height:7,backgroundColor:t.orange,borderRadius:5},weekMeta:{flexDirection:'row',justifyContent:'space-between',marginTop:10},weekMetaText:{color:'#bbb',fontSize:9,fontWeight:'700'},nextCard:{backgroundColor:'#fff',borderWidth:1.5,borderColor:'#f0b29a',borderRadius:19,padding:17,marginBottom:11},nextTitle:{color:t.text,fontSize:21,fontWeight:'900',marginTop:5},nextText:{color:t.muted,fontSize:10,marginTop:5},nextAction:{color:t.text,fontSize:11,fontWeight:'900',marginTop:13},start:{backgroundColor:t.orange,minHeight:46,borderRadius:12,alignItems:'center',justifyContent:'center',marginTop:14},startText:{color:'#fff',fontSize:11,fontWeight:'900'},grid:{flexDirection:'row',flexWrap:'wrap',gap:8,marginBottom:11},stat:{width:'48%',flexGrow:1,minHeight:92,backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:15,padding:13},statLabel:{color:t.muted,fontSize:7,fontWeight:'900',letterSpacing:.8},statValue:{color:t.text,fontSize:18,fontWeight:'900',marginTop:8},statSmall:{color:t.text,fontSize:12,fontWeight:'900',marginTop:9},section:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:16,marginBottom:11},sectionTitle:{color:t.text,fontSize:17,fontWeight:'900',marginTop:3,marginBottom:8},row:{flexDirection:'row',justifyContent:'space-between',paddingVertical:10,borderTopWidth:1,borderTopColor:t.line},rowName:{color:t.text,fontSize:10,fontWeight:'800',flex:1},record:{color:t.success,fontSize:9,fontWeight:'900'},badges:{flexDirection:'row',flexWrap:'wrap',gap:7},badge:{width:'48%',flexGrow:1,backgroundColor:'#f5f8f6',borderRadius:12,padding:11},badgeLocked:{opacity:.45},badgeIcon:{color:t.success,fontSize:15,fontWeight:'900'},badgeTitle:{color:t.text,fontSize:9,fontWeight:'800',marginTop:4},financeCard:{minHeight:70,flexDirection:'row',justifyContent:'space-between',alignItems:'center',backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:16},financeTitle:{color:t.text,fontSize:13,fontWeight:'900',marginTop:4,textTransform:'capitalize'},arrow:{color:t.text,fontSize:20,fontWeight:'800'}
});
