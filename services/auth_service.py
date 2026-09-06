"""Autenticacao e papeis de acesso do Gym OS."""

from werkzeug.security import check_password_hash, generate_password_hash
import database

PAPEIS = {"ADMIN", "RECEPCAO", "PROFESSOR"}
ROTULOS_PAPEL = {"ADMIN": "Administrador", "RECEPCAO": "Recepção", "PROFESSOR": "Professor"}


def hash_senha(senha: str) -> str:
    return generate_password_hash(str(senha), method="scrypt")


def garantir_admin_bootstrap(usuario: str, senha: str):
    """Mantem uma conta administrativa de bootstrap controlada por variaveis de ambiente."""
    return database.garantir_usuario_bootstrap(
        login=(usuario or "admin").strip(),
        nome="Administrador",
        senha_hash=hash_senha(senha or "admin123"),
    )


def autenticar(login: str, senha: str):
    login = (login or "").strip()

    # Contas da equipe continuam tendo prioridade em caso de nomes legados.
    usuario = database.obter_usuario_por_login(login)
    if usuario and usuario.get("ativo") and check_password_hash(usuario.get("senha_hash") or "", senha or ""):
        database.atualizar_ultimo_login(usuario["id"])
        return database.obter_usuario(usuario["id"])

    acesso = database.obter_acesso_aluno_por_login(login)
    if not acesso:
        somente_digitos = "".join(c for c in login if c.isdigit())
        if len(somente_digitos) == 11:
            acesso = database.obter_acesso_aluno_por_cpf(somente_digitos)
    if not acesso or not acesso.get("ativo"):
        return None
    if not check_password_hash(acesso.get("senha_hash") or "", senha or ""):
        return None
    database.atualizar_ultimo_login_aluno(acesso["id"])
    return {
        "id": acesso["id"],
        "login": acesso["login"],
        "nome": acesso["nome"],
        "papel": "ALUNO",
        "pessoa_id": acesso["pessoa_id"],
        "ativo": acesso["ativo"],
    }


def papel_valido(papel: str) -> bool:
    return str(papel or "").upper() in PAPEIS


def destino_inicial(usuario: dict) -> str:
    if usuario.get("papel") == "PROFESSOR":
        return "pagina_minha_area"
    if usuario.get("papel") == "ALUNO":
        return "aluno_app_inicio"
    return "pagina_painel"
