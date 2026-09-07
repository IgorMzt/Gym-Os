import { apiAutenticada } from '@/services/api';

export type Cobranca = {
  id: number; status?: string | null; valor_centavos: number; vencimento?: string | null;
  data_pagamento?: string | null; pix_payload?: string | null; pix_qr_base64?: string | null;
  ultimo_evento?: string | null; data_atualizacao?: string | null;
};
export type FinanceiroResponse = {
  sucesso: boolean; status_financeiro: string; status_financeiro_efetivo: string;
  data_vencimento?: string | null; dias_para_vencimento?: number | null; tolerancia_dias: number;
  limite_tolerancia?: string | null; dias_tolerancia_restantes?: number | null; asaas_configurado: boolean;
  plano?: { id: number; nome: string; valor_centavos: number; duracao_dias: number } | null;
  cobranca_aberta?: Cobranca | null; cobrancas: Cobranca[];
};
export async function obterFinanceiro() { return apiAutenticada<FinanceiroResponse>('/api/v1/aluno/financeiro'); }
export async function gerarPix() { return apiAutenticada<{ sucesso: boolean; existente: boolean; cobranca: Cobranca }>('/api/v1/aluno/financeiro/pix', { method: 'POST' }); }
