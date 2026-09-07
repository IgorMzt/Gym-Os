import { limparTokens, obterAccessToken, obterRefreshToken, salvarTokens } from '@/storage/tokens';
import { setNetworkState } from '@/services/network-state';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');
const memoriaGet = new Map<string, unknown>();

export class ApiError extends Error {
  status: number;
  codigo?: string;

  constructor(message: string, status: number, codigo?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.codigo = codigo;
  }
}

function endpoint(path: string) {
  if (!API_URL) {
    throw new ApiError(
      'API não configurada. Defina EXPO_PUBLIC_API_URL em mobile/.env.local.',
      0,
      'API_NAO_CONFIGURADA',
    );
  }
  return `${API_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

async function lerResposta(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      data.erro || data.mensagem || 'Não foi possível concluir a solicitação.',
      response.status,
      data.codigo,
    );
  }
  return data;
}

export async function apiPublica<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    const response = await fetch(endpoint(path), {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    });
    setNetworkState('online');
    return lerResposta(response) as Promise<T>;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    setNetworkState('offline');
    throw new ApiError('Sem conexão com o Gym OS.', 0, 'SEM_CONEXAO');
  }
}

async function renovarAccessToken() {
  const refreshToken = await obterRefreshToken();
  if (!refreshToken) return null;

  try {
    const data = await apiPublica<{ access_token: string; refresh_token: string }>(
      '/api/v1/auth/refresh',
      { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) },
    );
    await salvarTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

export async function apiAutenticada<T>(path: string, init: RequestInit = {}, tentarRefresh = true): Promise<T> {
  let accessToken = await obterAccessToken();
  if (!accessToken && tentarRefresh) accessToken = await renovarAccessToken();
  if (!accessToken) throw new ApiError('Sessão expirada.', 401, 'SESSAO_EXPIRADA');

  const method = String(init.method || 'GET').toUpperCase();
  try {
    const response = await fetch(endpoint(path), {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers || {}),
      },
    });
    setNetworkState('online');

    if (response.status === 401 && tentarRefresh) {
      const novoAccessToken = await renovarAccessToken();
      if (!novoAccessToken) {
        await limparTokens();
        throw new ApiError('Sessão expirada.', 401, 'SESSAO_EXPIRADA');
      }
      return apiAutenticada<T>(path, init, false);
    }

    const data = await lerResposta(response) as T;
    if (method === 'GET') memoriaGet.set(path, data);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    setNetworkState('offline');
    if (method === 'GET' && memoriaGet.has(path)) return memoriaGet.get(path) as T;
    throw new ApiError('Você está sem conexão. Tente novamente quando a internet voltar.', 0, 'SEM_CONEXAO');
  }
}

export function getApiUrl() {
  return API_URL;
}
