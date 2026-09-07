import { apiAutenticada } from '@/services/api';

export type Avaliacao = {
  id: number;
  data_avaliacao: string;
  professor_nome?: string | null;
  peso_kg?: number | null;
  altura_cm?: number | null;
  imc?: number | null;
  gordura_percentual?: number | null;
  massa_gorda_kg?: number | null;
  massa_magra_kg?: number | null;
  braco_cm?: number | null;
  antebraco_cm?: number | null;
  torax_cm?: number | null;
  cintura_cm?: number | null;
  abdomen_cm?: number | null;
  quadril_cm?: number | null;
  coxa_cm?: number | null;
  panturrilha_cm?: number | null;
  observacoes?: string | null;
};

export type ComparacaoItem = { atual?: number | null; anterior?: number | null; delta?: number | null };
export type Comparacao = Record<string, ComparacaoItem>;
export type EvolucaoResponse = { sucesso: true; avaliacoes: Avaliacao[]; comparacao: Comparacao };

export const obterEvolucao = () => apiAutenticada<EvolucaoResponse>('/api/v1/aluno/evolucao');
export const obterAvaliacao = (id: number) => apiAutenticada<{ sucesso: true; avaliacao: Avaliacao }>(`/api/v1/aluno/evolucao/${id}`);
