"""Servicos SaaS da V6.14: planos, assinaturas, checkout, CMS e branding."""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Iterable

import database


FEATURE_LABELS = {
    "financeiro": "Financeiro",
    "pix": "PIX",
    "mobile": "App mobile",
    "catraca": "Catraca",
    "biometria": "Biometria",
    "relatorios": "Relatórios",
    "multiunidade": "Multiunidade",
    "branding": "Branding",
    "agents": "Agents",
}

SITE_DEFAULTS = {
    "hero_titulo": "Gestão de academias, reimaginada.",
    "hero_subtitulo": "Alunos, treinos, financeiro, acesso e automação em uma única plataforma.",
    "hero_cta": "Começar agora",
    "recursos_titulo": "Tudo o que sua academia precisa.",
    "planos_titulo": "Planos para cada fase.",
    "faq_titulo": "Perguntas frequentes",
    "contato_email": "contato@gymos.local",
    "contato_whatsapp": "",
    "hero_image_ref": "",
    "site_logo_ref": "",
}

STATUS_ASSINATURA = {"TRIAL", "ATIVA", "ATRASADA", "SUSPENSA", "CANCELADA"}


def _row_dict(row):
    return dict(row) if row is not None else None


def _slug(texto: str) -> str:
    valor = str(texto or "").strip().lower()
    mapa = str.maketrans("áàãâéêíóôõúüç", "aaaaeeiooouuc")
    valor = valor.translate(mapa)
    valor = re.sub(r"[^a-z0-9]+", "-", valor).strip("-")
    return valor[:80]


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _data(dias: int) -> str:
    return (datetime.now() + timedelta(days=max(0, int(dias or 0)))).strftime("%Y-%m-%d %H:%M:%S")


def listar_planos(*, publicos: bool = False, ativos: bool = False) -> list[dict]:
    conn = database.conectar()
    try:
        sql = "SELECT * FROM saas_planos WHERE 1=1"
        params = []
        if publicos:
            sql += " AND publico=1"
        if ativos:
            sql += " AND ativo=1"
        sql += " ORDER BY ordem,nome,id"
        planos = [dict(r) for r in conn.execute(sql, params).fetchall()]
        for plano in planos:
            plano["recursos"] = listar_recursos_plano(int(plano["id"]), conn=conn)
        return planos
    finally:
        conn.close()


def obter_plano(plano_id: int | None = None, slug: str | None = None):
    conn = database.conectar()
    try:
        if plano_id is not None:
            row = conn.execute("SELECT * FROM saas_planos WHERE id=?", (int(plano_id),)).fetchone()
        else:
            row = conn.execute("SELECT * FROM saas_planos WHERE LOWER(slug)=LOWER(?)", (str(slug or ""),)).fetchone()
        if not row:
            return None
        plano = dict(row)
        plano["recursos"] = listar_recursos_plano(int(plano["id"]), conn=conn)
        return plano
    finally:
        conn.close()


def listar_recursos() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM saas_recursos WHERE ativo=1 ORDER BY categoria,nome").fetchall()]
    finally:
        conn.close()


def listar_recursos_plano(plano_id: int, *, conn=None) -> list[dict]:
    proprio = conn is None
    conn = conn or database.conectar()
    try:
        rows = conn.execute(
            """
            SELECT r.codigo,r.nome,r.descricao,r.categoria,COALESCE(pr.habilitado,0) habilitado,pr.limite
            FROM saas_recursos r
            LEFT JOIN saas_plano_recursos pr ON pr.recurso_codigo=r.codigo AND pr.plano_id=?
            WHERE r.ativo=1 ORDER BY r.categoria,r.nome
            """,
            (int(plano_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if proprio:
            conn.close()


def salvar_plano(dados: dict, plano_id: int | None = None) -> int:
    nome = str(dados.get("nome") or "").strip()
    slug = _slug(dados.get("slug") or nome)
    if not nome or not slug:
        raise ValueError("Nome do plano é obrigatório.")

    def inteiro(nome_campo, padrao=0, nulo=False):
        valor = dados.get(nome_campo)
        if nulo and (valor is None or str(valor).strip() == ""):
            return None
        try:
            return int(valor if valor not in (None, "") else padrao)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{nome_campo} inválido.") from exc

    conn = database.conectar()
    try:
        payload = (
            nome,
            slug,
            str(dados.get("descricao") or "").strip(),
            inteiro("preco_mensal_centavos"),
            inteiro("preco_anual_centavos"),
            inteiro("trial_dias"),
            inteiro("max_alunos", nulo=True),
            inteiro("max_unidades", nulo=True),
            inteiro("max_professores", nulo=True),
            inteiro("max_agentes", nulo=True),
            1 if dados.get("destaque") else 0,
            1 if dados.get("publico") else 0,
            1 if dados.get("ativo", True) else 0,
            inteiro("ordem"),
        )
        if plano_id:
            conn.execute(
                """
                UPDATE saas_planos SET nome=?,slug=?,descricao=?,preco_mensal_centavos=?,preco_anual_centavos=?,trial_dias=?,
                    max_alunos=?,max_unidades=?,max_professores=?,max_agentes=?,destaque=?,publico=?,ativo=?,ordem=?,data_atualizacao=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                payload + (int(plano_id),),
            )
            pid = int(plano_id)
        else:
            cur = conn.execute(
                """
                INSERT INTO saas_planos(nome,slug,descricao,preco_mensal_centavos,preco_anual_centavos,trial_dias,
                    max_alunos,max_unidades,max_professores,max_agentes,destaque,publico,ativo,ordem)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                payload,
            )
            pid = int(cur.lastrowid)
        conn.commit()
        return pid
    finally:
        conn.close()


def salvar_recursos_plano(plano_id: int, recursos_habilitados: Iterable[str]) -> None:
    habilitados = {str(x) for x in recursos_habilitados}
    conn = database.conectar()
    try:
        for recurso in conn.execute("SELECT codigo FROM saas_recursos WHERE ativo=1").fetchall():
            codigo = str(recurso["codigo"])
            conn.execute(
                """
                INSERT INTO saas_plano_recursos(plano_id,recurso_codigo,habilitado)
                VALUES(?,?,?)
                ON CONFLICT(plano_id,recurso_codigo) DO UPDATE SET habilitado=excluded.habilitado
                """,
                (int(plano_id), codigo, 1 if codigo in habilitados else 0),
            )
        conn.commit()
    finally:
        conn.close()


def excluir_plano(plano_id: int) -> None:
    conn = database.conectar()
    try:
        em_uso = conn.execute("SELECT COUNT(*) qtd FROM saas_assinaturas WHERE plano_id=?", (int(plano_id),)).fetchone()
        if int(em_uso["qtd"] or 0) > 0:
            conn.execute("UPDATE saas_planos SET ativo=0,publico=0,data_atualizacao=CURRENT_TIMESTAMP WHERE id=?", (int(plano_id),))
        else:
            conn.execute("DELETE FROM saas_planos WHERE id=?", (int(plano_id),))
        conn.commit()
    finally:
        conn.close()


def assinatura_atual(academia_id: int):
    conn = database.conectar()
    try:
        row = conn.execute(
            """
            SELECT a.*,p.nome plano_nome,p.slug plano_slug,p.max_alunos,p.max_unidades,p.max_professores,p.max_agentes
            FROM saas_assinaturas a JOIN saas_planos p ON p.id=a.plano_id
            WHERE a.academia_id=? ORDER BY a.id DESC LIMIT 1
            """,
            (int(academia_id),),
        ).fetchone()
        return _row_dict(row)
    finally:
        conn.close()


def listar_assinaturas() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT s.*,a.nome academia_nome,a.slug academia_slug,p.nome plano_nome,p.slug plano_slug
            FROM saas_assinaturas s JOIN academias a ON a.id=s.academia_id JOIN saas_planos p ON p.id=s.plano_id
            ORDER BY s.id DESC
            """
        ).fetchall()]
    finally:
        conn.close()


def atualizar_status_assinatura(assinatura_id: int, status: str, motivo: str | None = None) -> None:
    status = str(status or "").upper()
    if status not in STATUS_ASSINATURA:
        raise ValueError("Status de assinatura inválido.")
    conn = database.conectar()
    try:
        cancelada = _agora() if status == "CANCELADA" else None
        conn.execute(
            "UPDATE saas_assinaturas SET status=?,motivo=?,cancelada_em=COALESCE(?,cancelada_em),data_atualizacao=CURRENT_TIMESTAMP WHERE id=?",
            (status, motivo, cancelada, int(assinatura_id)),
        )
        conn.commit()
    finally:
        conn.close()


def trocar_plano(academia_id: int, plano_id: int, ciclo: str = "MENSAL") -> int:
    plano = obter_plano(plano_id=plano_id)
    if not plano or not plano.get("ativo"):
        raise ValueError("Plano inválido ou inativo.")
    ciclo = "ANUAL" if str(ciclo).upper() == "ANUAL" else "MENSAL"
    valor = int(plano["preco_anual_centavos"] if ciclo == "ANUAL" else plano["preco_mensal_centavos"])
    conn = database.conectar()
    try:
        atual = conn.execute("SELECT id FROM saas_assinaturas WHERE academia_id=? ORDER BY id DESC LIMIT 1", (int(academia_id),)).fetchone()
        if atual:
            conn.execute("UPDATE saas_assinaturas SET status='CANCELADA',cancelada_em=CURRENT_TIMESTAMP,motivo='Troca de plano',data_atualizacao=CURRENT_TIMESTAMP WHERE id=?", (int(atual["id"]),))
        cur = conn.execute(
            """
            INSERT INTO saas_assinaturas(academia_id,plano_id,status,ciclo,valor_centavos,inicio_em,renovacao_em,gateway)
            VALUES(?,?, 'ATIVA', ?, ?, CURRENT_TIMESTAMP, ?, 'MANUAL')
            """,
            (int(academia_id), int(plano_id), ciclo, valor, _data(365 if ciclo == "ANUAL" else 30)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def feature_enabled(academia_id: int | None, codigo: str) -> bool:
    """Academia principal legada mantém acesso total; novas seguem a assinatura."""
    if not academia_id or int(academia_id) == 1:
        return True
    conn = database.conectar()
    try:
        assinatura = conn.execute(
            "SELECT id,status,plano_id FROM saas_assinaturas WHERE academia_id=? ORDER BY id DESC LIMIT 1",
            (int(academia_id),),
        ).fetchone()
        if not assinatura:
            return True  # tenant legado/manual
        if str(assinatura["status"]).upper() not in {"TRIAL", "ATIVA"}:
            return False
        row = conn.execute(
            "SELECT habilitado FROM saas_plano_recursos WHERE plano_id=? AND recurso_codigo=?",
            (int(assinatura["plano_id"]), str(codigo)),
        ).fetchone()
        return bool(row and int(row["habilitado"] or 0) == 1)
    finally:
        conn.close()


def limite(academia_id: int, campo: str):
    permitido = {"max_alunos", "max_unidades", "max_professores", "max_agentes"}
    if campo not in permitido:
        raise ValueError("Limite desconhecido.")
    if int(academia_id) == 1:
        return None
    assinatura = assinatura_atual(academia_id)
    return None if not assinatura else assinatura.get(campo)


def listar_academias_saas() -> list[dict]:
    conn = database.conectar()
    try:
        rows = conn.execute(
            """
            SELECT a.*,
                   (SELECT COUNT(*) FROM unidades u WHERE u.academia_id=a.id AND u.ativo=1) unidades_ativas,
                   (SELECT COUNT(*) FROM pessoas p WHERE p.academia_id=a.id) alunos,
                   (SELECT COUNT(*) FROM agentes_locais ag WHERE ag.academia_id=a.id AND ag.ativo=1) agentes
            FROM academias a ORDER BY a.id DESC
            """
        ).fetchall()
        saida = []
        for row in rows:
            item = dict(row)
            item["assinatura"] = assinatura_atual(int(item["id"]))
            saida.append(item)
        return saida
    finally:
        conn.close()


def set_academia_ativa(academia_id: int, ativa: bool) -> None:
    if int(academia_id) == 1 and not ativa:
        raise ValueError("A Academia Principal não pode ser desativada pelo SaaS.")
    conn = database.conectar()
    try:
        conn.execute("UPDATE academias SET ativo=?,data_atualizacao=CURRENT_TIMESTAMP WHERE id=?", (1 if ativa else 0, int(academia_id)))
        conn.commit()
    finally:
        conn.close()


def dashboard_saas() -> dict:
    conn = database.conectar()
    try:
        academias = int(conn.execute("SELECT COUNT(*) qtd FROM academias WHERE ativo=1").fetchone()["qtd"] or 0)
        assinaturas = int(conn.execute("SELECT COUNT(*) qtd FROM saas_assinaturas WHERE status IN ('ATIVA','TRIAL')").fetchone()["qtd"] or 0)
        trials = int(conn.execute("SELECT COUNT(*) qtd FROM saas_assinaturas WHERE status='TRIAL'").fetchone()["qtd"] or 0)
        mrr = int(conn.execute("SELECT COALESCE(SUM(CASE WHEN ciclo='ANUAL' THEN valor_centavos/12 ELSE valor_centavos END),0) total FROM saas_assinaturas WHERE status='ATIVA'").fetchone()["total"] or 0)
        alunos = int(conn.execute("SELECT COUNT(*) qtd FROM pessoas").fetchone()["qtd"] or 0)
        agentes = int(conn.execute("SELECT COUNT(*) qtd FROM agentes_locais WHERE ativo=1").fetchone()["qtd"] or 0)
        return {"academias": academias, "assinaturas": assinaturas, "trials": trials, "mrr_centavos": mrr, "alunos": alunos, "agentes": agentes}
    finally:
        conn.close()


def listar_cupons() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute("SELECT c.*,p.nome plano_nome FROM saas_cupons c LEFT JOIN saas_planos p ON p.id=c.plano_id ORDER BY c.id DESC").fetchall()]
    finally:
        conn.close()


def salvar_cupom(dados: dict, cupom_id: int | None = None) -> int:
    codigo = re.sub(r"[^A-Z0-9_-]", "", str(dados.get("codigo") or "").upper())[:40]
    if not codigo:
        raise ValueError("Código do cupom é obrigatório.")
    tipo = str(dados.get("tipo") or "PERCENTUAL").upper()
    if tipo not in {"PERCENTUAL", "VALOR"}:
        raise ValueError("Tipo de cupom inválido.")
    valor = int(dados.get("valor") or 0)
    if valor <= 0:
        raise ValueError("Valor do cupom deve ser maior que zero.")
    plano_id = int(dados["plano_id"]) if dados.get("plano_id") else None
    max_usos = int(dados["max_usos"]) if dados.get("max_usos") else None
    conn = database.conectar()
    try:
        payload = (codigo, tipo, valor, plano_id, max_usos, str(dados.get("valido_ate") or "").strip() or None, 1 if dados.get("ativo", True) else 0)
        if cupom_id:
            conn.execute("UPDATE saas_cupons SET codigo=?,tipo=?,valor=?,plano_id=?,max_usos=?,valido_ate=?,ativo=?,data_atualizacao=CURRENT_TIMESTAMP WHERE id=?", payload + (int(cupom_id),))
            cid = int(cupom_id)
        else:
            cid = int(conn.execute("INSERT INTO saas_cupons(codigo,tipo,valor,plano_id,max_usos,valido_ate,ativo) VALUES(?,?,?,?,?,?,?)", payload).lastrowid)
        conn.commit()
        return cid
    finally:
        conn.close()


def aplicar_cupom(codigo: str | None, plano_id: int, valor_centavos: int) -> tuple[int, dict | None]:
    if not codigo:
        return max(0, int(valor_centavos)), None
    conn = database.conectar()
    try:
        row = conn.execute("SELECT * FROM saas_cupons WHERE UPPER(codigo)=UPPER(?) AND ativo=1", (str(codigo).strip(),)).fetchone()
        if not row:
            raise ValueError("Cupom inválido.")
        cupom = dict(row)
        if cupom.get("plano_id") and int(cupom["plano_id"]) != int(plano_id):
            raise ValueError("Este cupom não é válido para o plano escolhido.")
        if cupom.get("max_usos") is not None and int(cupom.get("usos") or 0) >= int(cupom["max_usos"]):
            raise ValueError("Limite de uso deste cupom foi atingido.")
        if cupom.get("valido_ate") and str(cupom["valido_ate"])[:10] < datetime.now().strftime("%Y-%m-%d"):
            raise ValueError("Cupom expirado.")
        valor = int(valor_centavos)
        if cupom["tipo"] == "PERCENTUAL":
            valor -= round(valor * min(100, int(cupom["valor"])) / 100)
        else:
            valor -= int(cupom["valor"])
        return max(0, valor), cupom
    finally:
        conn.close()


def criar_checkout(*, plano_id: int, ciclo: str, academia_nome: str, academia_slug: str,
                    admin_nome: str, admin_login: str, admin_email: str, admin_senha_hash: str,
                    telefone: str = "", documento: str = "", cupom: str = "") -> dict:
    plano = obter_plano(plano_id=plano_id)
    if not plano or not plano.get("ativo") or not plano.get("publico"):
        raise ValueError("Plano indisponível.")
    slug = _slug(academia_slug or academia_nome)
    if len(slug) < 3:
        raise ValueError("Código da academia inválido.")
    conn = database.conectar()
    try:
        if conn.execute("SELECT 1 FROM academias WHERE LOWER(slug)=LOWER(?)", (slug,)).fetchone():
            raise ValueError("Este código de academia já está em uso.")
        if conn.execute("SELECT 1 FROM usuarios WHERE LOWER(login)=LOWER(?)", (str(admin_login).strip(),)).fetchone():
            raise ValueError("Este usuário de administrador já está em uso.")
        if conn.execute("SELECT 1 FROM saas_checkouts WHERE LOWER(admin_login)=LOWER(?) AND status IN ('PENDENTE','APROVADO')", (str(admin_login).strip(),)).fetchone():
            raise ValueError("Já existe uma contratação pendente com este usuário.")
        ciclo = "ANUAL" if str(ciclo).upper() == "ANUAL" else "MENSAL"
        base = int(plano["preco_anual_centavos"] if ciclo == "ANUAL" else plano["preco_mensal_centavos"])
        valor, _ = aplicar_cupom(cupom, int(plano_id), base)
        token = secrets.token_urlsafe(24)
        cur = conn.execute(
            """
            INSERT INTO saas_checkouts(token,plano_id,ciclo,status,academia_nome,academia_slug,admin_nome,admin_login,admin_email,
                admin_senha_hash,telefone,documento,cupom_codigo,valor_centavos)
            VALUES(?,?,?,'PENDENTE',?,?,?,?,?,?,?,?,?,?)
            """,
            (token, int(plano_id), ciclo, academia_nome.strip(), slug, admin_nome.strip(), admin_login.strip(), admin_email.strip().lower(), admin_senha_hash, telefone.strip(), documento.strip(), cupom.strip().upper() or None, valor),
        )
        conn.commit()
        return {"id": int(cur.lastrowid), "token": token, "valor_centavos": valor, "plano": plano, "ciclo": ciclo}
    finally:
        conn.close()


def obter_checkout(token: str):
    conn = database.conectar()
    try:
        row = conn.execute("SELECT c.*,p.nome plano_nome,p.slug plano_slug,p.trial_dias FROM saas_checkouts c JOIN saas_planos p ON p.id=c.plano_id WHERE c.token=?", (str(token),)).fetchone()
        return _row_dict(row)
    finally:
        conn.close()


def provisionar_checkout(token: str) -> dict:
    """Finaliza um checkout aprovado e cria tenant + unidade + admin + assinatura."""
    checkout = obter_checkout(token)
    if not checkout:
        raise ValueError("Checkout não encontrado.")
    if checkout["status"] == "CONCLUIDO" and checkout.get("academia_id"):
        academia = database.obter_academia(int(checkout["academia_id"]))
        return {"academia": academia, "checkout": checkout, "ja_processado": True}
    if checkout["status"] not in {"PENDENTE", "APROVADO"}:
        raise ValueError("Checkout não pode ser provisionado neste estado.")

    academia = database.criar_academia(checkout["academia_nome"], checkout["academia_slug"])
    academia_id = int(academia["id"])
    unidades = database.listar_unidades(academia_id)
    unidade = unidades[0]
    database.set_tenant_context(academia_id, int(unidade["id"]))
    conn = database.conectar()
    try:
        # A senha ja chega hashada do fluxo de checkout; evita manter texto puro.
        cur = conn.execute(
            """
            INSERT INTO usuarios(login,nome,senha_hash,papel,ativo,origem,academia_id,unidade_id)
            VALUES(?,?,?,'ADMIN',1,'SAAS',?,?)
            """,
            (checkout["admin_login"], checkout["admin_nome"], checkout["admin_senha_hash"], academia_id, int(unidade["id"])),
        )
        usuario_id = int(cur.lastrowid)
        trial_dias = int(checkout.get("trial_dias") or 0)
        status = "TRIAL" if trial_dias > 0 else "ATIVA"
        inicio = _agora()
        trial_fim = _data(trial_dias) if trial_dias > 0 else None
        renovacao = _data(trial_dias if trial_dias > 0 else (365 if checkout["ciclo"] == "ANUAL" else 30))
        assinatura_id = int(conn.execute(
            """
            INSERT INTO saas_assinaturas(academia_id,plano_id,status,ciclo,valor_centavos,inicio_em,trial_fim_em,renovacao_em,gateway)
            VALUES(?,?,?,?,?,?,?,?, 'GYM_OS_CHECKOUT')
            """,
            (academia_id, int(checkout["plano_id"]), status, checkout["ciclo"], int(checkout["valor_centavos"]), inicio, trial_fim, renovacao),
        ).lastrowid)
        if checkout.get("cupom_codigo"):
            conn.execute("UPDATE saas_cupons SET usos=usos+1,data_atualizacao=CURRENT_TIMESTAMP WHERE UPPER(codigo)=UPPER(?)", (checkout["cupom_codigo"],))
        conn.execute("UPDATE saas_checkouts SET status='CONCLUIDO',academia_id=?,data_atualizacao=CURRENT_TIMESTAMP WHERE id=?", (academia_id, int(checkout["id"])))
        conn.execute("INSERT INTO academia_branding(academia_id,nome_exibicao) VALUES(?,?) ON CONFLICT(academia_id) DO NOTHING", (academia_id, checkout["academia_nome"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        database.set_tenant_context(1, 1)
    return {"academia": database.obter_academia(academia_id), "unidade": unidade, "usuario_id": usuario_id, "assinatura_id": assinatura_id, "status": status}




def listar_checkouts() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute(
            """SELECT c.*,p.nome plano_nome,p.slug plano_slug FROM saas_checkouts c
            JOIN saas_planos p ON p.id=c.plano_id ORDER BY c.id DESC"""
        ).fetchall()]
    finally:
        conn.close()


def listar_agents_global() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute(
            """SELECT ag.*,a.nome academia_nome,u.nome unidade_nome
            FROM agentes_locais ag
            LEFT JOIN academias a ON a.id=ag.academia_id
            LEFT JOIN unidades u ON u.id=ag.unidade_id
            ORDER BY ag.ativo DESC,ag.id DESC"""
        ).fetchall()]
    finally:
        conn.close()


def set_agent_ativo(agent_id: int, ativo: bool) -> None:
    conn = database.conectar()
    try:
        conn.execute("UPDATE agentes_locais SET ativo=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (1 if ativo else 0, int(agent_id)))
        conn.commit()
    finally:
        conn.close()

def site_conteudo() -> dict:
    conn = database.conectar()
    try:
        dados = dict(SITE_DEFAULTS)
        for row in conn.execute("SELECT chave,valor FROM saas_site_conteudo WHERE publicado=1").fetchall():
            dados[str(row["chave"])] = row["valor"]
        return dados
    finally:
        conn.close()


def site_conteudo_completo() -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM saas_site_conteudo ORDER BY chave").fetchall()]
    finally:
        conn.close()


def salvar_site_conteudo(chave: str, valor: str, tipo: str = "texto", publicado: bool = True) -> None:
    chave = re.sub(r"[^a-z0-9_.-]", "", str(chave or "").lower())[:80]
    if not chave:
        raise ValueError("Chave de conteúdo inválida.")
    conn = database.conectar()
    try:
        conn.execute(
            """
            INSERT INTO saas_site_conteudo(chave,valor,tipo,publicado) VALUES(?,?,?,?)
            ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,tipo=excluded.tipo,publicado=excluded.publicado,data_atualizacao=CURRENT_TIMESTAMP
            """,
            (chave, str(valor or ""), str(tipo or "texto"), 1 if publicado else 0),
        )
        conn.commit()
    finally:
        conn.close()


def branding(academia_id: int) -> dict:
    conn = database.conectar()
    try:
        row = conn.execute("SELECT * FROM academia_branding WHERE academia_id=?", (int(academia_id),)).fetchone()
        if row:
            return dict(row)
        academia = conn.execute("SELECT nome FROM academias WHERE id=?", (int(academia_id),)).fetchone()
        return {
            "academia_id": int(academia_id),
            "nome_exibicao": academia["nome"] if academia else "Gym OS",
            "logo_ref": None,
            "favicon_ref": None,
            "banner_ref": None,
            "login_background_ref": None,
            "cor_primaria": "#73C7FF",
            "cor_secundaria": "#07182E",
            "cor_destaque": "#2D8CFF",
            "tema": "dark",
        }
    finally:
        conn.close()


def salvar_branding(academia_id: int, dados: dict) -> None:
    def cor(chave, padrao):
        valor = str(dados.get(chave) or padrao).strip()
        return valor if re.fullmatch(r"#[0-9A-Fa-f]{6}", valor) else padrao
    tema = str(dados.get("tema") or "dark").lower()
    if tema not in {"light", "dark", "system"}:
        tema = "dark"
    conn = database.conectar()
    try:
        conn.execute(
            """
            INSERT INTO academia_branding(academia_id,nome_exibicao,logo_ref,favicon_ref,banner_ref,login_background_ref,cor_primaria,cor_secundaria,cor_destaque,tema)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(academia_id) DO UPDATE SET nome_exibicao=excluded.nome_exibicao,logo_ref=excluded.logo_ref,
                favicon_ref=excluded.favicon_ref,banner_ref=excluded.banner_ref,login_background_ref=excluded.login_background_ref,
                cor_primaria=excluded.cor_primaria,cor_secundaria=excluded.cor_secundaria,cor_destaque=excluded.cor_destaque,
                tema=excluded.tema,data_atualizacao=CURRENT_TIMESTAMP
            """,
            (int(academia_id), str(dados.get("nome_exibicao") or "").strip() or None, dados.get("logo_ref") or None, dados.get("favicon_ref") or None,
             dados.get("banner_ref") or None, dados.get("login_background_ref") or None, cor("cor_primaria", "#73C7FF"),
             cor("cor_secundaria", "#07182E"), cor("cor_destaque", "#2D8CFF"), tema),
        )
        conn.commit()
    finally:
        conn.close()


def registrar_auditoria(acao: str, alvo: str = "", detalhes: dict | str | None = None, ip: str = "") -> None:
    if isinstance(detalhes, dict):
        detalhes = json.dumps(detalhes, ensure_ascii=False)
    conn = database.conectar()
    try:
        conn.execute("INSERT INTO saas_auditoria(acao,alvo,detalhes,ip) VALUES(?,?,?,?)", (str(acao), str(alvo or ""), str(detalhes or ""), str(ip or "")))
        conn.commit()
    finally:
        conn.close()


def listar_auditoria(limite: int = 80) -> list[dict]:
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM saas_auditoria ORDER BY id DESC LIMIT ?", (max(1, min(int(limite), 500)),)).fetchall()]
    finally:
        conn.close()
