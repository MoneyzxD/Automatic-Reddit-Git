from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

import main
from stages.narrator_profile import NarratorProfile
from stages.script_guardian import QualityRejected, QualityUnavailable


def locked_profile():
    return NarratorProfile(
        profile_id="p1", story_id="s1", source_gender="female",
        narration_gender="female", confidence=1.0, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def test_gate_final_reprovado_nao_chama_voz(tmp_path):
    guardian, voice = Mock(), Mock()
    guardian.review_and_fix.side_effect = QualityRejected(SimpleNamespace(status="rejected"))
    with pytest.raises(QualityRejected):
        main.review_and_generate_audio(
            guardian=guardian, voice_generator=voice, source_text="source",
            part_script="hook + story + closing", language="pt", story_id="s1",
            profile=locked_profile(), part_number=1, audio_path=tmp_path / "audio.mp3",
        )
    voice.generate.assert_not_called()


def test_gate_recebe_parte_inteira_e_narra_correcao_aprovada(tmp_path):
    guardian, voice = Mock(), Mock()
    guardian.review_and_fix.return_value = SimpleNamespace(
        approved_text="HOOK. Corpo corrigido. ENCERRAMENTO.", status="approved")
    voice.generate.return_value = True
    text, ok = main.review_and_generate_audio(
        guardian=guardian, voice_generator=voice, source_text="source",
        part_script="HOOK. Corpo errado. ENCERRAMENTO.", language="pt", story_id="s1",
        profile=locked_profile(), part_number=1, audio_path=tmp_path / "audio.mp3",
    )
    assert (text, ok) == ("HOOK. Corpo corrigido. ENCERRAMENTO.", True)
    assert guardian.review_and_fix.call_args.kwargs["candidate_text"] == "HOOK. Corpo errado. ENCERRAMENTO."
    assert guardian.review_and_fix.call_args.kwargs["final_gate"] is True
    voice.generate.assert_called_once_with(text, "pt", tmp_path / "audio.mp3", narrator_gender="female")


def test_dependencia_obrigatoria_indisponivel_retorna_codigo_2(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda: {})
    monkeypatch.setattr(main, "run_pipeline", Mock(side_effect=QualityUnavailable(SimpleNamespace(status="unavailable"))))
    assert main.cli(["--test-story", "--lang", "pt"]) == 2


def test_fixture_pipeline_nao_consulta_groq_real(pipeline, monkeypatch):
    import utils.groq_client as groq_client
    monkeypatch.setenv("GROQ_API_KEY_EN", "chave-sintetica-nao-usar")
    client = Mock(side_effect=AssertionError("Teste não pode consultar Groq real"))
    monkeypatch.setattr(groq_client, "tracked_groq", client)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    client.assert_not_called()


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    from stages import (adapter, translator, naturalizer, titler, voice, subtitle, narrator_profile,
                        video, thumbnail, metadata, script_guardian, word_timing)
    from scheduler import notifier, queue
    story = {"id": "s1", "title": "My sister asked for money", "text":
             "I (28F) work as a nurse. My sister asked for money and I refused the loan."}
    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    monkeypatch.setattr(main, "TEST_STORY", story)
    monkeypatch.setenv("PIPELINE_DB_PATH", str(tmp_path / "db" / "pipeline.db"))
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [tmp_path / "data" / "queue"])
    state = SimpleNamespace(calls=[], audios=[], renders=[], notices=[], subtitles=[], thumbnails=[],
                            fail=None, outage=False, fail_language=None, fail_text="", final_patch=False,
                            config={"base_dir": str(tmp_path), "translator": {"retry_waits": [0, 0], "delay": 0},
                                    "script_quality": {"semantic_retry_wait_seconds": 0}}, root=tmp_path)

    class LT:
        def __init__(self, config):
            pass

        def health(self, **kwargs):
            return SimpleNamespace(version="6.6", locales=("pt-BR", "en-US", "es"))

        def check(self, text, language):
            return []

    class Semantic:
        def __init__(self, config):
            pass

        def review(self, **context):
            if context["mode"] == "facts":
                return json.dumps({"facts": []})
            state.calls.append(context)
            if (context["stage"] == state.fail and context["mode"] == "chunk"
                    and (state.fail_language is None or context["language"] == state.fail_language)
                    and state.fail_text in context["candidate_text"]):
                if state.outage:
                    raise RuntimeError("https://provider.test?secret=SECRET")
                return json.dumps({"approved": False, "issues": []})
            issues = []
            if "ERRADO" in context["candidate_text"] and context["mode"] == "chunk":
                issues.append(dict(original="ERRADO", replacement="APROVADO", category="grammar",
                                   severity="critical", subject="text", reason="correção",
                                   source_quote=""))
            if (state.final_patch and context["stage"] == "pre_tts" and context["mode"] == "chunk"
                    and context["candidate_text"].startswith("Minha irmã disse APROVADO?")):
                issues.append(dict(original="Minha irmã disse APROVADO?", replacement="Minha irmã disse CORRIGIDO?",
                                   category="grammar", severity="critical", subject="text", reason="correção",
                                   source_quote="", start=0))
            return json.dumps({"approved": not issues, "issues": issues})

    monkeypatch.setattr(script_guardian, "LanguageToolClient", LT)
    monkeypatch.setattr(script_guardian, "_GroqReviewer", Semantic)
    # O perfil usa evidência explícita sintética; nenhum teste chama a API real.
    monkeypatch.setattr(narrator_profile.NarratorProfileResolver, "_groq_evidence", lambda *args: [])
    monkeypatch.setattr(adapter.StoryAdapter, "_groq_adapt", lambda self, story: {
        **story, "full_script": story["text"] + " ERRADO.", "adapted_by": "groq"})
    localized = {
        "pt": "Eu sou uma enfermeira. Minha irmã pediu dinheiro e eu recusei emprestar porque ela ofendeu meu trabalho.",
        "es": "Soy una enfermera. Mi hermana me pidió dinero y yo rechacé el préstamo porque ella insultó mi trabajo.",
    }
    monkeypatch.setattr(translator.ScriptTranslator, "_translate_chunk_google",
                        lambda self, text, source, target: localized[target] + " ERRADO.")
    monkeypatch.setattr(translator.ScriptTranslator, "_translate_chunk_mymemory", lambda *args: None)
    monkeypatch.setattr(naturalizer.ScriptNaturalizer, "_groq_rewrite",
                        lambda self, text, language, gender: text + " Pensei ERRADO.")
    for name in ("_groq_title", "_groq_hook", "_groq_closing"):
        monkeypatch.setattr(titler.TitleGenerator, name, lambda *args: "Minha irmã disse ERRADO?")
    monkeypatch.setattr(metadata.MetadataGenerator, "_description_via_groq",
                        lambda *args: "Minha irmã falou ERRADO.")
    def audio(self, text, language, path, narrator_gender):
        state.audios.append((text, language, narrator_gender))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return True
    def render(self, **kwargs):
        state.renders.append(kwargs)
        path = kwargs["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return True
    monkeypatch.setattr(voice.VoiceGenerator, "generate", audio)
    monkeypatch.setattr(word_timing, "load_word_boundaries", lambda path: [])
    def subtitles(self, audio_path, language, output_path, **kwargs):
        state.subtitles.append(kwargs["script_text"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("ASS", encoding="utf-8")
        return True
    monkeypatch.setattr(subtitle.SubtitleGenerator, "generate", subtitles)
    monkeypatch.setattr(video.VideoRenderer, "render", render)
    def thumbnail_image(self, text, language, path):
        state.thumbnails.append(text)
        return False
    monkeypatch.setattr(thumbnail.ThumbnailGenerator, "generate", thumbnail_image)
    monkeypatch.setattr(thumbnail.ThumbnailGenerator, "render_hook_card_video", lambda *args, **kwargs: None)
    monkeypatch.setattr(thumbnail.ThumbnailGenerator, "render_hook_card", lambda *args: None)
    monkeypatch.setattr(main, "get_audio_duration", lambda path: 30)
    monkeypatch.setattr(notifier, "notify_pipeline_result", lambda *args: state.notices.append(args))
    monkeypatch.setattr(notifier, "send_admin_alert", lambda *args: True)
    return state


def test_gates_derivados_usam_roteiro_sem_serializar_ledger_como_fonte(pipeline, monkeypatch):
    from stages import naturalizer, script_guardian

    localized = {"pt": "Recusei novos empréstimos depois de descobrir a mentira.",
                 "es": "Rechacé nuevos préstamos después de descubrir la mentira.",
                 "en": "I refused further loans after discovering the lie."}
    monkeypatch.setattr(naturalizer.ScriptNaturalizer, "_groq_rewrite",
                        lambda self, text, language, gender: localized[language])
    original_review = script_guardian._GroqReviewer.review
    facts_sources = []

    def review(self, **context):
        if context["mode"] == "facts":
            units = context["source_units"]
            facts_sources.append("".join(unit["text"] for unit in units))
            return json.dumps({"facts": [{"kind": "event", "value": "loan decision",
                                         "source_unit_ids": [units[0]["id"]]}]})
        return original_review(self, **context)

    monkeypatch.setattr(script_guardian._GroqReviewer, "review", review)
    main.run_pipeline(pipeline.config, ["pt", "en", "es"], test_story=True)
    derived = [c for c in pipeline.calls if c["stage"] in {
        "title", "opening_hook", "closing_hook", "injected_hook", "split_part", "metadata", "pre_tts"}]
    assert {c["language"] for c in derived} == {"pt", "en", "es"}
    assert all(c["source_chunk"] == localized[c["language"]] for c in derived)
    assert all("source_quote" not in source and "Fatos validados" not in source for source in facts_sources)
    assert all(json.loads(c["factual_context"])[0]["source_quote"] == localized[c["language"]]
               for c in derived)
    assert len(pipeline.audios) == 3


def test_metadados_reprovados_impedem_audio_render_export_e_fila(pipeline):
    pipeline.fail = "metadata"
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert pipeline.audios == pipeline.renders == []
    assert not (pipeline.root / "data" / "exports").exists()
    assert not list((pipeline.root / "data" / "queue").glob("*.json"))
    quarantine = list((pipeline.root / "data" / "quarantine" / "s1").glob("*.json"))
    assert len(quarantine) == 1
    report = json.loads(quarantine[0].read_text(encoding="utf-8"))
    assert report["stage"] == "metadata"
    assert report["profile_id"]
    assert report["source_sha256"]


def test_retomada_nao_gera_pt_duas_vezes(pipeline):
    from scheduler.queue import get_pending
    pipeline.fail, pipeline.fail_language, pipeline.outage = "translation", "es", True
    with pytest.raises(QualityUnavailable):
        main.run_pipeline(pipeline.config, ["pt", "es"], test_story=True)
    assert len(get_pending("pt")) == 1
    prior_audios = len(pipeline.audios)
    prior_profile = get_pending("pt")[0]["metadata"]["narrator_profile_id"]
    pipeline.fail = None
    main.run_pipeline(pipeline.config, ["pt", "es"], test_story=True)
    assert len(get_pending("pt")) == len(get_pending("es")) == 1
    assert get_pending("es")[0]["metadata"]["narrator_profile_id"] == prior_profile
    assert all(language == "es" for _, language, _ in pipeline.audios[prior_audios:])


def test_adaptacao_indisponivel_torna_todos_idiomas_retomaveis(pipeline):
    from utils.db import PipelineDB
    pipeline.fail, pipeline.outage = "adaptation", True
    with pytest.raises(QualityUnavailable):
        main.run_pipeline(pipeline.config, ["pt", "en", "es"], test_story=True)
    db = PipelineDB(pipeline.root / "db/pipeline.db")
    assert db.processing_languages("s1", ["pt", "en", "es"]) == ["pt", "en", "es"]
    assert pipeline.audios == []


def test_retomada_reusa_roteiro_aprovado_mas_repete_gate_pre_tts(pipeline, monkeypatch):
    from stages import adapter, voice, narrator_profile
    original = voice.VoiceGenerator.generate
    monkeypatch.setattr(voice.VoiceGenerator, "generate", lambda *args, **kwargs: False)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    initial_pre_tts = len([c for c in pipeline.calls if c["stage"] == "pre_tts"])
    monkeypatch.setattr(voice.VoiceGenerator, "generate", original)
    def no_regenerate(*args, **kwargs):
        raise AssertionError("Fonte/perfil/roteiro aprovados não devem ser gerados novamente")
    monkeypatch.setattr(adapter.StoryAdapter, "adapt", no_regenerate)
    monkeypatch.setattr(narrator_profile.NarratorProfileResolver, "resolve", no_regenerate)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert len(pipeline.audios) == 1
    assert len([c for c in pipeline.calls if c["stage"] == "pre_tts"]) > initial_pre_tts


def test_perfil_persistido_ausente_bloqueia_sem_redetectar(pipeline, monkeypatch):
    from stages import voice, narrator_profile
    monkeypatch.setattr(voice.VoiceGenerator, "generate", lambda *args, **kwargs: False)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    for path in (pipeline.root / "data/scripts/profiles").glob("*.json"):
        path.unlink()
    called = []
    monkeypatch.setattr(narrator_profile.NarratorProfileResolver, "resolve", lambda *args, **kwargs: called.append(1))
    with pytest.raises(ValueError):
        main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert called == []


@pytest.mark.parametrize("stage", ["audio", "subtitle", "render"])
def test_falha_de_midia_na_segunda_parte_nao_enfileira_primeira(pipeline, monkeypatch, stage):
    from stages import voice, subtitle, video
    monkeypatch.setattr(main, "TEST_STORY", {
        "id": "s1", "title": "My sister asked for money",
        "text": "I (28F) work as a nurse.\n\n" + "\n\n".join([
            "I kept working as a nurse and refused the loan. " * 20 for _ in range(3)]),
    })
    cls, method = {"audio": (voice.VoiceGenerator, "generate"),
                   "subtitle": (subtitle.SubtitleGenerator, "generate"),
                   "render": (video.VideoRenderer, "render")}[stage]
    original = getattr(cls, method)
    attempts = []
    def media(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 2:
            return False
        return original(self, *args, **kwargs)
    monkeypatch.setattr(cls, method, media)
    main.run_pipeline(pipeline.config, ["en"], test_story=True)
    assert len(attempts) == 2
    assert not (pipeline.root / "data" / "exports").exists()
    assert not list((pipeline.root / "data" / "queue").glob("*.json"))


def test_tres_idiomas_mesmo_perfil_e_correcao_em_todos_os_destinos(pipeline):
    main.run_pipeline(pipeline.config, ["pt", "en", "es"], test_story=True)
    calls = [call for call in pipeline.calls if call["mode"] == "global"]
    assert calls[0]["stage"] == "adaptation"
    assert "28-year-old woman" in calls[0]["source_chunk"]
    for language in ("pt", "en", "es"):
        stages = list(dict.fromkeys(call["stage"] for call in calls if call["language"] == language))
        if language == "en":
            stages = stages[1:]
        assert stages == ["translation", "naturalization", "title", "opening_hook", "closing_hook",
                          "injected_hook", "split_part", "metadata", "pre_tts"]
        trans = next(call for call in calls if call["stage"] == "translation" and call["language"] == language)
        nat = next(call for call in calls if call["stage"] == "naturalization" and call["language"] == language)
        assert "ERRADO" not in trans["source_chunk"]
        assert "ERRADO" not in nat["source_chunk"]
    assert len({call["profile"]["profile_id"] for call in calls}) == 1
    assert len(pipeline.audios) == len(pipeline.renders) == 3
    for text, language, gender in pipeline.audios:
        assert gender == "female"
        assert "ERRADO" not in text
        assert text.startswith("Minha irmã disse APROVADO?")
        assert text.endswith("Minha irmã disse APROVADO?")
        saved = (pipeline.root / "data" / "scripts" / language / "s1_part1_final.txt").read_text(encoding="utf-8")
        assert saved == text
    metas = [json.loads(path.read_text(encoding="utf-8")) for path in (pipeline.root / "data" / "exports").rglob("*.json")]
    assert len(metas) == 3
    assert len({meta["narrator_profile_id"] for meta in metas}) == 1
    assert all(meta["description"] == "Minha irmã falou APROVADO." for meta in metas)
    assert all("ERRADO" not in json.dumps(meta, ensure_ascii=False) for meta in metas)


@pytest.mark.parametrize("stage", ["adaptation", "translation", "naturalization", "title",
                                  "opening_hook", "closing_hook", "injected_hook", "split_part", "pre_tts"])
def test_reprovacao_de_checkpoint_nao_publica(pipeline, stage):
    pipeline.fail = stage
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert pipeline.audios == pipeline.renders == []
    assert not (pipeline.root / "data" / "exports").exists()
    assert not list((pipeline.root / "data" / "queue").glob("*.json"))
    assert list((pipeline.root / "data" / "quarantine" / "s1").glob("*.json"))


@pytest.mark.parametrize("stage", ["adaptation", "translation", "naturalization", "metadata", "pre_tts"])
def test_indisponibilidade_nao_publica_e_escapa_para_interromper_lote(pipeline, stage):
    pipeline.fail, pipeline.outage = stage, True
    with pytest.raises(QualityUnavailable):
        main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert pipeline.audios == pipeline.renders == []
    assert not (pipeline.root / "data" / "exports").exists()
    assert "SECRET" not in json.dumps(pipeline.notices)
    assert "provider.test" not in json.dumps(pipeline.notices)
    assert pipeline.notices[-1][1]["dependency"]


def test_quarentena_rejeita_escape_da_raiz(tmp_path):
    from stages.script_guardian import ScriptReview
    review = ScriptReview("rejected", "candidate", (), (), 1, False, "")
    with pytest.raises(ValueError, match="inseguro"):
        main.quarantine_review(tmp_path, review, "candidate", story_id="../escape", language="pt",
                               stage="metadata", profile=locked_profile(), source_text="source")


def test_gate_sem_excecao_mas_nao_aprovado_tambem_bloqueia_voz(tmp_path):
    guardian, voice = Mock(), Mock()
    guardian.review_and_fix.return_value = SimpleNamespace(status="unavailable", approved_text="texto")
    with pytest.raises(QualityUnavailable):
        main.review_and_generate_audio(
            guardian=guardian, voice_generator=voice, source_text="source", part_script="texto",
            language="pt", story_id="s1", profile=locked_profile(), part_number=1,
            audio_path=tmp_path / "audio.mp3")
    voice.generate.assert_not_called()


@pytest.mark.parametrize("status", ["rejected", "unavailable"])
@pytest.mark.parametrize("title_only", [False, True])
def test_falha_tipificada_da_traducao_nao_vira_audio_ingles(pipeline, monkeypatch, status, title_only):
    from stages.translator import ScriptTranslator
    original = ScriptTranslator._translate_chunk_google
    def translate(self, text, source, target):
        if target == "pt" and (not title_only or text == "My sister asked for money"):
            return text if status == "rejected" else None
        return original(self, text, source, target)
    monkeypatch.setattr(ScriptTranslator, "_translate_chunk_google", translate)
    if status == "unavailable":
        with pytest.raises(QualityUnavailable):
            main.run_pipeline(pipeline.config, ["pt", "en"], test_story=True)
        assert pipeline.audios == []
    else:
        main.run_pipeline(pipeline.config, ["pt", "en"], test_story=True)
        assert [language for _, language, _ in pipeline.audios] == ["en"]
    assert not (pipeline.root / "data" / "exports" / "pt").exists()
    stage = "title_translation" if title_only else "translation"
    report = json.loads((pipeline.root / "data" / "quarantine" / "s1" / f"pt_{stage}.json").read_text(encoding="utf-8"))
    assert report["review"]["status"] == status


def test_rejeicao_tardia_da_segunda_parte_nao_enfileira_primeira(pipeline, monkeypatch):
    monkeypatch.setattr(main, "TEST_STORY", {
        "id": "s1", "title": "My sister asked for money",
        "text": "I (28F) work as a nurse.\n\n" + "\n\n".join([
            "I kept working as a nurse and refused the loan. " * 20 for _ in range(3)]),
    })
    pipeline.fail, pipeline.fail_text = "pre_tts", "\n\nPart 2\n\n"
    main.run_pipeline(pipeline.config, ["en"], test_story=True)
    assert len(pipeline.audios) == len(pipeline.renders) == 1
    assert not (pipeline.root / "data" / "exports").exists()
    assert not list((pipeline.root / "data" / "queue").glob("*.json"))
    assert (pipeline.root / "data" / "quarantine" / "s1" / "en_pre_tts_part2.json").exists()


def test_preflight_falha_antes_da_extracao_e_do_dedupe(pipeline, monkeypatch):
    from stages import script_guardian, extractor
    monkeypatch.setattr(script_guardian.LanguageToolClient, "health", Mock(side_effect=RuntimeError("SECRET")))
    extraction = Mock()
    monkeypatch.setattr(extractor.RedditExtractor, "run", extraction)
    with pytest.raises(QualityUnavailable):
        main.run_pipeline(pipeline.config, ["pt"])
    extraction.assert_not_called()
    assert not (pipeline.root / "db" / "pipeline.db").exists()
    assert pipeline.calls == pipeline.audios == []
    assert "SECRET" not in json.dumps(pipeline.notices)


@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_nao_abre_banco_persistente(pipeline, monkeypatch, existing):
    import sqlite3
    from utils import db
    database = pipeline.root / "db/pipeline.db"
    if existing:
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE sentinela (id INTEGER PRIMARY KEY)")
        before = database.read_bytes()
    constructor = Mock(wraps=db.PipelineDB)
    monkeypatch.setattr(db, "PipelineDB", constructor)
    main.run_pipeline(pipeline.config, ["pt"], dry_run=True, test_story=True)
    constructor.assert_not_called()
    assert database.exists() is existing
    if existing:
        assert database.read_bytes() == before


def test_dry_run_com_historia_real_nao_marca_dedupe_nem_chama_provedores(pipeline):
    from utils.db import PipelineDB
    raw = pipeline.root / "data" / "raw"
    raw.mkdir(parents=True)
    story = {**main.TEST_STORY, "upvote_ratio": 0.99}
    (raw / "s1.json").write_text(json.dumps(story), encoding="utf-8")
    pipeline.config["filtering"] = {"min_score": 0}
    main.run_pipeline(pipeline.config, ["pt", "en", "es"], dry_run=True)
    assert pipeline.calls == pipeline.audios == pipeline.renders == []
    assert not PipelineDB(pipeline.root / "db" / "pipeline.db").story_exists("s1")
    assert not list(pipeline.root.rglob("*_narrator_profile.json"))
    assert not (pipeline.root / "data" / "exports").exists()
    assert not list((pipeline.root / "data" / "queue").glob("*.json"))


def test_correcao_real_no_gate_final_chega_a_audio_legenda_card_e_metadados(pipeline):
    pipeline.final_patch = True
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    text = pipeline.audios[0][0]
    assert text.startswith("Minha irmã disse CORRIGIDO?")
    assert pipeline.subtitles == [text]
    assert pipeline.thumbnails == ["Minha irmã disse CORRIGIDO?"]
    meta_path = next((pipeline.root / "data" / "exports").rglob("*.json"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["hook"] == "Minha irmã disse CORRIGIDO?"
    assert meta["youtube"]["title"] == "Minha irmã disse CORRIGIDO? #shorts"
    assert meta["tiktok"]["caption"].startswith("Minha irmã disse CORRIGIDO?")


def test_excecao_alheia_nao_vira_reprovacao_de_conteudo(pipeline, monkeypatch):
    from stages.naturalizer import ScriptNaturalizer
    monkeypatch.setattr(ScriptNaturalizer, "_groq_rewrite", Mock(side_effect=ValueError("bug interno")))
    with pytest.raises(ValueError, match="bug interno"):
        main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert not (pipeline.root / "data" / "quarantine").exists()
    assert pipeline.audios == []


def test_quarentena_atomica_preserva_relatorio_anterior_em_falha(tmp_path, monkeypatch):
    import os
    from stages.script_guardian import ScriptReview
    review = ScriptReview("rejected", "candidate", (), (), 1, False, "")
    context = dict(story_id="s1", language="pt", stage="metadata", profile=locked_profile(), source_text="source")
    path = main.quarantine_review(tmp_path, review, "candidate", **context)
    original = path.read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disco indisponível")))
    with pytest.raises(OSError):
        main.quarantine_review(tmp_path, review, "outra candidata", **context)
    assert path.read_text(encoding="utf-8") == original
    assert not list(path.parent.glob("*.tmp"))


def test_rejeicao_base_retorna_zero_na_cli_e_nao_inicia_idiomas(pipeline, monkeypatch):
    pipeline.fail = "adaptation"
    monkeypatch.setattr(main, "load_config", lambda: pipeline.config)
    assert main.cli(["--test-story", "--lang", "pt", "en", "es"]) == 0
    assert pipeline.audios == []
    assert {call["stage"] for call in pipeline.calls} == {"adaptation"}


def test_rejeicao_de_um_idioma_preserva_outros(pipeline):
    pipeline.fail, pipeline.fail_language = "metadata", "pt"
    main.run_pipeline(pipeline.config, ["pt", "en", "es"], test_story=True)
    assert {language for _, language, _ in pipeline.audios} == {"en", "es"}
    assert not (pipeline.root / "data" / "exports" / "pt").exists()
    assert (pipeline.root / "data" / "exports" / "en").exists()
    assert (pipeline.root / "data" / "exports" / "es").exists()


def test_codigo_2_da_cli_interrompe_lote_sem_buscar_proxima_historia(pipeline, monkeypatch):
    from stages import script_guardian
    from scripts import generate_daily_batch
    monkeypatch.setattr(main, "load_config", lambda: pipeline.config)
    monkeypatch.setattr(script_guardian.LanguageToolClient, "health", Mock(side_effect=RuntimeError("offline")))
    launches = []
    def launch(command, **kwargs):
        launches.append(command)
        return SimpleNamespace(returncode=main.cli(command[2:]))
    monkeypatch.setattr(generate_daily_batch.subprocess, "run", launch)
    with pytest.raises(RuntimeError, match="codigo 2"):
        generate_daily_batch.preencher_lote(["pt"], meta=1, max_tentativas=6)
    assert len(launches) == 1
    assert pipeline.audios == []


@pytest.mark.parametrize("quoted", [False, True])
def test_jsonl_e_quarentena_sanitizam_strings_e_preservam_hashes(tmp_path, monkeypatch, quoted):
    import hashlib
    import os
    from dataclasses import asdict
    from stages.script_guardian import ScriptReview, ReviewIssue, TextPatch
    from utils import telemetry

    # O redactor vê somente configurações sintéticas, sem consultar .env/arquivos de token.
    opaque = "AQ.chave-opaca-sintetica-sem-prefixo-legado"
    oauth = "oauth-valor-sintetico-aninhado"
    client_secret = "cliente-segredo-sintetico-aninhado"
    session = "sessao-opaca-sintetica"
    monkeypatch.setattr(os, "environ", {
        "GROQ_API_KEY_PT": f"'{opaque}'" if quoted else opaque,
        "YOUTUBE_TOKEN_PT": f"'{json.dumps({'token': oauth})}'" if quoted else json.dumps({"token": oauth}),
        "YOUTUBE_CREDENTIALS": json.dumps({"installed": {"client_secret": client_secret}}),
        "REDDIT_SESSION_COOKIE": f"reddit_session={session}; csrftoken=csrf-sintetico",
    })
    candidate = (
        f"Texto normal. {opaque} {oauth} {session} {client_secret}\n"
        "Cookie: reddit_session=COOKIE_SINTETICO; other=OUTRO_COOKIE\n"
        "Authorization: Bearer AUTH_SINTETICO\n"
        "api_key=KEY_SINTETICA password='SENHA SINTETICA' credentials=CREDS_SINTETICAS\n"
        "API key: VALOR_SINTETICO\n"
        "Bearer TOKEN_BEARER_SINTETICO\n"
        "https://api.telegram.org/bot123456789:AAAAAAAAAAAAAAAAAAAAAAAA/sendMessage"
    )
    source = "Fonte original com token=TOKEN_FONTE"
    review = ScriptReview("rejected", candidate, (
        ReviewIssue("grammar", "critical", candidate, candidate, source_quote=candidate),
    ), (TextPatch(candidate, candidate, "grammar", "critical", "text", candidate, candidate),),
        1, False, candidate)
    path = tmp_path / "quality.jsonl"
    telemetry.append_quality_report(path, {
        "review": asdict(review), "candidate_text": candidate,
        "credentials": "CAMPO_CREDENCIAL", "password": "CAMPO_SENHA",
    })
    quarantine = main.quarantine_review(
        tmp_path, review, candidate, story_id="s1", language="pt", stage="metadata",
        profile=locked_profile(), source_text=source,
    )
    for report_path in (path, quarantine):
        persisted = report_path.read_text(encoding="utf-8")
        assert "Texto normal." in persisted
        assert "[REDACTED]" in persisted
        for secret in (opaque, oauth, session, client_secret, "COOKIE_SINTETICO", "OUTRO_COOKIE", "AUTH_SINTETICO",
                       "KEY_SINTETICA", "SENHA SINTETICA", "CREDS_SINTETICAS", "TOKEN_BEARER_SINTETICO",
                       "123456789:AAAAAAAAAAAAAAAAAAAAAAAA", "CAMPO_CREDENCIAL", "CAMPO_SENHA", "VALOR_SINTETICO"):
            assert secret not in persisted
        json.loads(persisted)
    data = json.loads(quarantine.read_text(encoding="utf-8"))
    assert data["source_sha256"] == hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert data["candidate_sha256"] == hashlib.sha256(candidate.encode("utf-8")).hexdigest()
