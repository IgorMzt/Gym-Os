"""Storage privado do Gym OS (V6.12).

Suporta dois backends com a mesma referencia persistida no banco:

* ``local``  -> arquivos privados fora de ``static`` (desenvolvimento/piloto);
* ``object`` -> S3/MinIO compativel, sempre privado e acessado por URL assinada.

Referencias legadas ``uploads/...`` continuam sendo resolvidas em ``static`` para
nao quebrar cadastros anteriores a V6.12.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from itsdangerous import BadSignature, URLSafeSerializer


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PRIVATE_DIR = BASE_DIR / "storage" / "private"
LEGACY_UPLOAD_DIR = BASE_DIR / "static" / "uploads"
LOCAL_SCHEME = "private://"
OBJECT_SCHEME = "object://"


def backend() -> str:
    return (os.getenv("STORAGE_BACKEND") or "local").strip().lower()


def _ttl(padrao: int = 300) -> int:
    try:
        return max(30, min(int(os.getenv("STORAGE_SIGNED_URL_TTL") or padrao), 3600))
    except (TypeError, ValueError):
        return padrao


def _local_root() -> Path:
    configurado = (os.getenv("STORAGE_LOCAL_DIR") or "").strip()
    raiz = Path(configurado).expanduser().resolve() if configurado else DEFAULT_PRIVATE_DIR
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def _bucket() -> str:
    value = (os.getenv("STORAGE_BUCKET") or "").strip()
    if not value:
        raise RuntimeError("STORAGE_BUCKET e obrigatorio quando STORAGE_BACKEND=object.")
    return value


def _prefix() -> str:
    return (os.getenv("STORAGE_PREFIX") or "gym-os").strip("/ ") or "gym-os"


def _s3_client():
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise RuntimeError("boto3 nao instalado; instale as dependencias da V6.12.") from exc

    kwargs = {}
    endpoint = (os.getenv("STORAGE_ENDPOINT_URL") or "").strip()
    region = (os.getenv("STORAGE_REGION") or "").strip()
    access_key = (os.getenv("STORAGE_ACCESS_KEY_ID") or "").strip()
    secret_key = (os.getenv("STORAGE_SECRET_ACCESS_KEY") or "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if region:
        kwargs["region_name"] = region
    if access_key:
        kwargs["aws_access_key_id"] = access_key
    if secret_key:
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def _normalizar_categoria(categoria: str | None) -> str:
    bruto = (categoria or "geral").strip().lower().replace("\\", "/")
    partes = [p for p in bruto.split("/") if p and p not in {".", ".."}]
    seguro = "-".join("".join(c for c in p if c.isalnum() or c in {"-", "_"}) for p in partes)
    return seguro[:80] or "geral"


def _normalizar_extensao(extensao: str) -> str:
    ext = (extensao or ".bin").strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    ext = "." + "".join(c for c in ext[1:] if c.isalnum())[:12]
    return ext if len(ext) > 1 else ".bin"


def _key_segura(key: str) -> str:
    key = str(key or "").replace("\\", "/").lstrip("/")
    parts = PurePosixPath(key).parts
    if not key or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("Referencia de storage invalida.")
    return "/".join(parts)


def _registrar_metadata(*, referencia: str, object_key: str, conteudo: bytes,
                        content_type: str, categoria: str, owner_type=None,
                        owner_id=None, retention_until=None) -> None:
    """Registra metadados quando o schema V6.12 ja estiver disponivel.

    O arquivo nao deixa de ser salvo se o chamador estiver executando uma
    ferramenta legada antes da inicializacao do banco. Em runtime normal o
    ``create_app`` inicializa o schema antes de qualquer upload.
    """
    try:
        import database
        database.registrar_storage_object(
            referencia=referencia,
            object_key=object_key,
            backend=backend(),
            bucket=_bucket() if backend() == "object" else None,
            categoria=categoria,
            content_type=content_type,
            size_bytes=len(conteudo),
            sha256=hashlib.sha256(conteudo).hexdigest(),
            owner_type=owner_type,
            owner_id=owner_id,
            retention_until=retention_until,
        )
    except (AttributeError, RuntimeError, OSError):
        # Compatibilidade com comandos executados antes da migracao de schema.
        return
    except Exception as exc:
        # SQLite sem a tabela V6.12 tambem pode ocorrer em utilitarios antigos.
        if "storage_objects" in str(exc).lower() or "no such table" in str(exc).lower():
            return
        raise


def salvar_upload(conteudo: bytes, extensao: str = ".bin", *, categoria: str = "geral",
                  content_type: str | None = None, owner_type=None, owner_id=None,
                  retention_until=None) -> str:
    if not isinstance(conteudo, (bytes, bytearray)) or not conteudo:
        raise ValueError("Conteudo de upload vazio ou invalido.")
    conteudo = bytes(conteudo)
    ext = _normalizar_extensao(extensao)
    categoria = _normalizar_categoria(categoria)
    tipo = content_type or mimetypes.guess_type("arquivo" + ext)[0] or "application/octet-stream"
    key = _key_segura(f"{_prefix()}/{categoria}/{uuid.uuid4().hex}{ext}")

    atual = backend()
    if atual == "local":
        destino = (_local_root() / key).resolve()
        raiz = _local_root().resolve()
        if raiz not in destino.parents:
            raise ValueError("Destino de storage invalido.")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        referencia = LOCAL_SCHEME + key
    elif atual == "object":
        client = _s3_client()
        params = {
            "Bucket": _bucket(),
            "Key": key,
            "Body": conteudo,
            "ContentType": tipo,
        }
        sse = (os.getenv("STORAGE_SSE") or "").strip()
        if sse:
            params["ServerSideEncryption"] = sse
        client.put_object(**params)
        referencia = OBJECT_SCHEME + key
    else:
        raise RuntimeError(f"STORAGE_BACKEND nao suportado: {atual}")

    _registrar_metadata(
        referencia=referencia,
        object_key=key,
        conteudo=conteudo,
        content_type=tipo,
        categoria=categoria,
        owner_type=owner_type,
        owner_id=owner_id,
        retention_until=retention_until,
    )
    return referencia


def _marcar_excluido(referencia: str) -> None:
    try:
        import database
        database.marcar_storage_object_excluido(referencia)
    except Exception:
        pass


def remover_upload(caminho_relativo: str | None) -> None:
    if not caminho_relativo:
        return
    referencia = str(caminho_relativo).strip()
    try:
        if referencia.startswith(LOCAL_SCHEME):
            key = _key_segura(referencia[len(LOCAL_SCHEME):])
            destino = (_local_root() / key).resolve()
            raiz = _local_root().resolve()
            if raiz in destino.parents:
                destino.unlink(missing_ok=True)
        elif referencia.startswith(OBJECT_SCHEME):
            key = _key_segura(referencia[len(OBJECT_SCHEME):])
            _s3_client().delete_object(Bucket=_bucket(), Key=key)
        else:
            # Somente compatibilidade com uploads publicos pre-V6.12.
            nome = Path(referencia.replace("\\", "/")).name
            (LEGACY_UPLOAD_DIR / nome).unlink(missing_ok=True)
    finally:
        _marcar_excluido(referencia)


def vincular_upload(referencia: str | None, *, owner_type: str, owner_id: int,
                    categoria: str | None = None, retention_until=None) -> bool:
    if not referencia:
        return False
    try:
        import database
        return database.vincular_storage_object(
            str(referencia), owner_type=owner_type, owner_id=int(owner_id),
            categoria=categoria, retention_until=retention_until,
        )
    except Exception:
        return False


def _serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt="gym-os-private-storage-v612")


def _secret() -> str:
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            return str(current_app.secret_key)
    except Exception:
        pass
    return os.getenv("SECRET_KEY", "gym-os-development-storage-secret")


def url_temporaria(referencia: str | None, expires_seconds: int | None = None) -> str | None:
    if not referencia:
        return None
    ref = str(referencia).strip()
    ttl = max(30, min(int(expires_seconds or _ttl()), 3600))

    # Arquivos antigos continuam publicos somente para compatibilidade.
    if not ref.startswith((LOCAL_SCHEME, OBJECT_SCHEME)):
        caminho = ref.replace("\\", "/").lstrip("/")
        if caminho.startswith("static/"):
            caminho = caminho[len("static/"):]
        try:
            from flask import has_app_context, url_for
            if has_app_context():
                return url_for("static", filename=caminho)
        except Exception:
            pass
        return "/static/" + caminho

    if ref.startswith(OBJECT_SCHEME):
        key = _key_segura(ref[len(OBJECT_SCHEME):])
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": key},
            ExpiresIn=ttl,
        )

    payload = {"ref": ref, "exp": int(time.time()) + ttl}
    token = _serializer(_secret()).dumps(payload)
    try:
        from flask import has_app_context, url_for
        if has_app_context():
            return url_for("media.private_media", token=token)
    except Exception:
        pass
    return f"/media/private/{token}"


def resolver_token_local(token: str) -> tuple[Path, str, str]:
    try:
        payload = _serializer(_secret()).loads(token)
    except BadSignature as exc:
        raise ValueError("Assinatura de arquivo invalida.") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("URL de arquivo expirada.")
    ref = str(payload.get("ref") or "")
    if not ref.startswith(LOCAL_SCHEME):
        raise ValueError("Referencia privada invalida.")
    key = _key_segura(ref[len(LOCAL_SCHEME):])
    raiz = _local_root().resolve()
    caminho = (raiz / key).resolve()
    if raiz not in caminho.parents or not caminho.is_file():
        raise FileNotFoundError("Arquivo privado nao encontrado.")
    content_type = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    return caminho, content_type, ref




def _legacy_source_path(referencia: str | None) -> Path | None:
    if not referencia:
        return None
    ref = str(referencia).strip().replace("\\", "/").lstrip("/")
    if ref.startswith((LOCAL_SCHEME, OBJECT_SCHEME)):
        return None
    if ref.startswith("static/"):
        ref = ref[len("static/"):]
    if not ref.startswith("uploads/"):
        return None
    relativo = PurePosixPath(ref)
    if any(p in {"", ".", ".."} for p in relativo.parts):
        return None
    partes = list(relativo.parts)
    if not partes or partes[0] != "uploads":
        return None
    raiz = LEGACY_UPLOAD_DIR.resolve()
    destino = (raiz / Path(*partes[1:])).resolve()
    if destino != raiz and raiz not in destino.parents:
        return None
    return destino


def migrar_uploads_legados(*, dry_run: bool = True) -> dict:
    """Move referencias historicas de ``static/uploads`` para storage privado.

    O comando e intencionalmente explicito para que a academia possa revisar a
    migracao com ``--dry-run`` antes de remover arquivos que eram publicos.
    """
    import database

    specs = [
        ("pessoas", "id", "foto_path", "biometria", "pessoa"),
        ("professores", "id", "foto_path", "professores", "professor"),
        ("exercicios", "id", "imagem_path", "exercicios", "exercicio"),
        ("avaliacoes_fisicas", "id", "foto_frontal_path", "avaliacoes", "avaliacao_fisica"),
        ("avaliacoes_fisicas", "id", "foto_lateral_path", "avaliacoes", "avaliacao_fisica"),
        ("avaliacoes_fisicas", "id", "foto_costas_path", "avaliacoes", "avaliacao_fisica"),
    ]
    grupos: dict[str, list[dict]] = {}
    conn = database.conectar()
    try:
        for tabela, pk, coluna, categoria, owner_type in specs:
            rows = conn.execute(
                f"SELECT {pk} AS owner_id,{coluna} AS referencia FROM {tabela} "
                f"WHERE {coluna} IS NOT NULL AND TRIM({coluna})<>''"
            ).fetchall()
            for row in rows:
                ref = str(row["referencia"] or "").strip()
                source = _legacy_source_path(ref)
                if source is None:
                    continue
                grupos.setdefault(ref, []).append({
                    "table": tabela, "pk": pk, "column": coluna,
                    "category": categoria, "owner_type": owner_type,
                    "owner_id": int(row["owner_id"]), "source": source,
                })
    finally:
        conn.close()

    existentes = 0
    ausentes = 0
    migrados = 0
    atualizacoes = 0
    erros = []
    detalhes = []
    for ref, usos in grupos.items():
        source = usos[0]["source"]
        if not source.is_file():
            ausentes += 1
            detalhes.append({"referencia": ref, "status": "missing", "usos": len(usos)})
            continue
        existentes += 1
        detalhes.append({"referencia": ref, "status": "candidate", "usos": len(usos)})
        if dry_run:
            continue

        nova_ref = None
        try:
            categoria = usos[0]["category"]
            ext = source.suffix or ".bin"
            tipo = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            # Em caso raro de uma mesma foto referenciada por mais de um registro,
            # preservamos um unico objeto e deixamos o ownership sem titular unico.
            unique_owner = len({(u["owner_type"], u["owner_id"]) for u in usos}) == 1
            nova_ref = salvar_upload(
                source.read_bytes(), ext, categoria=categoria, content_type=tipo,
                owner_type=usos[0]["owner_type"] if unique_owner else None,
                owner_id=usos[0]["owner_id"] if unique_owner else None,
            )
            update_conn = database.conectar()
            try:
                for uso in usos:
                    update_conn.execute(
                        f"UPDATE {uso['table']} SET {uso['column']}=? WHERE {uso['pk']}=?",
                        (nova_ref, uso["owner_id"]),
                    )
                    if uso["table"] == "pessoas" and uso["column"] == "foto_path":
                        update_conn.execute(
                            "UPDATE biometric_profiles SET source_reference=?,updated_at=CURRENT_TIMESTAMP WHERE pessoa_id=?",
                            (nova_ref, uso["owner_id"]),
                        )
                    atualizacoes += 1
                update_conn.commit()
            except Exception:
                update_conn.rollback()
                raise
            finally:
                update_conn.close()
            source.unlink(missing_ok=True)
            migrados += 1
            detalhes[-1].update({"status": "migrated", "nova_referencia": nova_ref})
        except Exception as exc:
            if nova_ref:
                try:
                    remover_upload(nova_ref)
                except Exception:
                    pass
            erros.append({"referencia": ref, "erro": str(exc)})
            detalhes[-1].update({"status": "error", "erro": str(exc)})

    return {
        "ok": not erros,
        "dry_run": bool(dry_run),
        "referencias_legacy": len(grupos),
        "arquivos_existentes": existentes,
        "arquivos_ausentes": ausentes,
        "migrados": migrados,
        "campos_atualizados": atualizacoes,
        "erros": erros,
        "detalhes": detalhes,
    }

def _retention_expired(value, *, now: datetime | None = None) -> bool:
    if not value:
        return False
    text = str(value).strip()
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) <= current.astimezone(timezone.utc)


def purgar_expirados(*, dry_run: bool = False, now: datetime | None = None) -> dict:
    """Remove objetos ativos cuja retencao venceu.

    A politica de retencao e declarativa por objeto. Objetos sem
    ``retention_until`` nao sao removidos automaticamente.
    """
    try:
        import database
        objetos = database.listar_storage_objects(status="ACTIVE")
    except Exception as exc:
        return {"ok": False, "dry_run": bool(dry_run), "erro": str(exc), "candidatos": 0, "removidos": 0}

    candidatos = [o for o in objetos if _retention_expired(o.get("retention_until"), now=now)]
    removidos = 0
    erros = []
    if not dry_run:
        for objeto in candidatos:
            referencia = objeto.get("referencia")
            try:
                remover_upload(referencia)
                removidos += 1
            except Exception as exc:
                erros.append({"referencia": referencia, "erro": str(exc)})

    return {
        "ok": not erros,
        "dry_run": bool(dry_run),
        "candidatos": len(candidatos),
        "removidos": removidos,
        "erros": erros,
    }

def healthcheck() -> dict:
    atual = backend()
    try:
        if atual == "local":
            raiz = _local_root()
            teste = raiz / ".healthcheck"
            teste.write_bytes(b"ok")
            teste.unlink(missing_ok=True)
            return {"ok": True, "backend": atual, "private": True}
        if atual == "object":
            _s3_client().head_bucket(Bucket=_bucket())
            return {"ok": True, "backend": atual, "bucket": _bucket(), "private": True}
        return {"ok": False, "backend": atual, "detalhe": "backend nao suportado"}
    except Exception as exc:
        return {"ok": False, "backend": atual, "detalhe": str(exc)}
