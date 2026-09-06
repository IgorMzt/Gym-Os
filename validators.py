"""Validadores e conversores de entrada usados pelas APIs."""
import re
from datetime import date

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def cpf_apenas_digitos(cpf):
    return re.sub(r"\D", "", str(cpf or ""))


def cpf_valido(cpf):
    cpf = cpf_apenas_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digito1 = (soma * 10) % 11
    digito1 = 0 if digito1 == 10 else digito1
    if digito1 != int(cpf[9]):
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digito2 = (soma * 10) % 11
    digito2 = 0 if digito2 == 10 else digito2
    return digito2 == int(cpf[10])


def parse_bool(valor, padrao=False):
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    texto = str(valor).strip().lower()
    if texto in {"1", "true", "sim", "on", "yes"}:
        return True
    if texto in {"0", "false", "nao", "não", "off", "no"}:
        return False
    raise ValueError("Valor booleano invalido.")


def parse_int(valor, nome="valor", minimo=None, maximo=None, permitir_nulo=False):
    if valor in (None, ""):
        if permitir_nulo:
            return None
        raise ValueError(f"{nome} e obrigatorio.")
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} invalido.") from exc
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} deve ser no minimo {minimo}.")
    if maximo is not None and numero > maximo:
        raise ValueError(f"{nome} deve ser no maximo {maximo}.")
    return numero


def parse_float(valor, nome="valor", minimo=None, maximo=None):
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} invalido.") from exc
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} deve ser no minimo {minimo}.")
    if maximo is not None and numero > maximo:
        raise ValueError(f"{nome} deve ser no maximo {maximo}.")
    return numero


def email_valido(email):
    if not email:
        return True
    return bool(_EMAIL_RE.fullmatch(str(email).strip()))


def data_iso(valor, nome="Data", permitir_vazio=False):
    texto = str(valor or "").strip()
    if not texto and permitir_vazio:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise ValueError(f"{nome} invalida.") from exc
