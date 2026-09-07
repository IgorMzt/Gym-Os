import { apiAutenticada } from '@/services/api';

export type UltimaExecucao = { carga_realizada?: string | null; repeticoes_realizadas?: string | null; series_realizadas?: number | null; iniciado_em?: string | null };
export type ExercicioFicha = { id: number; exercicio_id: number; exercicio_nome: string; grupo_muscular?: string | null; series?: number | null; repeticoes?: string | null; carga?: string | null; descanso_segundos?: number | null; observacoes?: string | null };
export type TreinoFicha = { id: number; nome: string; ordem: number; observacoes?: string | null; exercicios: ExercicioFicha[] };
export type Ficha = { id: number; nome: string; objetivo?: string | null; observacoes?: string | null; professor_nome?: string | null; treinos: TreinoFicha[] };
export type ItemExecucao = { id: number; exercicio_id?: number | null; exercicio_nome: string; grupo_muscular?: string | null; series_planejadas?: number | null; repeticoes_planejadas?: string | null; carga_planejada?: string | null; descanso_planejado?: number | null; observacoes_planejadas?: string | null; concluido: number | boolean; series_realizadas?: number | null; repeticoes_realizadas?: string | null; carga_realizada?: string | null; observacoes_execucao?: string | null; ultima_execucao?: UltimaExecucao | null };
export type Sessao = { id: number; status: string; ficha_nome: string; treino_nome: string; total_exercicios: number; exercicios_concluidos: number; progresso_percentual: number; itens: ItemExecucao[] };
export type TreinosResponse = { sucesso: true; ficha: Ficha | null; sessao_em_andamento: Sessao | null; proximo_treino_id: number | null };

export const obterTreinos = () => apiAutenticada<TreinosResponse>('/api/v1/aluno/treinos');
export const iniciarTreino = (treinoId: number) => apiAutenticada<{ sucesso: true; id: number; reutilizada: boolean }>('/api/v1/aluno/execucoes', { method: 'POST', body: JSON.stringify({ treino_id: treinoId }) });
export const obterExecucao = (id: number) => apiAutenticada<{ sucesso: true; sessao: Sessao }>(`/api/v1/aluno/execucoes/${id}`);
export const salvarItem = (id: number, dados: object) => apiAutenticada<{ sucesso: true }>(`/api/v1/aluno/execucoes/itens/${id}`, { method: 'PUT', body: JSON.stringify(dados) });
export const concluirTreino = (id: number, observacoes = '') => apiAutenticada<{ sucesso: true }>(`/api/v1/aluno/execucoes/${id}/concluir`, { method: 'POST', body: JSON.stringify({ observacoes }) });
export const cancelarTreino = (id: number, observacoes = '') => apiAutenticada<{ sucesso: true }>(`/api/v1/aluno/execucoes/${id}/cancelar`, { method: 'POST', body: JSON.stringify({ observacoes }) });
