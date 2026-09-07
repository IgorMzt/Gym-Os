import { apiAutenticada } from '@/services/api';

export type PreferenciasMobile = {
  pessoa_id: number;
  meta_semanal: number;
  lembrete_treino_ativo: number | boolean;
  lembrete_treino_hora: string;
  atualizado_em?: string | null;
};

export type Conquista = { id: string; titulo: string; descricao: string; desbloqueada: boolean };
export type Recorde = { exercicio_id: number; exercicio_nome: string; carga_kg: number; data: string };
export type SessaoRecente = { id: number; treino_nome: string; ficha_nome: string; duracao_segundos?: number | null; iniciado_em?: string | null; finalizado_em?: string | null };
export type ProximoTreino = { id: number; nome: string; ordem?: number; exercicios?: Array<{ id: number }> };

export type ExperienciaResponse = {
  sucesso: true;
  semana: { realizados: number; meta: number; progresso_percentual: number; duracao_minutos: number; exercicios: number; volume_kg: number };
  streak_dias: number;
  total_treinos: number;
  recordes_30_dias: Recorde[];
  total_recordes: number;
  conquistas: Conquista[];
  proximo_treino: ProximoTreino | null;
  ficha: { id: number; nome: string; professor_nome?: string | null } | null;
  professor: { professor_nome?: string | null } | null;
  ultima_avaliacao: { peso_kg?: number | null; data_avaliacao?: string | null } | null;
  sessao_em_andamento: { id: number; treino_nome: string; exercicios_concluidos: number; total_exercicios: number } | null;
  recentes: SessaoRecente[];
  preferencias: PreferenciasMobile;
};

export type ResumoTreino = {
  id: number;
  treino_nome: string;
  ficha_nome: string;
  duracao_segundos: number;
  total_exercicios: number;
  exercicios_concluidos: number;
  volume_kg: number;
  percepcao_esforco?: number | null;
  feedback_mobile?: string | null;
  finalizado_em?: string | null;
};

export const obterExperiencia = () => apiAutenticada<ExperienciaResponse>('/api/v1/aluno/experiencia');
export const obterPreferencias = () => apiAutenticada<{ sucesso: true; preferencias: PreferenciasMobile }>('/api/v1/aluno/preferencias');
export const salvarPreferencias = (dados: { meta_semanal: number; lembrete_treino_ativo: boolean; lembrete_treino_hora: string }) =>
  apiAutenticada<{ sucesso: true; preferencias: PreferenciasMobile }>('/api/v1/aluno/preferencias', { method: 'PUT', body: JSON.stringify(dados) });
export const obterResumoTreino = (id: number) => apiAutenticada<{ sucesso: true; resumo: ResumoTreino }>(`/api/v1/aluno/execucoes/${id}/resumo`);
export const salvarFeedbackTreino = (id: number, percepcao_esforco: number, comentario = '') =>
  apiAutenticada<{ sucesso: true; resumo: ResumoTreino }>(`/api/v1/aluno/execucoes/${id}/feedback`, { method: 'POST', body: JSON.stringify({ percepcao_esforco, comentario }) });
