import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';

import { StudentShell } from '@/components/student-shell';
import { studentTheme as t } from '@/constants/student-theme';
import { iniciarTreino, obterTreinos, TreinosResponse } from '@/services/treinos';

export default function TreinoScreen() {
  const [dados, setDados] = useState<TreinosResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [iniciando, setIniciando] = useState<number | null>(null);
  const [erro, setErro] = useState('');

  const carregar = useCallback(async () => {
    try { setErro(''); setDados(await obterTreinos()); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível carregar seus treinos.'); }
    finally { setCarregando(false); }
  }, []);

  useFocusEffect(useCallback(() => { setCarregando(true); carregar(); }, [carregar]));

  async function iniciar(id: number) {
    try {
      setIniciando(id); setErro('');
      const r = await iniciarTreino(id);
      router.push(`/execucao/${r.id}` as never);
    } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível iniciar o treino.'); }
    finally { setIniciando(null); }
  }

  return <StudentShell><ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={false} onRefresh={carregar} />}>
    <Text style={s.eyebrow}>MINHA ROTINA</Text><Text style={s.title}>Meu treino</Text>
    <Text style={s.subtitle}>{dados?.ficha?.nome || 'Sua ficha ativa'}</Text>
    {carregando ? <ActivityIndicator style={s.loader} color={t.orange} /> : null}
    {erro ? <View style={s.error}><Text style={s.errorText}>{erro}</Text></View> : null}
    {dados?.sessao_em_andamento ? <Pressable style={s.resume} onPress={() => router.push(`/execucao/${dados.sessao_em_andamento!.id}` as never)}><View><Text style={s.resumeSmall}>EM ANDAMENTO</Text><Text style={s.resumeTitle}>{dados.sessao_em_andamento.treino_nome}</Text><Text style={s.resumeText}>{dados.sessao_em_andamento.exercicios_concluidos}/{dados.sessao_em_andamento.total_exercicios} concluídos</Text></View><Text style={s.resumeArrow}>Continuar →</Text></Pressable> : null}
    {!carregando && !dados?.ficha ? <View style={s.empty}><Text style={s.emptyTitle}>Nenhum treino disponível</Text><Text style={s.emptyText}>Quando seu professor criar uma ficha ativa, ela aparecerá aqui.</Text></View> : null}
    {dados?.ficha?.treinos.map((treino, idx) => {
      const proximo = treino.id === dados.proximo_treino_id;
      return <View style={[s.card, proximo && s.nextCard]} key={treino.id}>
        <View style={s.cardHead}><View style={{flex:1}}><Text style={s.cardSmall}>TREINO {idx + 1}{proximo ? ' · PRÓXIMO' : ''}</Text><Text style={s.cardTitle}>{treino.nome}</Text></View><Text style={s.count}>{treino.exercicios.length} exercícios</Text></View>
        {treino.observacoes ? <Text style={s.note}>{treino.observacoes}</Text> : null}
        {treino.exercicios.map((ex, i) => <View style={s.exercise} key={ex.id}><View style={s.number}><Text style={s.numberText}>{i+1}</Text></View><View style={{flex:1}}><Text style={s.exerciseName}>{ex.exercicio_nome}</Text><Text style={s.exerciseMeta}>{ex.series ?? '—'} séries · {ex.repeticoes || '—'} reps{ex.carga ? ` · ${ex.carga}` : ''}</Text></View></View>)}
        {!dados.sessao_em_andamento ? <Pressable disabled={iniciando !== null} style={s.button} onPress={() => iniciar(treino.id)}><Text style={s.buttonText}>{iniciando === treino.id ? 'Iniciando...' : `Iniciar ${treino.nome}`}</Text></Pressable> : null}
      </View>;
    })}
  </ScrollView></StudentShell>;
}

const s=StyleSheet.create({content:{padding:14,paddingTop:22,paddingBottom:30},eyebrow:{color:t.orange,fontSize:9,fontWeight:'900',letterSpacing:1.2},title:{color:t.text,fontSize:29,fontWeight:'900',marginTop:4},subtitle:{color:t.muted,fontSize:11,marginTop:5,marginBottom:16},loader:{marginTop:40},error:{backgroundColor:'#fff0ed',borderRadius:12,padding:12,marginBottom:12},errorText:{color:t.danger,fontSize:11,fontWeight:'700'},resume:{backgroundColor:t.dark,borderRadius:17,padding:17,marginBottom:12,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},resumeSmall:{color:t.orange,fontSize:8,fontWeight:'900',letterSpacing:1},resumeTitle:{color:'#fff',fontSize:18,fontWeight:'900',marginTop:4},resumeText:{color:'#aaa',fontSize:10,marginTop:4},resumeArrow:{color:'#fff',fontSize:11,fontWeight:'800'},card:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:16,marginBottom:12},nextCard:{borderColor:'#f4b399',borderWidth:1.5},cardHead:{flexDirection:'row',alignItems:'flex-start',gap:8},cardSmall:{color:t.orange,fontSize:8,fontWeight:'900',letterSpacing:1},cardTitle:{color:t.text,fontSize:19,fontWeight:'900',marginTop:3},count:{color:t.muted,fontSize:9,fontWeight:'700'},note:{color:t.muted,fontSize:10,lineHeight:15,marginTop:9},exercise:{flexDirection:'row',alignItems:'center',gap:10,borderTopWidth:1,borderTopColor:t.line,paddingVertical:11},number:{width:27,height:27,borderRadius:8,backgroundColor:'#f3eee9',alignItems:'center',justifyContent:'center'},numberText:{color:t.orange,fontSize:10,fontWeight:'900'},exerciseName:{color:t.text,fontSize:12,fontWeight:'800'},exerciseMeta:{color:t.muted,fontSize:9,marginTop:3},button:{backgroundColor:t.orange,minHeight:47,borderRadius:13,alignItems:'center',justifyContent:'center',marginTop:8},buttonText:{color:'#fff',fontSize:12,fontWeight:'900'},empty:{backgroundColor:t.card,borderWidth:1,borderColor:t.line,borderRadius:18,padding:25,alignItems:'center'},emptyTitle:{color:t.text,fontSize:14,fontWeight:'900'},emptyText:{color:t.muted,fontSize:10,textAlign:'center',marginTop:6}});
