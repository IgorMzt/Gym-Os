import { apiAutenticada } from '@/services/api';

export type SessaoHistorico = {
  id: number;
  status: string;
  ficha_nome: string;
  treino_nome: string;
  iniciado_em?: string | null;
  finalizado_em?: string | null;
  duracao_segundos?: number | null;
  observacoes?: string | null;
  total_exercicios: number;
  exercicios_concluidos: number;
};

export type ItemHistorico = {
  id: number;
  exercicio_nome: string;
  grupo_muscular?: string | null;
  series_realizadas?: number | null;
  repeticoes_realizadas?: string | null;
  carga_realizada?: string | null;
  observacoes_execucao?: string | null;
  concluido: number | boolean;
};

export type SessaoHistoricoDetalhe = SessaoHistorico & { itens: ItemHistorico[] };
export type EstatisticasHistorico = { em_andamento: number; concluidos: number; ultimos_30_dias: number; duracao_media_min: number };
export type UltimaCarga = { exercicio_id: number; exercicio_nome: string; carga_realizada?: string | null; repeticoes_realizadas?: string | null; series_realizadas?: number | null; iniciado_em?: string | null };
export type HistoricoResponse = { sucesso: true; sessoes: SessaoHistorico[]; estatisticas: EstatisticasHistorico; ultimas_cargas: UltimaCarga[] };

export const obterHistorico = () => apiAutenticada<HistoricoResponse>('/api/v1/aluno/historico');
export const obterTreinoHistorico = (id: number) => apiAutenticada<{ sucesso: true; sessao: SessaoHistoricoDetalhe }>(`/api/v1/aluno/historico/${id}`);
