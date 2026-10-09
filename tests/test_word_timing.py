"""Regressões de temporização visível das legendas palavra a palavra."""
import pytest

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
