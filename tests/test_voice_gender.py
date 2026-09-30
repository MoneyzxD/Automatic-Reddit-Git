from unittest.mock import Mock

import pytest

from stages.voice import VoiceGenerator


CONFIG = {"voices": {"pt": {
    "female": {"primary": "pt-f-1", "fallback": "pt-f-2"},
    "male": {"primary": "pt-m-1", "fallback": "pt-m-2"},
}}}


@pytest.fixture(autouse=True)
def isolar_provedores(monkeypatch):
    monkeypatch.setattr("stages.voice.generate_audio_with_timestamps", Mock(return_value=(False, [])))
    monkeypatch.setattr(VoiceGenerator, "_gtts_generate", Mock(return_value=False))


def test_fallback_da_voz_preserva_genero():
    voice = VoiceGenerator(CONFIG)
    assert voice._select_voice("pt", "male") == ("pt-m-1", "pt-m-2")
    assert voice._select_voice("pt-br", "female") == ("pt-f-1", "pt-f-2")


@pytest.mark.parametrize("invalid", ["unknown", "", None])
def test_voz_rejeita_genero_antes_de_provedor(invalid, monkeypatch, tmp_path):
    voice = VoiceGenerator({**CONFIG, "force_gtts": True})
    provider = Mock()
    monkeypatch.setattr(voice, "_gtts_generate", provider)
    with pytest.raises(ValueError, match="male ou female"):
        voice.generate("Texto", "pt", tmp_path / "voz.mp3", narrator_gender=invalid)
    provider.assert_not_called()
    with pytest.raises(ValueError, match="male ou female"):
        voice._select_voice("pt", invalid)


def test_genero_obrigatorio_nas_entradas(tmp_path):
    voice = VoiceGenerator(CONFIG)
    for method in (voice.generate, voice._edge_tts_generate):
        with pytest.raises(TypeError):
            method("Texto", "pt", tmp_path / "voz.mp3")


@pytest.mark.parametrize("gender,expected", [
    ("male", ["pt-m-1", "pt-m-2"]),
    ("female", ["pt-f-1", "pt-f-2"]),
])
def test_falha_edge_nao_troca_genero_nem_chama_gtts(gender, expected, monkeypatch, tmp_path):
    provider = Mock(return_value=(False, []))
    monkeypatch.setattr("stages.voice.generate_audio_with_timestamps", provider)
    voice = VoiceGenerator(CONFIG)
    gtts = Mock(return_value=True)
    monkeypatch.setattr(voice, "_gtts_generate", gtts)
    assert voice.generate("Texto", "pt", tmp_path / "voz.mp3", narrator_gender=gender) is False
    assert [call.args[1] for call in provider.call_args_list] == expected
    gtts.assert_not_called()


def test_sem_fallback_tenta_apenas_voz_do_genero(monkeypatch, tmp_path):
    provider = Mock(return_value=(False, []))
    monkeypatch.setattr("stages.voice.generate_audio_with_timestamps", provider)
    voice = VoiceGenerator({"voices": {"pt": {"male": {"primary": "pt-m-1"}}}})
    assert voice.generate("Texto", "pt", tmp_path / "voz.mp3", narrator_gender="male") is False
    assert provider.call_count == 1


@pytest.mark.parametrize("allowed", [False, True])
def test_force_gtts_respeita_permissao_explicita(allowed, monkeypatch, tmp_path):
    voice = VoiceGenerator({**CONFIG, "force_gtts": True,
                            "allow_uncontrolled_gender_fallback": allowed})
    gtts = Mock(return_value=False)
    monkeypatch.setattr(voice, "_gtts_generate", gtts)
    assert voice.generate("Texto", "pt", tmp_path / "voz.mp3", narrator_gender="male") is False
    assert gtts.call_count == int(allowed)


def test_batch_valida_todas_as_partes_antes_de_gerar(monkeypatch, tmp_path):
    voice = VoiceGenerator(CONFIG)
    provider = Mock(return_value=True)
    monkeypatch.setattr(voice, "generate", provider)
    with pytest.raises(ValueError, match="male ou female"):
        voice.generate_batch([{"narrator_gender": "male"}, {}], "pt", tmp_path)
    provider.assert_not_called()


def test_config_incompleta_nao_escolhe_voz_de_outro_idioma():
    with pytest.raises(ValueError):
        VoiceGenerator(CONFIG)._select_voice("en", "male")
