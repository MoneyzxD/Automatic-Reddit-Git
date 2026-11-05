"""O reparo de recibo exige evidência exata e nunca reenvia mídia."""
import copy
from types import SimpleNamespace

import pytest
from scripts import reconcile_es_20261105 as repair


@pytest.mark.parametrize("mismatch", [None, "channel", "description", "date", "duration", "id"])
def test_reparo_aceita_so_video_confirmado(monkeypatch, tmp_path, mismatch):
    row = {"id": repair.ITEM, "metadata": {"youtube": {"title": "Título", "description": "Descrição"}},
           "platforms": {"youtube": {"status": "uploading", "video_id": None}}}
    before = copy.deepcopy(row)
    video = {"id": repair.VIDEO, "snippet": {"channelId": repair.CHANNEL, "title": "Título",
        "description": "Descrição", "publishedAt": "2026-11-05T15:58:02Z"},
        "status": {"privacyStatus": "public", "uploadStatus": "processed"},
        "contentDetails": {"duration": "PT2M29S"}}
    if mismatch == "channel": video["snippet"]["channelId"] = "outro"
    if mismatch == "description": video["snippet"]["description"] = "outra"
    if mismatch == "date": video["snippet"]["publishedAt"] = "2026-11-04T15:58:02Z"
    if mismatch == "duration": video["contentDetails"]["duration"] = "PT1S"
    if mismatch == "id": row["platforms"]["youtube"]["video_id"] = "outro"
    def request(data):
        return SimpleNamespace(list=lambda **k: SimpleNamespace(execute=lambda: {"items": [data]}))
    youtube = SimpleNamespace(channels=lambda: request({"id": repair.CHANNEL}), videos=lambda: request(video))
    writes, checkpoints = [], []
    monkeypatch.setattr(repair, "require_ready", lambda *a: None)
    monkeypatch.setattr(repair.queue, "_load_queue", lambda *a: {"items": [row]})
    monkeypatch.setattr(repair.queue, "update_status", lambda *a, **k: writes.append((a, k)))
    monkeypatch.setattr(repair, "checkpoint_from_environment", lambda *a, **k: checkpoints.append(k["reason"]))
    if mismatch:
        with pytest.raises(repair.StateError): repair.reconcile(tmp_path, youtube)
        assert writes == [] and checkpoints == []
    else:
        repair.reconcile(tmp_path, youtube)
        assert writes[0][0] == ("es", repair.ITEM, "youtube", "uploaded")
        assert writes[0][1]["video_id"] == repair.VIDEO
        assert checkpoints == ["reconciliation_preflight", "reconciliation_confirmed"]
        assert row == before
