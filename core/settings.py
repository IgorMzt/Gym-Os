"""Configuracao por ambiente para desenvolvimento, testes e producao."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_TRUE = {"1", "true", "sim", "yes", "on"}
_FALSE = {"0", "false", "nao", "não", "no", "off"}


def _bool_env(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None or valor.strip() == "":
        return padrao
    normalizado = valor.strip().lower()
    if normalizado in _TRUE:
        return True
    if normalizado in _FALSE:
        return False
    raise ValueError(f"{nome} deve ser booleano (0/1, true/false).")


def _int_env(nome: str, padrao: int, minimo: int = 0, maximo: int | None = None) -> int:
    valor = os.getenv(nome)
    try:
        numero = int(valor) if valor not in (None, "") else int(padrao)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} deve ser inteiro.") from exc
    if numero < minimo or (maximo is not None and numero > maximo):
        limite = f" entre {minimo} e {maximo}" if maximo is not None else f" >= {minimo}"
        raise ValueError(f"{nome} deve estar{limite}.")
    return numero


@dataclass(frozen=True)
class Settings:
    environment: str
    role: str
    secret_key: str
    admin_user: str
    admin_password: str
    debug: bool
    host: str
    port: int
    secure_cookies: bool
    trust_proxy: bool
    proxy_hops: int
    auto_init_db: bool
    database_backend: str
    database_url: str
    sqlite_path: str
    database_pool_min: int
    database_pool_max: int
    database_pool_timeout: int
    app_timezone: str
    storage_backend: str
    storage_local_dir: str
    log_level: str
    log_dir: str
    enable_local_hardware: bool
    agent_api_token: str
    app_version: str = "6.11"

    @classmethod
    def from_env(cls) -> "Settings":
        environment = (os.getenv("APP_ENV") or "development").strip().lower()
        role = (os.getenv("APP_ROLE") or "local").strip().lower()
        production = environment == "production"
        local_default = role != "cloud"
        return cls(
            environment=environment,
            role=role,
            secret_key=os.getenv("SECRET_KEY", "troque-esta-secret-key-em-producao"),
            admin_user=os.getenv("ADMIN_USER", "admin"),
            admin_password=os.getenv("ADMIN_PASSWORD", "admin123"),
            debug=_bool_env("FLASK_DEBUG", False),
            host=os.getenv("HOST", "0.0.0.0"),
            port=_int_env("PORT", 5000, 1, 65535),
            secure_cookies=_bool_env("SESSION_COOKIE_SECURE", production),
            trust_proxy=_bool_env("TRUST_PROXY", production),
            proxy_hops=_int_env("PROXY_HOPS", 1, 1, 10),
            auto_init_db=_bool_env("AUTO_INIT_DB", not production),
            database_backend=(os.getenv("DATABASE_BACKEND") or "sqlite").strip().lower(),
            database_url=(os.getenv("DATABASE_URL") or "").strip(),
            sqlite_path=(os.getenv("SQLITE_PATH") or "").strip(),
            database_pool_min=_int_env("DATABASE_POOL_MIN", 1, 1, 50),
            database_pool_max=_int_env("DATABASE_POOL_MAX", 8, 1, 100),
            database_pool_timeout=_int_env("DATABASE_POOL_TIMEOUT", 10, 1, 120),
            app_timezone=(os.getenv("APP_TIMEZONE") or "America/Sao_Paulo").strip(),
            storage_backend=(os.getenv("STORAGE_BACKEND") or "local").strip().lower(),
            storage_local_dir=(os.getenv("STORAGE_LOCAL_DIR") or "").strip(),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
            log_dir=(os.getenv("LOG_DIR") or "").strip(),
            enable_local_hardware=_bool_env("ENABLE_LOCAL_HARDWARE", local_default),
            agent_api_token=(os.getenv("AGENT_API_TOKEN") or "").strip(),
        )

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @property
    def cloud(self) -> bool:
        return self.role == "cloud"

    def validate(self) -> None:
        if self.environment not in {"development", "testing", "production"}:
            raise ValueError("APP_ENV deve ser development, testing ou production.")
        if self.role not in {"local", "cloud"}:
            raise ValueError("APP_ROLE deve ser local ou cloud.")
        if self.database_backend not in {"sqlite", "postgresql"}:
            raise ValueError("DATABASE_BACKEND deve ser sqlite ou postgresql.")
        if self.storage_backend not in {"local", "object"}:
            raise ValueError("STORAGE_BACKEND deve ser local ou object.")
        if self.database_backend == "postgresql" and not self.database_url:
            raise ValueError("DATABASE_URL e obrigatoria quando DATABASE_BACKEND=postgresql.")
        if self.database_pool_min > self.database_pool_max:
            raise ValueError("DATABASE_POOL_MIN nao pode ser maior que DATABASE_POOL_MAX.")
        if not self.app_timezone or len(self.app_timezone) > 80:
            raise ValueError("APP_TIMEZONE invalida.")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL invalido.")

        if self.production:
            if len(self.secret_key) < 32 or self.secret_key == "troque-esta-secret-key-em-producao":
                raise ValueError("SECRET_KEY insegura para producao; use uma chave aleatoria com pelo menos 32 caracteres.")
            if len(self.admin_password) < 12 or self.admin_password == "admin123":
                raise ValueError("ADMIN_PASSWORD insegura para producao; use pelo menos 12 caracteres.")
            if self.debug:
                raise ValueError("FLASK_DEBUG deve permanecer desativado em producao.")
            if not self.secure_cookies:
                raise ValueError("SESSION_COOKIE_SECURE deve ser 1 em producao.")
            if self.cloud and self.enable_local_hardware:
                raise ValueError("ENABLE_LOCAL_HARDWARE deve ser 0 quando APP_ROLE=cloud.")
            if self.cloud and len(self.agent_api_token) < 32:
                raise ValueError("AGENT_API_TOKEN deve ter pelo menos 32 caracteres no backend cloud de producao.")

    def readiness_blockers(self) -> list[str]:
        """Pendencias arquiteturais que impedem considerar o papel cloud pronto."""
        bloqueios: list[str] = []
        if self.cloud:
            if self.database_backend != "postgresql" or not self.database_url:
                bloqueios.append("database_postgresql_pendente")
            if self.storage_backend != "object":
                bloqueios.append("storage_objeto_pendente")
            if self.enable_local_hardware:
                bloqueios.append("hardware_local_habilitado_no_cloud")
            if not self.agent_api_token:
                bloqueios.append("agent_api_token_pendente")
        return bloqueios

    def sqlite_file(self, base_dir: Path) -> Path:
        if self.sqlite_path:
            return Path(self.sqlite_path).expanduser().resolve()
        return base_dir / "perfis.db"
