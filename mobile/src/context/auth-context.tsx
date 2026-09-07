import { createContext, PropsWithChildren, useContext, useEffect, useState } from 'react';

import { obterAlunoAtual } from '@/services/auth';
import { limparTokens, obterRefreshToken } from '@/storage/tokens';
import type { AlunoDetalhes } from '@/types/auth';
import { registrarPushNoBackend } from '@/services/notificacoes';

type AuthContextValue = {
  carregando: boolean;
  autenticado: boolean;
  aluno: AlunoDetalhes | null;
  definirAluno: (aluno: AlunoDetalhes | null) => void;
  recarregarAluno: () => Promise<AlunoDetalhes | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [carregando, setCarregando] = useState(true);
  const [aluno, setAluno] = useState<AlunoDetalhes | null>(null);

  async function recarregarAluno() {
    try {
      const data = await obterAlunoAtual();
      setAluno(data.aluno);
      registrarPushNoBackend().catch(() => undefined);
      return data.aluno;
    } catch {
      await limparTokens();
      setAluno(null);
      return null;
    }
  }

  useEffect(() => {
    let ativo = true;
    (async () => {
      const refresh = await obterRefreshToken();
      if (refresh && ativo) await recarregarAluno();
      if (ativo) setCarregando(false);
    })();
    return () => { ativo = false; };
  }, []);

  return (
    <AuthContext.Provider
      value={{ carregando, autenticado: Boolean(aluno), aluno, definirAluno: setAluno, recarregarAluno }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth deve ser usado dentro de AuthProvider.');
  return context;
}
