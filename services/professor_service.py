"""Regras de negócio do módulo de professores."""
import database


def contexto_por_usuario(usuario_id: int):
    professor = database.obter_professor_por_usuario(usuario_id)
    if not professor:
        return {"professor": None, "alunos": [], "total_alunos": 0}
    alunos = database.listar_alunos_professor(professor["id"])
    return {"professor": professor, "alunos": alunos, "total_alunos": len(alunos)}


def pode_acessar_aluno(usuario_id: int, pessoa_id: int) -> bool:
    professor = database.obter_professor_por_usuario(usuario_id)
    return bool(professor and professor.get("ativo") and database.professor_tem_aluno(professor["id"], pessoa_id))
