"""Resultados tipados e correções pontuais para a revisão de roteiro."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from stages.narrator_profile import NarratorProfile


Severity = Literal["info", "warning", "critical"]
Status = Literal["approved", "rejected", "unavailable"]

_SEVERITIES = {"info", "warning", "critical"}
REVIEW_CATEGORIES = (
    "narrator_gender", "factual", "amount", "relationship", "identity",
    "outcome", "negation", "event", "continuity", "attribution",
    "grammar", "style", "language", "omission", "terminology",
)


@dataclass(frozen=True)
class ReviewIssue:
    category: str
    severity: Severity
    message: str
    original: str = ""
    subject: str = ""
    source_quote: str = ""
    origin: str = "semantic"


@dataclass(frozen=True)
class TextPatch:
    original: str
    replacement: str
    category: str
    severity: Severity
    subject: str
    reason: str
    source_quote: str
    start: int | None = None


@dataclass(frozen=True)
class PatchResult:
    text: str
    applied: tuple[TextPatch, ...]
    rejected: tuple[TextPatch, ...]


@dataclass(frozen=True)
class ReviewOutcome:
    status: Status
    issues: tuple[ReviewIssue, ...]
    patches: tuple[TextPatch, ...]
    attempts: int
    raw: str = ""

    @property
    def approved(self) -> bool:
        return self.status == "approved"


@dataclass(frozen=True)
class ScriptReview:
    status: Status
    approved_text: str
    issues: tuple[ReviewIssue, ...]
    patches: tuple[TextPatch, ...]
    attempts: int
    changed: bool
    factual_context: str
    report_path: Path | None = None


class QualityGateError(RuntimeError):
    def __init__(self, review: ScriptReview):
        super().__init__(f"Gate de qualidade: {review.status}")
        self.review = review


class QualityRejected(QualityGateError):
    pass


class QualityUnavailable(QualityGateError):
    pass


def parse_semantic_review(raw: str | None) -> ReviewOutcome:
    """Converte a resposta sem inferir tipos nem aprovar achados críticos."""
    unavailable = ReviewOutcome("unavailable", (), (), 0, raw if isinstance(raw, str) else "")
    if not isinstance(raw, str) or not raw.strip():
        return unavailable
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return unavailable
    if (not isinstance(data, dict) or type(data.get("approved")) is not bool
            or not isinstance(data.get("issues"), list)):
        return unavailable

    issues = []
    patches = []
    fields = ("original", "replacement", "category", "severity", "subject", "reason", "source_quote")
    for item in data["issues"]:
        if (not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in fields)
                or item["category"] not in REVIEW_CATEGORIES or item["severity"] not in _SEVERITIES):
            return unavailable
        start = item.get("start")
        if start is not None and (type(start) is not int or start < 0):
            return unavailable
        issues.append(ReviewIssue(
            item["category"], item["severity"], item["reason"], item["original"],
            item["subject"], item["source_quote"],
        ))
        if item["original"] and item["replacement"]:
            patches.append(TextPatch(*(item[key] for key in fields), start=start))

    status = "rejected" if not data["approved"] or any(issue.severity == "critical" for issue in issues) else "approved"
    return ReviewOutcome(status, tuple(issues), tuple(patches), 1, raw)


def validate_and_apply_patches(
    text: str, patches: list[TextPatch], source_text: str, profile: NarratorProfile,
) -> PatchResult:
    """Aceita somente substituições exatas, sustentadas e sem sobreposição."""
    accepted: list[tuple[int, TextPatch]] = []
    rejected: list[TextPatch] = []
    for patch in patches:
        if (not isinstance(patch.original, str) or not patch.original
                or not isinstance(patch.replacement, str) or not patch.replacement
                or patch.original == patch.replacement
                or patch.category not in REVIEW_CATEGORIES or patch.severity not in _SEVERITIES
                or not isinstance(patch.subject, str) or not patch.subject
                or not isinstance(patch.reason, str) or not patch.reason
                or not isinstance(patch.source_quote, str)
                or (patch.category == "narrator_gender" and
                    (patch.subject != "narrator" or profile.narration_gender not in {"male", "female"}))
                or (patch.category not in {"grammar", "style", "language"} and
                    (not patch.source_quote or patch.source_quote not in source_text))):
            rejected.append(patch)
            continue

        if patch.start is None:
            start = text.find(patch.original)
            if start < 0 or text.find(patch.original, start + 1) >= 0:
                rejected.append(patch)
                continue
        elif type(patch.start) is int and patch.start >= 0:
            start = patch.start
        else:
            rejected.append(patch)
            continue

        end = start + len(patch.original)
        if (text[start:end] != patch.original or (start == 0 and end == len(text))
                or any(start < prior_start + len(prior.original) and end > prior_start
                       for prior_start, prior in accepted)):
            rejected.append(patch)
            continue
        accepted.append((start, patch))

    result = text
    for start, patch in sorted(accepted, key=lambda item: item[0], reverse=True):
        end = start + len(patch.original)
        updated = result[:start] + patch.replacement + result[end:]
        assert updated[:start] == result[:start]
        assert updated[start + len(patch.replacement):] == result[end:]
        result = updated
    return PatchResult(result, tuple(patch for _, patch in accepted), tuple(rejected))
