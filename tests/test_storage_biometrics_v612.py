import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import database
from agent.state import AgentState
from services import agent_service, storage_service


class StorageBiometriaV612Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        self.old_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "gym-v612.db"
        database.criar_tabelas()
        self.env = patch.dict(os.environ, {
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": str(Path(self.tmp.name) / "private"),
            "STORAGE_PREFIX": "gym-os-test",
            "SECRET_KEY": "v612-test-secret-key-with-enough-entropy",
            "STORAGE_SIGNED_URL_TTL": "120",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        database.DB_PATH = self.old_path
        database.DATABASE_BACKEND = self.old_backend
        self.tmp.cleanup()

    def _pessoa(self):
        plano = database.listar_planos(ativos_apenas=True)[0]
        dados = {
            "nome": "Aluno V612", "cpf": "12345678909", "data_nascimento": "2000-01-01",
            "sexo": None, "telefone": None, "email": None, "matricula": "V612001",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": "2026-09-01",
            "data_vencimento": "2027-09-01", "status_financeiro": "EM_DIA",
            "observacoes": None, "liberado": True,
        }
        return database.adicionar_pessoa(dados, [np.zeros(128), np.ones(128)], None)

    def test_schema_22_cria_storage_e_biometria(self):
        self.assertEqual(database.SCHEMA_VERSION, 22)
        conn = database.conectar()
        try:
            tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("storage_objects", tabelas)
            self.assertIn("biometric_profiles", tabelas)
            versao = conn.execute("SELECT valor FROM schema_meta WHERE chave='schema_version'").fetchone()[0]
            self.assertEqual(versao, "22")
            mig = conn.execute(
                "SELECT 1 FROM database_migrations WHERE migration_key='schema-22-storage-biometria'"
            ).fetchone()
            self.assertIsNotNone(mig)
        finally:
            conn.close()

    def test_storage_local_privado_tem_metadata_url_temporaria_e_exclusao(self):
        ref = storage_service.salvar_upload(
            b"conteudo-privado", ".jpg", categoria="biometria", content_type="image/jpeg"
        )
        self.assertTrue(ref.startswith("private://"))
        meta = database.obter_storage_object(ref)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["status"], "ACTIVE")
        self.assertEqual(meta["categoria"], "biometria")
        self.assertEqual(meta["size_bytes"], len(b"conteudo-privado"))

        url = storage_service.url_temporaria(ref, 60)
        token = url.rsplit("/", 1)[-1]
        arquivo, mime, resolved = storage_service.resolver_token_local(token)
        self.assertEqual(resolved, ref)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(arquivo.read_bytes(), b"conteudo-privado")

        storage_service.remover_upload(ref)
        self.assertFalse(arquivo.exists())
        self.assertEqual(database.obter_storage_object(ref)["status"], "DELETED")

    def test_storage_object_s3_compativel_usa_bucket_privado_e_presigned_url(self):
        class FakeS3:
            def __init__(self):
                self.puts = []
                self.deletes = []
            def put_object(self, **kwargs):
                self.puts.append(kwargs)
                return {}
            def generate_presigned_url(self, operation, Params, ExpiresIn):
                return f"https://storage.test/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"
            def delete_object(self, **kwargs):
                self.deletes.append(kwargs)
                return {}
            def head_bucket(self, **kwargs):
                return {}

        fake = FakeS3()
        with patch.dict(os.environ, {
            "STORAGE_BACKEND": "object",
            "STORAGE_BUCKET": "gym-os-private-test",
            "STORAGE_PREFIX": "tenant-test",
            "STORAGE_SSE": "AES256",
        }, clear=False), patch.object(storage_service, "_s3_client", return_value=fake):
            ref = storage_service.salvar_upload(b"objeto", ".jpg", categoria="biometria", content_type="image/jpeg")
            self.assertTrue(ref.startswith("object://tenant-test/biometria/"))
            self.assertEqual(fake.puts[0]["Bucket"], "gym-os-private-test")
            self.assertEqual(fake.puts[0]["ServerSideEncryption"], "AES256")
            meta = database.obter_storage_object(ref)
            self.assertEqual(meta["backend"], "object")
            self.assertEqual(meta["bucket"], "gym-os-private-test")
            url = storage_service.url_temporaria(ref, 90)
            self.assertIn("gym-os-private-test", url)
            self.assertIn("ttl=90", url)
            self.assertTrue(storage_service.healthcheck()["ok"])
            storage_service.remover_upload(ref)
            self.assertEqual(fake.deletes[0]["Bucket"], "gym-os-private-test")
            self.assertEqual(database.obter_storage_object(ref)["status"], "DELETED")

    def test_migracao_de_upload_legacy_para_privado(self):
        pessoa_id = self._pessoa()
        legacy_dir = Path(self.tmp.name) / "legacy-uploads"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = legacy_dir / "aluno.jpg"
        legacy_file.write_bytes(b"foto-legada")
        database.atualizar_amostras_e_foto(pessoa_id, None, "uploads/aluno.jpg")

        with patch.object(storage_service, "LEGACY_UPLOAD_DIR", legacy_dir):
            dry = storage_service.migrar_uploads_legados(dry_run=True)
            self.assertTrue(dry["ok"])
            self.assertEqual(dry["arquivos_existentes"], 1)
            self.assertTrue(legacy_file.exists())
            self.assertEqual(database.obter_pessoa(pessoa_id)["foto_path"], "uploads/aluno.jpg")

            result = storage_service.migrar_uploads_legados(dry_run=False)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["migrados"], 1)
            self.assertFalse(legacy_file.exists())

        pessoa = database.obter_pessoa(pessoa_id)
        self.assertTrue(pessoa["foto_path"].startswith("private://"))
        perfil = database.obter_perfil_biometrico(pessoa_id)
        self.assertEqual(perfil["source_reference"], pessoa["foto_path"])
        self.assertEqual(database.obter_storage_object(pessoa["foto_path"])["owner_id"], pessoa_id)

    def test_retencao_pode_ser_simulada_e_purgada(self):
        ref = storage_service.salvar_upload(
            b"expirado", ".bin", categoria="documentos",
            retention_until="2000-01-01T00:00:00+00:00",
        )
        dry = storage_service.purgar_expirados(dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertEqual(dry["candidatos"], 1)
        self.assertEqual(dry["removidos"], 0)
        self.assertEqual(database.obter_storage_object(ref)["status"], "ACTIVE")

        purge = storage_service.purgar_expirados()
        self.assertTrue(purge["ok"])
        self.assertEqual(purge["removidos"], 1)
        self.assertEqual(database.obter_storage_object(ref)["status"], "DELETED")

    def test_biometria_tem_versionamento(self):
        pessoa_id = self._pessoa()
        perfil = database.obter_perfil_biometrico(pessoa_id)
        self.assertEqual(perfil["version"], 1)
        self.assertEqual(perfil["sample_count"], 2)
        database.atualizar_amostras_e_foto(pessoa_id, [np.full(128, 0.25)], None)
        atualizado = database.obter_perfil_biometrico(pessoa_id)
        self.assertEqual(atualizado["version"], 2)
        self.assertEqual(atualizado["sample_count"], 1)

    def test_snapshot_agent_carrega_versao_biometrica_sem_foto(self):
        pessoa_id = self._pessoa()
        snapshot = agent_service.access_snapshot()
        pessoa = next(p for p in snapshot["pessoas"] if p["id"] == pessoa_id)
        self.assertEqual(pessoa["biometric_version"], 1)
        self.assertEqual(len(pessoa["encodings"]), 2)
        self.assertIn("biometric_sync_version", snapshot)
        self.assertNotIn("foto_path", pessoa)

        state = AgentState(Path(self.tmp.name) / "agent.db")
        state.save_snapshot(snapshot)
        cached = state.get_person(pessoa_id)
        self.assertEqual(cached["biometric_version"], 1)
        self.assertEqual(len(state.list_people_with_encodings()[0]["encodings"]), 2)

    def test_vinculo_do_storage_com_titular(self):
        pessoa_id = self._pessoa()
        ref = storage_service.salvar_upload(b"foto", ".jpg", categoria="biometria")
        self.assertTrue(storage_service.vincular_upload(
            ref, owner_type="pessoa", owner_id=pessoa_id, categoria="biometria"
        ))
        meta = database.obter_storage_object(ref)
        self.assertEqual(meta["owner_type"], "pessoa")
        self.assertEqual(meta["owner_id"], pessoa_id)


if __name__ == "__main__":
    unittest.main()
