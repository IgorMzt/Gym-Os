import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';

import { StudentShell } from '@/components/student-shell';
import { studentTheme as t } from '@/constants/student-theme';
import { HistoricoResponse, obterHistorico } from '@/services/historico';

function dataBr(valor?: string | null) {
  if (!valor) return '—';
  const d = new Date(valor.replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? valor.slice(0, 10) : d.toLocaleDateString('pt-BR');
}
function duracao(segundos?: number | null) {
  const min = Math.max(0, Math.round(Number(segundos || 0) / 60));
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)}h ${min % 60}min`;
}

export default function HistoricoScreen() {
  const [dados, setDados] = useState<HistoricoResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState('');

  const carregar = useCallback(async (refresh = false) => {
    refresh ? setAtualizando(true) : setCarregando(true);
    try { setErro(''); setDados(await obterHistorico()); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível carregar seu histórico.'); }
    finally { setCarregando(false); setAtualizando(false); }
  }, []);

  useFocusEffect(useCallback(() => { carregar(); }, [carregar]));

  return <StudentShell><ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={atualizando} onRefresh={() => carregar(true)} />}>
    <Text style={s.eyebrow}>HISTÓRICO</Text><Text style={s.title}>Seus treinos</Text><Text style={s.subtitle}>Acompanhe sua consistência e reveja cada sessão concluída.</Text>
    {carregando ? <ActivityIndicator style={s.loader} color={t.orange} /> : null}
    {erro ? <View style={s.error}><Text style={s.errorText}>{erro}</Text></View> : null}
    {dados ? <View style={s.stats}>
      <View style={s.stat}><Text style={s.statValue}>{dados.estatisticas.concluidos}</Text><Text style={s.statLabel}>CONCLUÍDOS</Text></View>
      <View style={s.stat}><Text style={s.statValue}>{dados.estatisticas.ultimos_30_dias}</Text><Text style={s.statLabel}>30 DIAS</Text></View>
      <View style={s.stat}><Text style={s.statValue}>{dados.estatisticas.duracao_media_min}</Text><Text style={s.statLabel}>MIN MÉDIA</Text></View>
    </View> : null}
    {!carregando && dados?.sessoes.length === 0 ? <View style={s.empty}><Text style={s.emptyTitle}>Seu histórico começa aqui</Text><Text style={s.emptyText}>Quando você concluir um treino pelo app, ele aparecerá nesta tela.</Text></View> : null}
    {dados?.sessoes.map((sessao) => <Pressable key={sessao.id} style={s.card} onPress={() => router.push(`/historico/${sessao.id}` as never)}>
      <View style={s.cardHead}><View style={{flex:1}}><Text style={s.date}>{dataBr(sessao.finalizado_em || sessao.iniciado_em)}</Text><Text style={s.cardTitle}>{sessao.treino_nome}</Text><Text style={s.ficha}>{sessao.ficha_nome}</Text></View><View style={s.done}><Text style={s.doneText}>✓</Text></View></View>
      <View style={s.meta}><Text style={s.metaText}>{sessao.exercicios_concluidos}/{sessao.total_exercicios} exercícios</Text><Text style={s.dot}>•</Text><Text style={s.metaText}>{duracao(sessao.duracao_segundos)}</Text><Text style={s.open}>Detalhes →</Text></View>
    </Pressable>)}
    {dados?.ultimas_cargas.length ? <><Text style={s.sectionTitle}>CARGAS RECENTES</Text><View style={s.loads}>{dados.ultimas_cargas.slice(0, 6).map((item, i) => <View key={`${item.exercicio_id}-${i}`} style={s.loadRow}><View style={{flex:1}}><Text style={s.loadName}>{item.exercicio_nome}</Text><Text style={s.loadMeta}>{item.series_realizadas || '—'} séries · {item.repeticoes_realizadas || '—'} reps</Text></View><Text style={s.loadValue}>{item.carga_realizada || '—'}</Text></View>)}</View></> : null}
  </ScrollView></StudentShell>;
}

const s=StyleSheet.create({content:{padding:14,paddingTop:22,paddingBottom:30},eyebrow:{color:t.orange,fontSize:9,fontWeight:'900',letterSpacing:1.2},title:{color:t.text,fontSize:29,fontWeight:'900',marginTop:4},subtitle:{color:t.muted,fontSize:11,lineHeight:17,marginTop:5,marginBottom:16},loader:{marginTop:40},error:{backgroundColor:'#fff0ed',borderRadius:12,padding:12,marginBottom:12},errorText:{color:t.danger,fontSize:11,fontWeight:'700'},stats:{flexDirection:'row',gap:8,marginBottom:12},stat:{flex:1,backgroundColor:t.dark,borderRadius:15,paddingVertical:14,paddingHorizontal:10},statValue:{color:'#fff',fontSize:22,fontWeight:'900'},statLabel:{color:'#9f9f9f',fontSize:7,fontWeight:'900',letterSpacing:.8,marginTop:3},card:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:16,marginBottom:10},cardHead:{flexDirection:'row',alignItems:'center'},date:{color:t.orange,fontSize:8,fontWeight:'900',letterSpacing:.8},cardTitle:{color:t.text,fontSize:18,fontWeight:'900',marginTop:4},ficha:{color:t.muted,fontSize:9,marginTop:3},done:{width:34,height:34,borderRadius:17,backgroundColor:'#e9f6ef',alignItems:'center',justifyContent:'center'},doneText:{color:t.success,fontWeight:'900',fontSize:17},meta:{borderTopWidth:1,borderTopColor:t.line,marginTop:13,paddingTop:11,flexDirection:'row',alignItems:'center',gap:6},metaText:{color:t.muted,fontSize:9,fontWeight:'700'},dot:{color:'#bbb'},open:{marginLeft:'auto',color:t.text,fontSize:9,fontWeight:'900'},empty:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:25,alignItems:'center'},emptyTitle:{color:t.text,fontSize:14,fontWeight:'900'},emptyText:{color:t.muted,fontSize:10,lineHeight:16,textAlign:'center',marginTop:6},sectionTitle:{color:t.muted,fontSize:8,fontWeight:'900',letterSpacing:1.1,marginTop:9,marginBottom:8},loads:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,paddingHorizontal:14},loadRow:{flexDirection:'row',alignItems:'center',paddingVertical:12,borderBottomWidth:1,borderBottomColor:t.line},loadName:{color:t.text,fontSize:11,fontWeight:'800'},loadMeta:{color:t.muted,fontSize:8,marginTop:3},loadValue:{color:t.orange,fontSize:12,fontWeight:'900'}});
