from unittest.mock import Mock
from types import SimpleNamespace

import pytest

import main
from stages.narrator_profile import NarratorProfile, NarratorProfileResolver


def male_profile(story_id="test_001"):
    return NarratorProfile(
        profile_id="profile-123", story_id=story_id, source_gender="male",
        narration_gender="male", confidence=0.99, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def test_resolve_historia_uma_vez_e_propaga_mesmo_perfil():
    resolver = Mock()
    resolver.resolve.return_value = male_profile()
    profile = main.resolve_story_narrator(
        resolver, "test_001", "Title", "I (28M) live with my husband."
    )
    original = {"language": "pt"}
    payloads = [main.attach_narrator_profile({"language": lang}, profile)
                for lang in ("pt", "en", "es")]
    main.attach_narrator_profile(original, profile)
    assert original == {"language": "pt"}
    resolver.resolve.assert_called_once_with(
        story_id="test_001", title="Title", original_text="I (28M) live with my husband."
    )
    assert {item["narrator_gender"] for item in payloads} == {"male"}
    assert {item["narrator_profile_id"] for item in payloads} == {"profile-123"}
    assert {item["narrator_confidence"] for item in payloads} == {0.99}
    assert {item["narrator_method"] for item in payloads} == {"explicit"}


@pytest.mark.parametrize("source,gender", [
    ("I (28M) live with my husband.", "male"),
    ("I (28F) live with my wife.", "female"),
])
def test_perfil_preserva_evidencia_explicita_apos_expansao(source, gender):
    resolver = NarratorProfileResolver({}, semantic_enabled=False)
    profile = main.resolve_story_narrator(
        resolver, "test_001", "My spouse", main.expand_age_gender_en(source))
    assert profile.source_gender == gender
    assert profile.narration_gender == gender
    assert profile.decision_method == "explicit"
    assert profile.evidence


@pytest.mark.parametrize("source", [
    "My husband (28M) told me I should leave.",
    'He said "I (28M) feel tired".',
    "They assume I (28M) live alone.",
])
def test_expansao_nao_transforma_terceiros_ou_crencas_em_identidade(source):
    profile = main.resolve_story_narrator(
        NarratorProfileResolver({}, semantic_enabled=False), "test_001", "Family",
        main.expand_age_gender_en(source))
    assert profile.source_gender == "unknown"
    assert not profile.evidence


@pytest.mark.parametrize("dry_run", [False, True])
def test_pipeline_resolve_antes_da_adaptacao_e_preserva_perfil(monkeypatch, tmp_path, dry_run):
    from stages import (adapter, translator, naturalizer, gender_detector, titler,
                        voice, subtitle, video, thumbnail, organizer, validator,
                        narrator_profile, metadata, splitter, word_timing, script_guardian)
    from utils import db
    from scheduler import notifier

    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    story = {"id": "test_001", "title": "My husband", "text": "I (28M) live with my husband."}
    monkeypatch.setattr(main, "TEST_STORY", story)
    resolver = Mock()
    resolver.resolve.return_value = male_profile()
    factory = Mock(return_value=resolver)
    monkeypatch.setattr(narrator_profile, "NarratorProfileResolver", factory)
    persisted = Mock()
    monkeypatch.setattr(narrator_profile, "save_profile", persisted)
    monkeypatch.setattr(db, "PipelineDB", Mock())
    monkeypatch.setattr(notifier, "notify_pipeline_result", Mock())
    adapt = Mock()

    def adapt_story(payload):
        assert resolver.resolve.call_count == 1
        assert payload["narrator_profile_id"] == "profile-123"
        return {**payload, "full_script": payload["text"]}

    adapt.adapt.side_effect = adapt_story
    monkeypatch.setattr(adapter, "StoryAdapter", Mock(return_value=adapt))
    trans = Mock()
    trans.translate_all.return_value = {
        lang: translator.TranslationResult("approved", "Estou sozinho.", "teste", "en", lang, ())
        for lang in ("pt", "en", "es")}
    trans.translate_title.return_value = "Conflito em casa"
    monkeypatch.setattr(translator, "ScriptTranslator", Mock(return_value=trans))
    nat = Mock()
    nat.naturalize.side_effect = lambda text, lang, gender: text
    monkeypatch.setattr(naturalizer, "ScriptNaturalizer", Mock(return_value=nat))
    correction = Mock()
    correction.validate_and_fix.side_effect = lambda text, gender, lang: text
    monkeypatch.setattr(gender_detector, "GenderDetector", Mock(return_value=correction))
    titles = Mock()
    titles.generate.return_value = "Conflito em casa"
    titles.generate_hook.return_value = "Minha familia discutiu comigo."
    titles.generate_closing_hook.return_value = "O que voce faria?"
    monkeypatch.setattr(titler, "TitleGenerator", Mock(return_value=titles))
    checks = Mock()
    checks.assert_ready = Mock()
    checks.review_and_fix.side_effect = lambda **kwargs: SimpleNamespace(
        approved_text=kwargs["candidate_text"], status="approved", factual_context="")
    monkeypatch.setattr(script_guardian, "ScriptGuardian", Mock(return_value=checks))
    audio = Mock()
    audio.generate.return_value = True
    monkeypatch.setattr(voice, "VoiceGenerator", Mock(return_value=audio))
    monkeypatch.setattr(word_timing, "load_word_boundaries", lambda path: [])
    monkeypatch.setattr(main, "get_audio_duration", lambda path: 30)
    for module, name in ((subtitle, "SubtitleGenerator"), (video, "VideoRenderer"),
                         (thumbnail, "ThumbnailGenerator")):
        monkeypatch.setattr(module, name, Mock())
    monkeypatch.setattr(organizer.FileOrganizer, "organize_output", Mock())
    monkeypatch.setattr(metadata.MetadataGenerator, "_description_via_groq", lambda *args: None)
    split_real = splitter.split_story
    parts = []

    def split_spy(*args, **kwargs):
        result = split_real(*args, **kwargs)
        parts.extend(result)
        return result

    monkeypatch.setattr(splitter, "split_story", split_spy)
    main.run_pipeline({}, ["pt", "en", "es"], dry_run=dry_run, test_story=True)
    factory.assert_called_once_with({}, semantic_enabled=not dry_run)
    resolver.resolve.assert_called_once_with(
        story_id="test_001", title="My husband", original_text="I 28-year-old man live with my husband.")
    correction.detect.assert_not_called()
    assert {p["language"] for p in parts} == {"pt", "en", "es"}
    assert {p["narrator_profile_id"] for p in parts} == {"profile-123"}
    assert {p["narrator_gender"] for p in parts} == {"male"}
    if dry_run:
        persisted.assert_not_called()
        audio.generate.assert_not_called()
        assert not list(tmp_path.rglob("*_narrator_profile.json"))
    else:
        persisted.assert_called_once_with(resolver.resolve.return_value, tmp_path)
        correction.bind_profile.assert_not_called()
        assert len(audio.generate.call_args_list) == 3
        assert all(c.kwargs["profile"] is resolver.resolve.return_value
                   for c in checks.review_and_fix.call_args_list)
        for method in (audio.generate,
                       titles.generate, titles.generate_hook, titles.generate_closing_hook):
            assert method.call_args_list
            assert all(c.kwargs["narrator_gender"] == "male" for c in method.call_args_list)
        assert all(c.args[2] == "male" for c in nat.naturalize.call_args_list)
        import json
        saved = [json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.rglob("*_meta.json")]
        assert len(saved) == 3
        assert {m["narrator_profile_id"] for m in saved} == {"profile-123"}
        assert {m["narrator_gender"] for m in saved} == {"male"}
