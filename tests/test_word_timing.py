"""Regressões de temporização visível das legendas palavra a palavra."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stages import word_timing
from stages.word_timing import generate_ass


def _events(path):
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue: "):
            fields = line.split(",", 9)
            events.append((fields[1], fields[2], fields[9].split("}")[-1]))
    return events


def test_fast_adjacent_words_do_not_remain_superimposed(tmp_path):
    path = tmp_path / "fast.ass"
    assert generate_ass([
        {"word": "já", "start": 29.86, "duration": .10},
        {"word": "tinha", "start": 29.98, "duration": .40},
    ], path)
    assert _events(path) == [
        ("0:00:29.86", "0:00:29.98", "JÁ"),
        ("0:00:29.98", "0:00:30.38", "TINHA"),
    ]


@pytest.mark.parametrize(("start", "end"), [
    (59.999, "0:01:00.35"), (3599.999, "1:00:00.35"),
])
def test_ass_rounding_carries_centiseconds_across_second_boundary(tmp_path, start, end):
    path = tmp_path / "rollover.ass"
    assert generate_ass([{"word": "fim", "start": start, "duration": .10}], path)
    expected_start = "0:01:00.00" if start < 100 else "1:00:00.00"
    assert _events(path) == [(expected_start, end, "FIM")]


def test_hook_filter_and_pause_do_not_extend_word_through_silence(tmp_path):
    path = tmp_path / "pause.ass"
    assert generate_ass([
        {"word": "hook", "start": 0.0, "duration": 1.0},
        {"word": "corpo", "start": 2.0, "duration": .10},
        {"word": "fim", "start": 5.0, "duration": .10},
    ], path, skip_before=1.5)
    assert _events(path) == [
        ("0:00:02.00", "0:00:02.35", "CORPO"),
        ("0:00:05.00", "0:00:05.35", "FIM"),
    ]


def test_tempos_nativos_edge_sao_preservados_sem_estimar_ou_transcrever(monkeypatch, tmp_path):
    import edge_tts

    calls = []
    class Communicate:
        def __init__(self, text, voice, **kwargs):
            calls.append(kwargs)
        async def stream(self):
            for item in [
                {"type": "audio", "data": b"audio-de-teste"},
                {"type": "WordBoundary", "text": "Hello", "offset": 5000000, "duration": 3000000},
                {"type": "WordBoundary", "text": "world", "offset": 15000000, "duration": 6000000},
            ]:
                yield item
    monkeypatch.setattr(edge_tts, "Communicate", Communicate)
    no_whisper = Mock(side_effect=AssertionError("Não transcrever áudio com tempos nativos"))
    monkeypatch.setattr(word_timing, "extract_word_timestamps_whisper", no_whisper)
    path = tmp_path / "voice.mp3"
    # O tempo estimado anterior não pode sobreviver a uma nova geração.
    word_timing.save_word_boundaries([{"word": "antigo", "start": 99, "duration": 1}],
                                      path.with_name("voice_boundaries.json"))
    ok, words = word_timing.generate_audio_with_timestamps("Hello world", "en-US-AriaNeural", "+4%", path, "en")
    assert ok and path.read_bytes() == b"audio-de-teste"
    assert calls[0]["boundary"] == "WordBoundary"
    assert [(w["word"], w["start"], w["duration"]) for w in words] == [
        ("Hello", .5, .3), ("world", 1.5, .6),
    ]
    assert all(w["timing_source"] == "edge_tts" for w in words)
    no_whisper.assert_not_called()


def test_whisper_falha_cuda_ao_iterar_reinicia_transcricao_inteira_em_cpu(monkeypatch, tmp_path):
    import faster_whisper

    def gpu_segments():
        yield SimpleNamespace(words=[SimpleNamespace(word="parcial", start=0, end=.2)])
        raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
    gpu = SimpleNamespace(model=SimpleNamespace(device="cuda"), transcribe=Mock(return_value=(gpu_segments(), None)))
    cpu = SimpleNamespace(model=SimpleNamespace(device="cpu"), transcribe=Mock(return_value=(
        [SimpleNamespace(words=[SimpleNamespace(word="Hello", start=.5, end=.8)])], None)))
    constructor = Mock(return_value=cpu)
    monkeypatch.setattr(word_timing, "_whisper_model", gpu)
    monkeypatch.setattr(faster_whisper, "WhisperModel", constructor)
    words = word_timing.extract_word_timestamps_whisper(tmp_path / "voice.mp3", "en", "Hello")
    assert [w["word"] for w in words] == ["Hello"]
    assert words[0]["start"] == .5
    constructor.assert_called_once_with("small", device="cpu", compute_type="int8")
    assert word_timing._whisper_model is cpu
    cpu.transcribe.assert_called_once()


def test_sem_tempos_reais_nao_exporta_audio_com_legendas_estimadas(monkeypatch, tmp_path):
    monkeypatch.setattr(word_timing, "generate_edge_tts_audio", lambda *args: True)
    monkeypatch.setattr(word_timing, "extract_word_timestamps_whisper", lambda *args, **kwargs: [])
    estimated = Mock(side_effect=AssertionError("Não estimar sincronização após falha dos tempos reais"))
    monkeypatch.setattr(word_timing, "estimate_word_timestamps", estimated)
    assert word_timing.generate_audio_with_timestamps("Hello", "en-US-AriaNeural", "+4%", tmp_path / "voice.mp3", "en") == (False, [])
    estimated.assert_not_called()
