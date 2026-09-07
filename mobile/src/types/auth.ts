export type AlunoResumo = {
  id: number;
  nome: string;
  login?: string | null;
  matricula?: string | null;
};

export type LoginResponse = {
  sucesso: true;
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  expires_in: number;
  refresh_expires_in: number;
  aluno: AlunoResumo;
};

export type AlunoDetalhes = {
  id: number;
  nome?: string | null;
  cpf?: string | null;
  data_nascimento?: string | null;
  sexo?: string | null;
  telefone?: string | null;
  email?: string | null;
  matricula?: string | null;
  plano?: string | null;
  plano_id?: number | null;
  data_inicio?: string | null;
  data_vencimento?: string | null;
  status_financeiro?: string | null;
  foto_url?: string | null;
};

export type MeResponse = {
  sucesso: true;
  aluno: AlunoDetalhes;
  conta: {
    login?: string | null;
    ultimo_login?: string | null;
  };
};
