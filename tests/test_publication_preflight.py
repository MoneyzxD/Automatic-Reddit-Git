from unittest.mock import Mock

import pytest

import publish
from scheduler import queue, uploader
from utils.pipeline_state import StateError


def test_estado_atual_invalido_bloqueia_kit_e_upload(monkeypatch):
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "production")
    monkeypatch.setattr(publish, "require_ready", Mock())
    monkeypatch.setattr(queue, "get_uncertain", lambda language: [])
    monkeypatch.setattr(queue, "get_pending", lambda language: [{"id": "aprovado"}])
    monkeypatch.setattr(queue, "count_scheduled_by_local_date", lambda *args: {})
    monkeypatch.setattr(queue, "get_item", lambda *args: {
        "id": "aprovado", "platforms": {"youtube": {"status": "pending"}},
    })
    confirmar = Mock(side_effect=StateError("Estado atual inconsistente"))
    monkeypatch.setattr(publish, "checkpoint_from_environment", confirmar)
    kit = Mock()
    transporte = Mock()
    transporte.return_value.upload_item.return_value = {"youtube": {"status": "uploaded"}}
    monkeypatch.setattr(publish, "_enviar_kit_tiktok", kit)
    monkeypatch.setattr(uploader, "Uploader", transporte)

    with pytest.raises(StateError, match="Estado atual inconsistente"):
        publish.publicar_idioma("en", {"channels": {"en": {"enabled": True}}}, 3)

    confirmar.assert_called_once_with(publish.BASE_DIR, reason="publication_preflight")
    kit.assert_not_called()
    transporte.assert_not_called()
