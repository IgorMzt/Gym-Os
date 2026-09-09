"""Reconhecimento/autorizacao local com fallback offline para o Gym OS Agent."""

from __future__ import annotations

import base64
from datetime import date, datetime, timezone

import numpy as np

from agent import hardware


class LocalAccessEngine:
    def __init__(self, state, *, offline_cache_max_minutes: int = 120):
        self.state = state
        self.offline_cache_max_minutes = max(1, int(offline_cache_max_minutes))

    def cache_fresh(self) -> bool:
        age = self.state.cache_age_seconds()
        return age is not None and age <= self.offline_cache_max_minutes * 60

    def match_encoding(self, encoding) -> tuple[dict | None, float | None]:
        probe = np.asarray(encoding, dtype=float)
        cfg = self.state.get_access_config()
        try:
            threshold = float(cfg.get("limiar_reconhecimento") or 0.50)
        except (TypeError, ValueError):
            threshold = 0.50
        best_person = None
        best_distance = None
        for pessoa in self.state.list_people_with_encodings():
            for raw in pessoa.get("encodings") or []:
                candidate = np.asarray(raw, dtype=float)
                if candidate.shape != probe.shape:
                    continue
                distance = float(np.linalg.norm(candidate - probe))
                if best_distance is None or distance < best_distance:
                    best_person, best_distance = pessoa, distance
        if best_person is None or best_distance is None or best_distance > threshold:
            return None, best_distance
        return best_person, best_distance

    def offline_access_allowed(self, pessoa: dict) -> tuple[bool, str]:
        if not self.cache_fresh():
            return False, "Cache local expirado; conecte o agente ao Gym OS Cloud."
        if not pessoa.get("liberado"):
            return False, "Acesso bloqueado manualmente"
        status = str(pessoa.get("status_financeiro") or "EM_DIA").upper()
        vencimento = pessoa.get("data_vencimento")
        cfg = self.state.get_access_config()
        try:
            tolerancia = max(0, int(cfg.get("tolerancia_financeira_dias") or 5))
        except (TypeError, ValueError):
            tolerancia = 5
        if not vencimento:
            return False, "Plano sem vencimento"
        try:
            venc = date.fromisoformat(str(vencimento)[:10])
        except ValueError:
            return False, "Vencimento invalido no cache local"
        hoje = date.today()
        if status == "PENDENTE":
            limite = date.fromordinal(venc.toordinal() + tolerancia)
            if hoje <= limite:
                return True, "Pagamento pendente dentro da tolerancia (offline)"
            return False, "Pagamento pendente"
        if status == "VENCIDO" or hoje > date.fromordinal(venc.toordinal() + tolerancia):
            return False, "Plano vencido"
        return True, "Plano ativo (validacao offline)"

    def process_encoding(self, encoding, *, catraca_id: int | None = None, online_decision: dict | None = None) -> dict:
        pessoa, distance = self.match_encoding(encoding)
        if pessoa is None:
            result = {"status": "NEGADO", "allowed": False, "reason": "Pessoa nao reconhecida", "pessoa": None}
            self.state.queue_event("ACCESS_DECISION", {
                "status": "NEGADO", "motivo": result["reason"], "distancia": distance,
                "catraca_id": catraca_id,
            })
            return result

        if online_decision and online_decision.get("pessoa"):
            allowed = bool(online_decision.get("allowed"))
            reason = str(online_decision.get("reason") or "Validacao cloud")
            source = "CLOUD"
        else:
            allowed, reason = self.offline_access_allowed(pessoa)
            source = "CACHE_OFFLINE"

        status = "LIBERADO" if allowed else "BLOQUEADO"
        catraca = self.state.get_turnstile(catraca_id)
        acionamento = None
        if allowed:
            if not catraca:
                allowed = False
                status = "ERRO"
                reason = "Catraca nao configurada no cache local"
            else:
                try:
                    acionamento = hardware.open_turnstile(catraca)
                except Exception as exc:
                    status = "ERRO"
                    reason = f"Acesso autorizado, mas a catraca nao respondeu: {exc}"
        payload = {
            "pessoa_id": int(pessoa["pessoa_id"]), "nome": pessoa.get("nome"),
            "cpf": pessoa.get("cpf"), "matricula": pessoa.get("matricula"),
            "status": status, "motivo": reason, "distancia": distance,
            "decision_source": source, "catraca_id": catraca.get("id") if catraca else catraca_id,
            "catraca_nome": catraca.get("nome") if catraca else None,
        }
        event_uuid = self.state.queue_event("ACCESS_DECISION", payload)
        return {
            "status": status, "allowed": status == "LIBERADO", "reason": reason,
            "pessoa": pessoa, "distance": distance, "acionamento": acionamento,
            "decision_source": source, "event_uuid": event_uuid,
        }

    def encoding_from_image_data_url(self, data_url: str):
        """Extrai um encoding no PC local; a imagem nunca precisa ir para a nuvem."""
        try:
            import cv2  # type: ignore
            import face_recognition  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV/face_recognition nao estao instalados no agente.") from exc
        if not data_url or "," not in data_url:
            raise ValueError("Imagem invalida.")
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        bgr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Imagem invalida.")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.35, fy=0.35)
        locations = face_recognition.face_locations(small, model="hog")
        if len(locations) != 1:
            return None, len(locations)
        encodings = face_recognition.face_encodings(small, locations, num_jitters=1)
        return (encodings[0] if encodings else None), len(locations)
