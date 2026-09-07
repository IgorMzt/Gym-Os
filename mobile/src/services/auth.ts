import { apiAutenticada, apiPublica } from '@/services/api';
import { limparTokens, obterRefreshToken, salvarTokens } from '@/storage/tokens';
import type { LoginResponse, MeResponse } from '@/types/auth';
import { removerPushDoBackend } from '@/services/notificacoes';

export async function loginAluno(login: string, senha: string) {
  const data = await apiPublica<LoginResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login, senha }),
  });
  await salvarTokens(data.access_token, data.refresh_token);
  return data;
}

export async function obterAlunoAtual() {
  return apiAutenticada<MeResponse>('/api/v1/aluno/me');
}

export async function logoutAluno() {
  const refreshToken = await obterRefreshToken();
  try {
    await removerPushDoBackend().catch(() => undefined);
    if (refreshToken) {
      await apiAutenticada('/api/v1/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } finally {
    await limparTokens();
  }
}
