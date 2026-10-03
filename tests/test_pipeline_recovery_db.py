"""Estado por idioma sem perder o dedupe legado nem mudar o narrador."""
import sqlite3

import pytest

from stages.filter import StoryFilter
from utils.db import PipelineDB, SCHEMA


def test_falha_temporaria_nao_vira_duplicada(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1", "title": "source"}, ["pt", "en"], "a" * 64)
    db.set_language_status("s1", "pt", "processing")
    db.set_language_status("s1", "pt", "unavailable", reason_code="rate_limit")
    assert db.story_exists("s1")
    assert db.processing_languages("s1", ["pt", "en"]) == ["pt", "en"]
    assert not StoryFilter({}, db, languages=["pt"]).is_already_processed("s1")
    assert StoryFilter({}, db).is_already_processed("s1")
    assert db.retry_candidates(["pt", "en"]) == ["s1"]


def test_pt_exportado_nao_impede_en(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt", "en"], "a" * 64)
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    db.set_language_status("s1", "pt", "exported", profile_id="p1")
    assert db.processing_languages("s1", ["pt", "en"]) == ["en"]
    assert db.processing_languages("s1", ["pt-br"]) == []


def test_legado_desconhecido_permanece_bloqueado(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.insert_story({"id": "old"})
    assert db.processing_languages("old", ["pt", "en", "es"]) == []
    assert StoryFilter({}, db, languages=["en"]).is_already_processed("old")
    assert db.retry_candidates(["pt", "en"]) == []
    with pytest.raises(ValueError):
        db.register_story({"id": "old"}, ["pt"], "a" * 64)


def test_nova_historia_tem_idiomas_solicitados(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    assert db.processing_languages("new", ["pt-br", "en", "pt"]) == ["pt", "en"]


def test_novo_idioma_nao_altera_terminais_anteriores(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt"], "a" * 64)
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    db.set_language_status("s1", "pt", "exported")
    db.register_story({"id": "s1"}, ["pt", "es"], "a" * 64)
    assert db.processing_languages("s1", ["pt", "es"]) == ["es"]


def test_hash_mudado_bloqueia_sem_modificar_estado(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1", "title": "original"}, ["pt"], "a" * 64)
    with pytest.raises(ValueError):
        db.register_story({"id": "s1", "title": "new"}, ["es"], "b" * 64)
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT title,source_sha256 FROM stories WHERE id='s1'").fetchone() == ("original", "a" * 64)
        assert conn.execute("SELECT language FROM story_languages").fetchall() == [("pt",)]


@pytest.mark.parametrize("terminal", ["exported", "rejected"])
def test_terminal_nao_reabre(tmp_path, terminal):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt"], "a" * 64)
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    db.set_language_status("s1", "pt", terminal)
    db.set_language_status("s1", "pt", terminal)
    with pytest.raises(ValueError):
        db.set_language_status("s1", "pt", "processing")
    assert db.processing_languages("s1", ["pt"]) == []


def test_processando_abandonado_nao_e_retomado_automaticamente(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt"], "a" * 64)
    db.set_language_status("s1", "pt", "processing")
    assert db.processing_languages("s1", ["pt"]) == []
    assert db.retry_candidates(["pt"]) == []


def test_perfil_imutavel_entre_idiomas_e_historias_independentes(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt", "en"], "a" * 64)
    db.register_story({"id": "s2"}, ["pt"], "b" * 64)
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    db.set_language_status("s2", "pt", "processing", profile_id="p2")
    with pytest.raises(ValueError):
        db.set_language_status("s1", "en", "processing", profile_id="p2")
    db.set_language_status("s1", "en", "processing", profile_id="p1")
    with pytest.raises(ValueError):
        db.set_language_status("s1", "pt", "unavailable", profile_id="p2")


def test_migracao_duas_vezes_preserva_partes_e_legado(tmp_path):
    path = tmp_path / "pipeline.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO stories(id,title,status) VALUES ('old','legado','extracted')")
        conn.execute("INSERT INTO pipeline_parts(story_id,language,part_number,status) VALUES ('old','en',1,'exported')")
    first = PipelineDB(path)
    second = PipelineDB(path)
    assert first.story_exists("old") and second.processing_languages("old", ["en"]) == []
    assert len(second.get_pending("en")) == 1
    with sqlite3.connect(path) as conn:
        assert sum(row[1] == "source_sha256" for row in conn.execute("PRAGMA table_info(stories)")) == 1
        assert conn.execute("SELECT COUNT(*) FROM story_languages").fetchone() == (0,)


@pytest.mark.parametrize("languages,source_hash", [(["xx"], "a" * 64), ([{}], "a" * 64), ([], "a" * 64), (["pt"], ""), (["pt"], "not-a-hash")])
def test_registro_invalido_nao_insere_historia(tmp_path, languages, source_hash):
    db = PipelineDB(tmp_path / "pipeline.db")
    with pytest.raises(ValueError):
        db.register_story({"id": "s1"}, languages, source_hash)
    assert not db.story_exists("s1")


def test_status_para_idioma_nao_registrado_nao_cria_evidencia(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.insert_story({"id": "old"})
    with pytest.raises(ValueError):
        db.set_language_status("old", "en", "exported")


def test_get_pending_parametriza_idioma(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.insert_story({"id": "s1"})
    db.update_status("s1", "en", 1, "exported")
    assert db.get_pending("en' OR 1=1 --") == []


def test_registro_para_retomada_fornece_hash_e_perfil_travados(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    assert db.recovery_record("new") is None
    db.insert_story({"id": "old"})
    assert db.recovery_record("old") is None
    db.register_story({"id": "s1"}, ["pt", "en"], "a" * 64)
    assert db.recovery_record("s1") == {"source_sha256": "a" * 64, "profile_id": None}
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    assert db.recovery_record("s1") == {"source_sha256": "a" * 64, "profile_id": "p1"}
