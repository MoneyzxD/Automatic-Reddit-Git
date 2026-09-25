# Narrator Profile and Script Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve one auditable narrator profile from the complete Reddit source, preserve it across PT/EN/ES and every part, and block publication when script fidelity, contextual terminology, grammar, or first-person gender remains critically wrong.

**Architecture:** Add two deep modules: `NarratorProfileResolver` owns evidence collection and the one-time gender decision; `ScriptGuardian` owns LanguageTool, contextual glossary, semantic review, verified patches, and the final quality gate. Existing stages remain adapters around those seams, and `main.py` only passes the locked profile and handles typed outcomes.

**Tech Stack:** Python 3.11 stdlib/dataclasses, existing Groq client, requests, PyYAML, pytest, LanguageTool 6.6 standalone, Java Temurin 17, GitHub Actions, systemd-compatible Oracle Linux deployment.

**Spec:** `docs/superpowers/specs/2026-09-25-narrator-script-quality-design.md`

## Global Constraints

- Keep the stack 100% free; do not introduce paid services.
- New code comments and log messages must be in Portuguese.
- Production behavior must work in GitHub Actions and be deployable on Oracle Cloud; do not depend on a developer-local Ollama process.
- Read the complete source. Do not use arbitrary `[:300]`, `[:400]`, `[:500]`, `[:3000]`, or `[:5000]` truncation as the source of truth.
- `narration_gender` must always be exactly `male` or `female` before naturalization, metadata, splitting, or TTS.
- Partner gender, sexual orientation, hair, name, profession, hobby, personality, clothing, and emotion have zero evidentiary weight.
- PT, EN, ES, all parts, metadata, and TTS must carry the same `profile_id` and `narration_gender`.
- Patches must be exact, surgical, non-overlapping, source-supported, and forbidden from changing another character based on the narrator profile.
- An unresolved critical issue or unavailable mandatory final review must prevent TTS/render/upload for that story or language.
- Pin LanguageTool to 6.6, Java to 17, and verify ZIP SHA-256 `53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631` on every runtime setup.
- LanguageTool must listen only on localhost; never fall back to its public API, a community Docker image, or `language_tool_python`.
- Keep Groq keys fixed per language workload through `utils.environment.groq_api_key`; do not rotate keys to bypass limits.
- Gemini is not a production dependency in this plan, and provider keys remain opaque strings without prefix validation.
- Never write OAuth tokens, cookies, API keys, complete provider responses containing secrets, or credentials to reports or logs.

## Review Focus

- Same-sex relationships and long hair: `I (28M) have long hair and live with my husband` must stay male, and `I (28F) live with my wife` must stay female.
- Late evidence: explicit narrator evidence after characters 3,000 and 5,000 must still control the profile and downstream voice.
- Unicode offsets: LanguageTool spans around accents and emoji must map to the correct Python substring before a patch is applied.
- Partial translation: one empty, unchanged-English, missing-placeholder, or wrong-language chunk must reject the whole target translation and its cache.
- Adversarial model output: invalid JSON, `approved=true` with blocking issues, fabricated quotes, duplicate spans, overlapping patches, and provider outages must never become silent approval.

## File Structure

### Create

- `utils/text_chunks.py` — lossless complete-text chunking with original offsets.
- `stages/narrator_profile.py` — immutable profile, evidence ledger, deterministic reducer, Groq evidence adapter, and sidecar persistence.
- `stages/language_tool.py` — local HTTP client, health/version/locale checks, UTF-16 offset conversion, and typed issues.
- `stages/contextual_glossary.py` — source protection/restoration and target terminology checks.
- `stages/script_guardian.py` — review types, surgical patch engine, fact ledger, semantic reviewer, checkpoints, JSONL reporting, and gate exceptions.
- `config/contextual_glossary.yaml` — versioned contextual terminology.
- `tests/fixtures/script_quality_cases.json` — reviewed regression corpus.
- `tests/test_text_chunks.py`
- `tests/test_narrator_profile.py`
- `tests/test_voice_gender.py`
- `tests/test_pipeline_narrator_profile.py`
- `tests/test_language_tool.py`
- `tests/test_contextual_glossary.py`
- `tests/test_translator_quality.py`
- `tests/test_script_guardian.py`
- `tests/test_full_context_stages.py`
- `tests/test_pipeline_quality_gate.py`
- `tests/test_languagetool_health.py`
- `tests/test_languagetool_deployment.py`
- `config/languagetool_runtime.env` — immutable LanguageTool runtime manifest.
- `scripts/check_languagetool.py` — shared readiness/version/locale/warmup command.
- `scripts/install_languagetool.sh` — idempotent Oracle/Linux installer with checksum verification.
- `deploy/languagetool/languagetool.service` — localhost-only systemd service template.

### Modify

- `main.py` — resolve once, pass profile, run checkpoints, quarantine rejected content, gate each part before TTS.
- `stages/gender_detector.py` — compatibility facade without stereotype signals or independent per-language decisions.
- `stages/voice.py` — require a locked gender and forbid cross-gender/uncontrolled fallbacks.
- `stages/adapter.py` — adapt all lossless chunks and prove source coverage.
- `stages/translator.py` — typed all-or-nothing translation, glossary placeholders, language/integrity validation, versioned cache metadata.
- `stages/validator.py` — unavailable/rejected states, no fail-open parsing or best-score publication, full context for title/hooks/metadata.
- `stages/titler.py` — consume guardian factual context instead of a 400-character prefix.
- `stages/metadata.py` — consume localized part text and factual context instead of a 300-character English prefix.
- `config/settings.yaml` — narrator and script-quality configuration; no local-only fallback in new paths.
- `.github/workflows/pipeline.yml` — install, verify, cache, start, warm, and stop LanguageTool.
- `tests/test_workflow_automation.py` — pin and readiness assertions.
- `requirements.txt` — document existing `requests` use; add no LanguageTool wrapper.
- `README.md`, `AGENTS.md`, `KNOWN_ISSUES.md`, `PROJECT_HANDOFF.md` — authoritative runtime and stage documentation.

---

### Task 1: Lossless full-text chunking and regression corpus

**Files:**
- Create: `utils/text_chunks.py`
- Create: `tests/test_text_chunks.py`
- Create: `tests/fixtures/script_quality_cases.json`

**Interfaces:**
- Produces: `TextChunk(index: int, start: int, end: int, text: str)`.
- Produces: `split_lossless(text: str, max_chars: int) -> list[TextChunk]`.
- Produces: `join_lossless(chunks: list[TextChunk]) -> str`.
- Invariant: chunks cover every source character exactly once and preserve offsets.

- [ ] **Step 1: Write failing chunk coverage tests**

```python
# tests/test_text_chunks.py
from utils.text_chunks import join_lossless, split_lossless


def test_chunks_preservam_cada_caractere_e_offsets():
    texto = "Inicio.\n\n" + ("paragrafo longo com acao. " * 40) + "I (44M) no fim."
    chunks = split_lossless(texto, max_chars=120)

    assert join_lossless(chunks) == texto
    assert "".join(c.text for c in chunks) == texto
    assert all(texto[c.start:c.end] == c.text for c in chunks)
    assert "I (44M)" in chunks[-1].text


def test_chunks_nao_quebram_unicode_nem_emoji():
    texto = "Joao disse: olá 👨‍👨‍👦. Depois, Pokémon apareceu."
    chunks = split_lossless(texto, max_chars=18)
    assert join_lossless(chunks) == texto
```

- [ ] **Step 2: Run the focused tests and confirm the missing module failure**

Run: `python -m pytest tests/test_text_chunks.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'utils.text_chunks'`.

- [ ] **Step 3: Implement the lossless chunk interface**

```python
# utils/text_chunks.py
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    start: int
    end: int
    text: str


def split_lossless(text: str, max_chars: int) -> list[TextChunk]:
    if max_chars < 32:
        raise ValueError("max_chars deve ser pelo menos 32")
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = hard_end
        if hard_end < len(text):
            candidates = (
                text.rfind("\n\n", start, hard_end),
                text.rfind(". ", start, hard_end),
                text.rfind(" ", start, hard_end),
            )
            split_at = max(candidates)
            if split_at > start:
                end = split_at + (2 if text[split_at:split_at + 2] in {"\n\n", ". "} else 1)
        chunks.append(TextChunk(len(chunks), start, end, text[start:end]))
        start = end
    return chunks


def join_lossless(chunks: list[TextChunk]) -> str:
    return "".join(chunk.text for chunk in chunks)
```

- [ ] **Step 4: Add the reviewed cross-language regression cases**

```json
[
  {"id":"gay_male_husband","source":"I (28M) have long hair and my husband loves it.","gender":"male"},
  {"id":"lesbian_female_wife","source":"I (28F) live with my wife.","gender":"female"},
  {"id":"late_marker","source_prefix_repetitions":260,"source_suffix":"I (44M) finally told them.","gender":"male"},
  {"id":"quoted_other_character","source":"My sister said, 'I'm a woman.' I (31M) disagreed.","gender":"male"},
  {"id":"pokemon_card_pt","source":"I traded a Pokemon card.","target":"Troquei uma carta Pokémon.","forbidden":["cartão Pokémon"]},
  {"id":"credit_card_pt","source":"I paid by credit card.","target":"Paguei com cartão de crédito.","forbidden":["carta de crédito"]}
]
```

- [ ] **Step 5: Run the focused tests**

Run: `python -m pytest tests/test_text_chunks.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the chunking foundation**

```bash
git add utils/text_chunks.py tests/test_text_chunks.py tests/fixtures/script_quality_cases.json
git commit -m "test: adiciona corpus integral de roteiros"
```

---

### Task 2: Immutable narrator profile and evidence ledger

**Files:**
- Create: `stages/narrator_profile.py`
- Create: `tests/test_narrator_profile.py`
- Modify: `stages/gender_detector.py`
- Modify: `config/settings.yaml`

**Interfaces:**
- Consumes: `split_lossless(text, max_chars)` from Task 1.
- Produces: immutable `NarratorEvidence` and `NarratorProfile` dataclasses.
- Produces: `NarratorProfileResolver.resolve(*, story_id, title, original_text) -> NarratorProfile`.
- Produces: `save_profile(profile, base_dir) -> Path` and `load_profile(story_id, base_dir, source_sha256, resolver_version) -> NarratorProfile | None`.
- Internal seam: injected semantic provider `Callable[[TextChunk], list[NarratorEvidence]]`; production adapter uses Groq, tests use fakes.
- Constructor option: `semantic_enabled: bool = True`; dry-run sets it to false so no provider call occurs while deterministic evidence/hash still returns a binary narration gender.

- [ ] **Step 1: Write failing deterministic decision tests**

```python
# tests/test_narrator_profile.py
import json

from stages.narrator_profile import NarratorProfileResolver


def resolver_sem_llm():
    return NarratorProfileResolver({"chunk_chars": 256}, semantic_provider=lambda chunk: [])


def test_marido_e_cabelo_nao_transformam_homem_em_mulher():
    perfil = resolver_sem_llm().resolve(
        story_id="gay-1",
        title="My family judged us",
        original_text="I (28M) have long hair and live with my husband.",
    )
    assert perfil.source_gender == "male"
    assert perfil.narration_gender == "male"


def test_esposa_nao_transforma_mulher_em_homem():
    perfil = resolver_sem_llm().resolve(
        story_id="lesbian-1", title="Our home", original_text="I (28F) live with my wife."
    )
    assert perfil.narration_gender == "female"


def test_evidencia_depois_de_cinco_mil_caracteres_e_lida():
    texto = ("No gender clue here. " * 300) + " I (44M) finally answered."
    perfil = resolver_sem_llm().resolve(story_id="late-1", title="Late clue", original_text=texto)
    assert perfil.narration_gender == "male"


def test_empate_sem_evidencia_e_estavel_e_binario():
    resolver = resolver_sem_llm()
    a = resolver.resolve(story_id="tie-1", title="Title", original_text="No useful clue.")
    b = resolver.resolve(story_id="tie-1", title="Title", original_text="No useful clue.")
    assert a.narration_gender in {"male", "female"}
    assert a.narration_gender == b.narration_gender
    assert a.profile_id == b.profile_id
    assert a.decision_method == "stable_tiebreak"
```

- [ ] **Step 2: Add failing semantic-evidence validation tests**

```python
from stages.narrator_profile import NarratorEvidence


def test_citacao_inventada_pelo_modelo_e_descartada():
    fake = lambda chunk: [NarratorEvidence(
        kind="semantic", quote="I am definitely a woman", start=-1,
        gender="female", weight=0.8, subject="narrator", origin="groq",
    )]
    resolver = NarratorProfileResolver({"chunk_chars": 128}, semantic_provider=fake)
    perfil = resolver.resolve(story_id="fake-quote", title="Title", original_text="Nothing says that.")
    assert perfil.decision_method == "stable_tiebreak"
    assert perfil.evidence == ()


def test_fala_de_outra_personagem_nao_e_evidencia_do_narrador():
    texto = "My sister said, 'I'm a woman.' I (31M) disagreed."
    perfil = resolver_sem_llm().resolve(story_id="quote-other", title="Title", original_text=texto)
    assert perfil.narration_gender == "male"
```

- [ ] **Step 3: Run the focused tests and verify failure**

Run: `python -m pytest tests/test_narrator_profile.py -q`

Expected: FAIL because `stages.narrator_profile` does not exist.

- [ ] **Step 4: Implement immutable models, explicit evidence, validated semantic evidence, and stable tie-break**

```python
# stages/narrator_profile.py (public shape)
@dataclass(frozen=True)
class NarratorEvidence:
    kind: str
    quote: str
    start: int
    gender: str
    weight: float
    subject: str
    origin: str


@dataclass(frozen=True)
class NarratorProfile:
    profile_id: str
    story_id: str
    source_gender: str
    narration_gender: str
    confidence: float
    decision_method: str
    evidence: tuple[NarratorEvidence, ...]
    source_sha256: str = ""
    resolver_version: str = "1"


def _stable_gender(story_id: str) -> str:
    digest = hashlib.sha256(story_id.encode("utf-8")).digest()
    return "female" if digest[0] & 1 else "male"
```

Implementation requirements:

- Scan title plus complete original text for narrator-bound `(28M)`, `(28F)`, `M28`, `F28`, and explicit first-person man/woman forms.
- Give no score to `husband`, `wife`, `boyfriend`, `girlfriend`, hair, names, jobs, hobbies, clothes, or emotions.
- Normalize semantic output to `male|female|unknown`, clamp confidence to `0..1`, require `subject == "narrator"`, and require the exact quote inside the same source chunk.
- Hash `resolver_version + story_id + title + complete_source_text` for `profile_id`, so provider variability cannot change the identity of the same source profile.
- Persist JSON atomically under `data/scripts/profiles/{story_id}_narrator_profile.json`; reject a sidecar whose source hash or resolver version differs.

- [ ] **Step 5: Add the production Groq evidence adapter without truncation**

Use `tracked_groq(env.groq_api_key("en"), "narrator_profile")`, one call per `TextChunk`, temperature `0`, strict JSON, and this response contract:

```json
{"evidence":[{"quote":"exact source text","gender":"male","confidence":0.94,"subject":"narrator","reason":"first-person self-identification"}]}
```

If the provider is missing, rate-limited, malformed, or returns invented text, record telemetry and continue through deterministic evidence or stable tie-break; do not call Ollama.

- [ ] **Step 6: Turn `GenderDetector` into a compatibility facade**

```python
class GenderDetector:
    def bind_profile(self, perfil: NarratorProfile) -> None:
        self._profile = perfil

    def detect(self, text: str = "", language: str = "en") -> dict:
        if self._profile is None:
            raise RuntimeError("Perfil do narrador ainda nao foi travado")
        perfil = self._profile
        return {
            "narrator_gender": perfil.narration_gender,
            "narrator_confidence": perfil.confidence,
            "corrections_needed": False,
            "profile_id": perfil.profile_id,
        }
```

Remove relationship/profession stereotype patterns from the compatibility path. The facade must never inspect `text` or initiate a provider call; production binds the profile created by `main.py`.

- [ ] **Step 7: Add narrator configuration**

```yaml
narrator_profile:
  enabled: true
  groq_model: openai/gpt-oss-20b
  chunk_chars: 6000
  confidence_threshold: 0.70
  resolver_version: "1"
```

- [ ] **Step 8: Run narrator tests and existing title tests**

Run: `python -m pytest tests/test_narrator_profile.py tests/test_titler.py -q`

Expected: PASS.

- [ ] **Step 9: Commit the profile module**

```bash
git add stages/narrator_profile.py stages/gender_detector.py config/settings.yaml tests/test_narrator_profile.py
git commit -m "feat: resolve perfil unico do narrador"
```

---

### Task 3: Lock profile through the pipeline and make TTS gender-safe

**Files:**
- Modify: `main.py:1-25,552-760,819-865,976-986`
- Modify: `stages/voice.py`
- Modify: `config/settings.yaml`
- Create: `tests/test_voice_gender.py`
- Create: `tests/test_pipeline_narrator_profile.py`

**Interfaces:**
- Consumes: `NarratorProfileResolver.resolve()` and `save_profile()` from Task 2.
- Produces: `VoiceGenerator.generate(text: str, language: str, output_path: Path, *, narrator_gender: Literal["male", "female"]) -> bool` with no gender default.
- Produces: `_select_voice(language, gender) -> tuple[str, str | None]`, where fallback is same-gender or absent.
- Produces: `resolve_story_narrator(resolver, story_id, title, source_text) -> NarratorProfile` and `attach_narrator_profile(payload, profile) -> dict` as pure orchestration helpers in `main.py`.
- Invariant: the resolver is called once per story, outside the language loop.

- [ ] **Step 1: Write failing voice safety tests**

```python
# tests/test_voice_gender.py
import pytest
from stages.voice import VoiceGenerator


CONFIG = {
    "voices": {
        "pt": {
            "female": {"primary": "pt-f-1", "fallback": "pt-f-2"},
            "male": {"primary": "pt-m-1", "fallback": "pt-m-2"},
        }
    }
}


def test_fallback_da_voz_preserva_genero():
    voice = VoiceGenerator(CONFIG)
    assert voice._select_voice("pt", "male") == ("pt-m-1", "pt-m-2")
    assert voice._select_voice("pt", "female") == ("pt-f-1", "pt-f-2")


@pytest.mark.parametrize("invalid", ["unknown", "", None])
def test_voz_rejeita_genero_nao_travado(invalid):
    voice = VoiceGenerator(CONFIG)
    with pytest.raises(ValueError, match="male ou female"):
        voice._select_voice("pt", invalid)
```

- [ ] **Step 2: Write the pipeline spy test for one resolution across three languages**

```python
# tests/test_pipeline_narrator_profile.py
from unittest.mock import Mock

from main import attach_narrator_profile, resolve_story_narrator
from stages.narrator_profile import NarratorProfile


def male_profile(story_id="test_001"):
    return NarratorProfile(
        profile_id="profile-123", story_id=story_id, source_gender="male",
        narration_gender="male", confidence=0.99, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def test_resolve_historia_uma_vez_e_propaga_mesmo_perfil():
    resolver = Mock()
    resolver.resolve.return_value = male_profile()
    profile = resolve_story_narrator(
        resolver, "test_001", "Title", "I (28M) live with my husband."
    )
    payloads = [attach_narrator_profile({"language": lang}, profile) for lang in ("pt", "en", "es")]

    resolver.resolve.assert_called_once_with(
        story_id="test_001", title="Title", original_text="I (28M) live with my husband."
    )
    assert {item["narrator_gender"] for item in payloads} == {"male"}
    assert {item["narrator_profile_id"] for item in payloads} == {"profile-123"}
```

- [ ] **Step 3: Run both new test files and confirm failures**

Run: `python -m pytest tests/test_voice_gender.py tests/test_pipeline_narrator_profile.py -q`

Expected: FAIL because voice schema/defaults and main flow are still unsafe.

- [ ] **Step 4: Migrate voice configuration to explicit gender buckets**

```yaml
voice:
  primary: edge-tts
  allow_uncontrolled_gender_fallback: false
  voices:
    pt:
      female: {primary: pt-BR-FranciscaNeural, fallback: null}
      male: {primary: pt-BR-AntonioNeural, fallback: null}
    en:
      female: {primary: en-US-AriaNeural, fallback: null}
      male: {primary: en-US-GuyNeural, fallback: null}
    es:
      female: {primary: es-MX-DaliaNeural, fallback: null}
      male: {primary: es-MX-JorgeNeural, fallback: null}
```

Do not invent unverified voice IDs. A missing same-gender fallback means the stage fails and the pipeline tries another story; it never switches gender. Keep gTTS disabled when `allow_uncontrolled_gender_fallback` is false because it cannot honor the locked voice identity.

- [ ] **Step 5: Resolve and persist the profile once before adaptation**

In `main.py`, immediately after `story_for_adapter["text"]` is built:

```python
profile_resolver = NarratorProfileResolver(
    config.get("narrator_profile", {}),
    semantic_enabled=not dry_run,
)
narrator_profile = profile_resolver.resolve(
    story_id=story_id,
    title=story_title,
    original_text=story_for_adapter["text"],
)
if not dry_run:
    save_profile(narrator_profile, BASE_DIR)
narrator_gender = narrator_profile.narration_gender
```

Implement that block through `resolve_story_narrator()` and enrich stage payloads only through `attach_narrator_profile()` so tests and callers share the invariant.

Delete the per-language detection block. Pass `narrator_gender` to every validator/naturalizer/title/metadata/voice call, including checkpoints that currently receive `unknown`. Attach `narrator_gender`, `narrator_profile_id`, confidence, and method to `adapted_for_split` before `split_story()`.

- [ ] **Step 6: Make voice arguments mandatory and remove cross-gender defaults**

Change `generate`, `_edge_tts_generate`, and `generate_batch` so omitted/invalid gender raises before provider calls. `_select_voice` reads only the selected gender bucket. When Edge TTS and its same-gender fallback fail, return `False`; call gTTS only when the explicit configuration flag is true.

- [ ] **Step 7: Update pipeline stage numbering and trace output**

Document profile resolution as stage 3.5 in `main.py` and include `profile_id`, method, and confidence in trace/metadata logs without storing provider secrets.

- [ ] **Step 8: Run focused and existing split/metadata-adjacent tests**

Run: `python -m pytest tests/test_voice_gender.py tests/test_pipeline_narrator_profile.py tests/test_generate_daily_batch.py tests/test_titler.py -q`

Expected: PASS.

- [ ] **Step 9: Commit locked narration and voice safety**

```bash
git add main.py stages/voice.py config/settings.yaml tests/test_voice_gender.py tests/test_pipeline_narrator_profile.py
git commit -m "fix: trava genero da narracao entre idiomas"
```

---

### Task 4: Local LanguageTool client with correct Unicode spans

**Files:**
- Create: `stages/language_tool.py`
- Create: `tests/test_language_tool.py`
- Modify: `config/settings.yaml`

**Interfaces:**
- Produces: `LanguageIssue(rule_id, category, message, replacements, start, end, original)`.
- Produces: `LanguageToolClient.check(text: str, language: str) -> tuple[LanguageIssue, ...]`.
- Produces: `LanguageToolClient.health(expected_version="6.6") -> HealthReport`.
- Raises: `LanguageToolUnavailable` for connection, HTTP, JSON, version, or required-locale failure when configured as required.
- Dependency seam: injected `requests.Session`; tests never call a real server.

- [ ] **Step 1: Write failing request and mapping tests**

```python
# tests/test_language_tool.py
from unittest.mock import Mock

import pytest

from stages.language_tool import LanguageToolClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def response_json(payload, status_code=200):
    return FakeResponse(payload, status_code)


@pytest.fixture
def session():
    return Mock()


def cliente(session, required=True):
    return LanguageToolClient({
        "languagetool_url": "http://127.0.0.1:8081/v2/check",
        "languagetool_timeout_seconds": 15,
        "languagetool_required": required,
        "languagetool_languages": {"pt": "pt-BR", "en": "en-US", "es": "es"},
    }, session=session)


def test_check_envia_locale_url_e_timeout(session):
    session.post.return_value = response_json({"matches": []})
    client = LanguageToolClient(
        {
            "languagetool_url": "http://127.0.0.1:8081/v2/check",
            "languagetool_timeout_seconds": 15,
            "languagetool_languages": {"pt": "pt-BR", "en": "en-US", "es": "es"},
        },
        session=session,
    )

    assert client.check("Eu estou bem.", "pt") == ()
    session.post.assert_called_once_with(
        "http://127.0.0.1:8081/v2/check",
        data={"text": "Eu estou bem.", "language": "pt-BR"},
        timeout=15.0,
    )
```

- [ ] **Step 2: Write failing UTF-16 offset and outage tests**

```python
def test_offset_utf16_aponta_para_trecho_python_com_emoji(session):
    texto = "Oi 👨‍👨‍👦, eu estava cansado."
    inicio_python = texto.index("cansado")
    inicio_utf16 = len(texto[:inicio_python].encode("utf-16-le")) // 2
    session.post.return_value = response_json({
        "matches": [{
            "offset": inicio_utf16,
            "length": len("cansado"),
            "message": "Concordancia",
            "replacements": [{"value": "cansada"}],
            "rule": {"id": "TEST_GENDER", "category": {"id": "GRAMMAR"}},
        }]
    })

    issue = cliente(session).check(texto, "pt")[0]
    assert (issue.start, issue.end, issue.original) == (
        inicio_python, inicio_python + len("cansado"), "cansado"
    )


def test_indisponibilidade_obrigatoria_nao_aprova(session):
    session.post.side_effect = OSError("connection refused")
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=True).check("Texto", "pt")
```

- [ ] **Step 3: Run focused tests and confirm the missing module failure**

Run: `python -m pytest tests/test_language_tool.py -q`

Expected: FAIL with missing module.

- [ ] **Step 4: Implement the HTTP adapter and UTF-16 conversion**

```python
@dataclass(frozen=True)
class LanguageIssue:
    rule_id: str
    category: str
    message: str
    replacements: tuple[str, ...]
    start: int
    end: int
    original: str


@dataclass(frozen=True)
class HealthReport:
    version: str
    locales: tuple[str, ...]


class LanguageToolUnavailable(RuntimeError):
    pass


def _utf16_index_to_python(text: str, utf16_index: int) -> int:
    if utf16_index < 0:
        raise ValueError("offset UTF-16 negativo")
    consumed = 0
    for index, char in enumerate(text):
        if consumed == utf16_index:
            return index
        consumed += len(char.encode("utf-16-le")) // 2
        if consumed > utf16_index:
            raise ValueError("offset UTF-16 caiu dentro de um caractere")
    if consumed == utf16_index:
        return len(text)
    raise ValueError("offset UTF-16 fora do texto")
```

The client must use `LANGUAGETOOL_URL` as an environment override, normalize `pt-br` to `pt`, reject unknown locales, call `raise_for_status()`, validate JSON shape, and never retry against an external host.

- [ ] **Step 5: Add script-quality configuration**

```yaml
script_quality:
  enabled: true
  fail_closed: true
  max_repair_attempts: 2
  languagetool_enabled: true
  languagetool_required: true
  languagetool_url: http://127.0.0.1:8081/v2/check
  languagetool_timeout_seconds: 15
  languagetool_languages:
    pt: pt-BR
    en: en-US
    es: es
```

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_language_tool.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the LanguageTool client**

```bash
git add stages/language_tool.py config/settings.yaml tests/test_language_tool.py
git commit -m "feat: adiciona cliente local do languagetool"
```

---

### Task 5: Contextual glossary and all-or-nothing translation

**Files:**
- Create: `stages/contextual_glossary.py`
- Create: `config/contextual_glossary.yaml`
- Create: `tests/test_contextual_glossary.py`
- Create: `tests/test_translator_quality.py`
- Modify: `stages/translator.py`

**Interfaces:**
- Produces: `ProtectedText(text: str, tokens: dict[str, str], glossary_version: str)`.
- Produces: `ContextualGlossary.prepare(source_text, source_lang, target_lang) -> ProtectedText`.
- Produces: `ContextualGlossary.restore(translated_text, protected) -> str`; missing/changed tokens raise `GlossaryIntegrityError`.
- Produces: `TranslationChunkResult` and `TranslationResult(status, text, provider, source_lang, target_lang, chunks, error)`.
- Produces: `ScriptTranslator.translate(text: str, source_lang: str, target_lang: str) -> TranslationResult` and `translate_all(script_text: str, story_id: str, scripts_dir: Path, languages: list[str], source_lang: str, force: bool = False) -> dict[str, str]`; the high-level method raises `TranslationFailed` instead of returning English for PT/ES.

- [ ] **Step 1: Write failing contextual terminology tests**

```python
# tests/test_contextual_glossary.py
from pathlib import Path

import pytest

from stages.contextual_glossary import ContextualGlossary


@pytest.fixture
def glossary():
    path = Path(__file__).parent.parent / "config" / "contextual_glossary.yaml"
    return ContextualGlossary.from_path(path)


@pytest.mark.parametrize(
    ("source", "target_lang", "expected"),
    [
        ("Pokemon card", "pt", "carta Pokémon"),
        ("trading card", "pt", "carta colecionável"),
        ("playing card", "pt", "carta de baralho"),
        ("credit card", "pt", "cartão de crédito"),
        ("birthday card", "pt", "cartão de aniversário"),
        ("business card", "pt", "cartão de visita"),
        ("Pokemon card", "es", "carta Pokémon"),
        ("credit card", "es", "tarjeta de crédito"),
    ],
)
def test_glossario_protege_e_restaura_conceito(source, target_lang, expected, glossary):
    protected = glossary.prepare(source, "en", target_lang)
    token = next(iter(protected.tokens))
    assert glossary.restore(protected.text, protected) == expected
    assert token not in expected
```

- [ ] **Step 2: Write failing translation integrity tests**

```python
# tests/test_translator_quality.py
from stages.translator import ScriptTranslator


def test_um_chunk_vazio_reprova_traducao_inteira(monkeypatch):
    translator = ScriptTranslator({"delay": 0})
    monkeypatch.setattr(translator, "_split_chunks", lambda text, chunk_size=None: ["one", "two"])
    monkeypatch.setattr(translator, "_translate_chunk_google", lambda chunk, *_: "um" if chunk == "one" else "")
    monkeypatch.setattr(translator, "_translate_chunk_mymemory", lambda *args: None)

    result = translator.translate("one two", "en", "pt")
    assert result.status == "rejected"
    assert result.text is None


def test_falha_nunca_devolve_ingles_como_portugues(monkeypatch):
    translator = ScriptTranslator({"delay": 0})
    monkeypatch.setattr(translator, "_translate_chunk_google", lambda *args: None)
    monkeypatch.setattr(translator, "_translate_chunk_mymemory", lambda *args: None)
    result = translator.translate("This stayed English.", "en", "pt")
    assert result.status == "unavailable"
    assert result.text is None


def test_placeholder_perdido_reprova_traducao(monkeypatch, glossary):
    translator = ScriptTranslator({}, glossary=glossary)
    monkeypatch.setattr(translator, "_translate_chunk_google", lambda *args: "Troquei alguma coisa")
    result = translator.translate("I traded a Pokemon card", "en", "pt")
    assert result.status == "rejected"
    assert "placeholder" in result.error.lower()
```

- [ ] **Step 3: Run both focused test files and confirm failures**

Run: `python -m pytest tests/test_contextual_glossary.py tests/test_translator_quality.py -q`

Expected: FAIL because the glossary and typed result do not exist.

- [ ] **Step 4: Add the versioned glossary data**

```yaml
version: "1"
concepts:
  pokemon_card:
    source_patterns: ["pokemon card", "pokémon card"]
    targets: {pt: "carta Pokémon", es: "carta Pokémon"}
    forbidden: {pt: ["cartão Pokémon"], es: ["tarjeta Pokémon"]}
  trading_card:
    source_patterns: ["trading card", "collectible card"]
    targets: {pt: "carta colecionável", es: "carta coleccionable"}
  playing_card:
    source_patterns: ["playing card"]
    targets: {pt: "carta de baralho", es: "carta"}
  credit_card:
    source_patterns: ["credit card"]
    targets: {pt: "cartão de crédito", es: "tarjeta de crédito"}
  debit_card:
    source_patterns: ["debit card"]
    targets: {pt: "cartão de débito", es: "tarjeta de débito"}
  birthday_card:
    source_patterns: ["birthday card"]
    targets: {pt: "cartão de aniversário", es: "tarjeta de cumpleaños"}
  greeting_card:
    source_patterns: ["greeting card"]
    targets: {pt: "cartão comemorativo", es: "tarjeta de felicitación"}
  business_card:
    source_patterns: ["business card"]
    targets: {pt: "cartão de visita", es: "tarjeta de presentación"}
```

Match longest source patterns first, use ASCII sentinel tokens such as `ZXQGLOSSARY000ZXQ`, and require every expected token exactly once after translation. Isolated ambiguous `card` becomes a blocking glossary issue; never apply a blind `card -> carta` replacement.

Implement the public value and error types before the loader:

```python
@dataclass(frozen=True)
class ProtectedText:
    text: str
    tokens: dict[str, str]
    glossary_version: str


class GlossaryIntegrityError(RuntimeError):
    pass
```

- [ ] **Step 5: Implement typed, per-chunk translation**

```python
@dataclass(frozen=True)
class TranslationChunkResult:
    index: int
    source_text: str
    translated_text: str | None
    provider: str | None
    status: Literal["approved", "rejected", "unavailable"]
    error: str = ""


@dataclass(frozen=True)
class TranslationResult:
    status: Literal["approved", "rejected", "unavailable"]
    text: str | None
    provider: str | None
    source_lang: str
    target_lang: str
    chunks: tuple[TranslationChunkResult, ...]
    error: str = ""


class TranslationFailed(RuntimeError):
    def __init__(self, result: TranslationResult):
        super().__init__(result.error)
        self.result = result
```

Translate each chunk through Google then MyMemory, but reject the whole result when any non-empty chunk is empty, unchanged for a different target, loses a glossary token, or fails the deterministic target-language sanity check. Do not save a target script until every chunk is approved.

- [ ] **Step 6: Version translation caches**

For each `script_{story_id}_{lang}.txt`, write `script_{story_id}_{lang}.cache.json` atomically with:

```json
{"source_sha256":"0000000000000000000000000000000000000000000000000000000000000000","source_lang":"en","target_lang":"pt","glossary_version":"1"}
```

Load the cached text only when all four fields match. A rejected/unavailable result must not create or refresh either cache file.

- [ ] **Step 7: Preserve title translation failure semantics**

Make `translate_title()` call the typed translator for a single chunk and raise `TranslationFailed` for PT/ES rather than silently returning the English title. `main.py` handles this like another per-language quality rejection.

- [ ] **Step 8: Run translation tests**

Run: `python -m pytest tests/test_contextual_glossary.py tests/test_translator_quality.py -q`

Expected: PASS.

- [ ] **Step 9: Commit glossary and translation integrity**

```bash
git add stages/contextual_glossary.py config/contextual_glossary.yaml stages/translator.py tests/test_contextual_glossary.py tests/test_translator_quality.py
git commit -m "fix: rejeita traducao parcial e ambigua"
```

---

### Task 6: Typed review outcomes and surgical patch engine

**Files:**
- Create: `stages/script_guardian.py`
- Create: `tests/test_script_guardian.py`

**Interfaces:**
- Produces: `ReviewIssue`, `TextPatch`, `ReviewOutcome`, `ScriptReview`, `QualityRejected`, and `QualityUnavailable`.
- Produces: `parse_semantic_review(raw: str | None) -> ReviewOutcome`.
- Produces: `validate_and_apply_patches(text, patches, source_text, profile) -> PatchResult`.
- Invariant: no whole-script rewrite and no implicit truthiness conversion such as `bool("false")`.

- [ ] **Step 1: Write failing parser-state tests**

```python
# tests/test_script_guardian.py
import json

import pytest

from stages.narrator_profile import NarratorProfile
from stages.script_guardian import TextPatch, parse_semantic_review, validate_and_apply_patches


@pytest.fixture
def perfil_feminino():
    return NarratorProfile(
        profile_id="pf", story_id="s1", source_gender="female",
        narration_gender="female", confidence=1.0, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


@pytest.fixture
def perfil_masculino():
    return NarratorProfile(
        profile_id="pm", story_id="s1", source_gender="male",
        narration_gender="male", confidence=1.0, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def patch_para(original, replacement="corrigido", subject="narrator"):
    return TextPatch(
        original=original, replacement=replacement, category="narrator_gender",
        severity="critical", subject=subject, reason="teste", source_quote="source",
    )


@pytest.mark.parametrize("raw", [None, "", "not json", "{truncated"])
def test_resposta_ausente_ou_invalida_e_unavailable(raw):
    outcome = parse_semantic_review(raw)
    assert outcome.status == "unavailable"
    assert not outcome.approved


def test_approved_true_com_issue_critico_e_rejected():
    raw = json.dumps({
        "approved": True,
        "issues": [{
            "original": "agora sou faxineiro",
            "replacement": "agora sou faxineira",
            "category": "narrator_gender",
            "severity": "critical",
            "subject": "narrator",
            "reason": "incompatível com o perfil",
            "source_quote": "I am a cleaner",
        }],
    })
    assert parse_semantic_review(raw).status == "rejected"


def test_string_false_nao_vira_booleano_true():
    raw = '{"approved":"false","issues":[]}'
    assert parse_semantic_review(raw).status == "unavailable"
```

- [ ] **Step 2: Write failing patch safety tests**

```python
def test_patch_muda_apenas_ocorrencia_unica(perfil_feminino):
    text = "Depois disso, agora sou faxineiro e sigo trabalhando."
    patch = TextPatch(
        original="agora sou faxineiro", replacement="agora sou faxineira",
        category="narrator_gender", severity="critical", subject="narrator",
        reason="concordancia", source_quote="I now work as a cleaner",
    )
    result = validate_and_apply_patches(text, [patch], "I now work as a cleaner", perfil_feminino)
    assert result.text == "Depois disso, agora sou faxineira e sigo trabalhando."
    assert result.applied == (patch,)


@pytest.mark.parametrize("candidate", [
    "trecho inexistente",
    "repetido repetido",
])
def test_patch_ausente_ou_ambiguo_e_rejeitado(candidate, perfil_feminino):
    patch = patch_para("repetido" if "repetido" in candidate else "nao existe")
    result = validate_and_apply_patches(candidate, [patch], "source", perfil_feminino)
    assert result.rejected == (patch,)


def test_patch_de_genero_de_outro_personagem_e_rejeitado(perfil_feminino):
    patch = patch_para("meu irmão estava cansado", "meu irmão estava cansada", subject="brother")
    result = validate_and_apply_patches("meu irmão estava cansado", [patch], "source", perfil_feminino)
    assert result.rejected == (patch,)
```

- [ ] **Step 3: Run focused tests and confirm failures**

Run: `python -m pytest tests/test_script_guardian.py -q`

Expected: FAIL because types and functions do not exist.

- [ ] **Step 4: Implement strict review models and parser**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ReviewIssue:
    category: str
    severity: Literal["info", "warning", "critical"]
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
    severity: Literal["info", "warning", "critical"]
    subject: str
    reason: str
    source_quote: str
    start: int | None = None


@dataclass(frozen=True)
class ReviewOutcome:
    status: Literal["approved", "rejected", "unavailable"]
    issues: tuple[ReviewIssue, ...]
    patches: tuple[TextPatch, ...]
    attempts: int
    raw: str = ""

    @property
    def approved(self) -> bool:
        return self.status == "approved"


@dataclass(frozen=True)
class ScriptReview:
    status: Literal["approved", "rejected", "unavailable"]
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
```

Parse only literal JSON booleans, required string fields, known severity values, and list objects. Normalize any blocking issue to `rejected` regardless of the model's top-level `approved` value.

- [ ] **Step 5: Implement exact patch validation and reverse-offset application**

Rules:

- `original` and `replacement` must be non-empty and different.
- `source_quote` must exist literally in the full source for factual/gender patches.
- Without `start`, `original` must occur exactly once.
- With `start`, `text[start:start + len(original)]` must match exactly.
- Spans must not overlap.
- `category == narrator_gender` requires `subject == narrator`.
- Apply accepted patches by descending start offset and prove untouched prefixes/suffixes remain byte-for-byte equal.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_script_guardian.py -q`

Expected: PASS for parser and patch sections.

- [ ] **Step 7: Commit typed outcomes and patch safety**

```bash
git add stages/script_guardian.py tests/test_script_guardian.py
git commit -m "feat: aplica correcoes cirurgicas verificadas"
```

---

### Task 7: Full-context ScriptGuardian orchestration and fact ledger

**Files:**
- Modify: `stages/script_guardian.py`
- Modify: `tests/test_script_guardian.py`
- Modify: `utils/telemetry.py`

**Interfaces:**
- Consumes: `LanguageToolClient`, `ContextualGlossary`, `NarratorProfile`, `split_lossless`, and patch engine.
- Produces: `ScriptGuardian.review_and_fix(*, source_text, candidate_text, language, stage, story_id, profile, final_gate=False) -> ScriptReview`.
- `ScriptReview` produces: `approved_text`, `status`, `issues`, `patches`, `changed`, `factual_context`, and `report_path`.
- Internal seam: injected semantic reviewer returning the Task 6 JSON contract.

- [ ] **Step 1: Add failing orchestration tests with fake adapters**

```python
from types import SimpleNamespace

from stages.language_tool import LanguageIssue
from stages.script_guardian import QualityUnavailable, ScriptGuardian


class FakeLanguageTool:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = 0

    def check(self, text, language):
        index = min(self.calls, max(0, len(self.responses) - 1))
        self.calls += 1
        return self.responses[index] if self.responses else ()

    def health(self, expected_version="6.6"):
        return SimpleNamespace(version=expected_version, locales=("pt-BR", "en-US", "es"))


class FakeGlossary:
    version = "1"
    def findings(self, source_text, candidate_text, language):
        return ()


class FakeSemanticReviewer:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def review(self, **kwargs):
        self.calls.append(SimpleNamespace(**kwargs))
        return self.responses.pop(0) if self.responses else json.dumps({"approved": True, "issues": []})


class UnavailableReviewer:
    def review(self, **kwargs):
        return None


def issue_lt(original, replacement, category):
    return (LanguageIssue(
        rule_id="TEST", category=category, message="teste",
        replacements=(replacement,), start=0, end=len(original), original=original,
    ),)


def response_patch(original, replacement, category):
    return json.dumps({"approved": False, "issues": [{
        "original": original, "replacement": replacement, "category": category,
        "severity": "critical", "subject": "narrator", "reason": "concordancia",
        "source_quote": "I now work as a cleaner",
    }]})


def guardian_fake(tmp_path, lt=None, semantic=None):
    return ScriptGuardian(
        {"fail_closed": True, "max_repair_attempts": 2}, base_dir=tmp_path,
        languagetool=lt or FakeLanguageTool(), glossary=FakeGlossary(),
        semantic_reviewer=semantic or FakeSemanticReviewer([json.dumps({"approved": True, "issues": []})]),
    )


def test_guardiao_roda_glossario_languagetool_semantica_e_recheck(tmp_path, perfil_feminino):
    lt = FakeLanguageTool([
        issue_lt("faxineiro", "faxineira", category="GRAMMAR"),
        (),
    ])
    semantic = FakeSemanticReviewer([
        response_patch("agora sou faxineiro", "agora sou faxineira", "narrator_gender")
    ])
    guardian = guardian_fake(tmp_path, lt=lt, semantic=semantic)

    review = guardian.review_and_fix(
        source_text="I now work as a cleaner.",
        candidate_text="Agora sou faxineiro.",
        language="pt",
        stage="pre_tts",
        story_id="s1",
        profile=perfil_feminino,
        final_gate=True,
    )

    assert review.status == "approved"
    assert review.approved_text == "Agora sou faxineira."
    assert lt.calls == 2


def test_gate_final_indisponivel_levanta_erro(tmp_path, perfil_feminino):
    guardian = guardian_fake(tmp_path, semantic=UnavailableReviewer())
    with pytest.raises(QualityUnavailable):
        guardian.review_and_fix(
            source_text="source", candidate_text="candidate", language="pt",
            stage="pre_tts", story_id="s1", profile=perfil_feminino, final_gate=True,
        )
```

- [ ] **Step 2: Add failing complete-context/fact tests**

```python
def test_fato_no_fim_da_fonte_chega_ao_revisor(tmp_path, perfil_masculino):
    source = ("Earlier context. " * 500) + "The surgery never existed."
    semantic = FakeSemanticReviewer([json.dumps({"approved": True, "issues": []})] * 20)
    guardian = guardian_fake(tmp_path, semantic=semantic)
    guardian.review_and_fix(
        source_text=source,
        candidate_text="A cirurgia foi cancelada.",
        language="pt", stage="translation", story_id="late-fact",
        profile=perfil_masculino,
    )
    assert any("The surgery never existed" in getattr(call, "source_chunk", "") for call in semantic.calls)
```

- [ ] **Step 3: Run the guardian tests and confirm orchestration failures**

Run: `python -m pytest tests/test_script_guardian.py -q`

Expected: FAIL because `ScriptGuardian` orchestration is incomplete.

- [ ] **Step 4: Implement validated fact ledger and semantic chunk review**

For each source chunk, collect only facts with exact `source_quote`:

```json
{"facts":[{"kind":"relationship|amount|event|outcome|identity","value":"compact fact","source_quote":"exact source text"}]}
```

Deduplicate facts and build a bounded factual context from validated facts, not a raw prefix. Review every candidate chunk plus the relevant source chunks and the global fact ledger. A final global pass checks omissions, contradictions, language, contextual terms, narrator identity, first-person agreement, relationships, amounts, negation, and outcome.

- [ ] **Step 5: Implement checkpoint order and repair loop**

Inside `review_and_fix`:

1. validate non-empty language/profile/text;
2. collect contextual-glossary issues;
3. call LanguageTool;
4. call the semantic reviewer with strict JSON;
5. apply only verified patches;
6. rerun glossary and LanguageTool;
7. permit at most `max_repair_attempts`;
8. raise `QualityRejected` for unresolved critical issues;
9. raise `QualityUnavailable` when a required dependency cannot complete a mandatory review;
10. return warnings without blocking when all remaining issues are stylistic.

- [ ] **Step 6: Write append-only structured reports**

Append one JSON object per attempt to `data/logs/script_quality.jsonl` with story/profile/language/stage/part, profile decision, tool versions, latency, accepted/rejected patch summaries, issue counts, and final status. Redact values whose keys contain `token`, `secret`, `cookie`, `authorization`, or `api_key`.

- [ ] **Step 7: Use the existing fixed per-language Groq key**

The default semantic adapter uses `env.groq_api_key(language)` and `tracked_groq(groq_key, "script_guardian")`, temperature `0`, bounded retries, and no Ollama fallback. Never accept prose outside the strict JSON object.

- [ ] **Step 8: Run guardian and telemetry tests**

Run: `python -m pytest tests/test_script_guardian.py -q`

Expected: PASS.

- [ ] **Step 9: Commit the guard orchestration**

```bash
git add stages/script_guardian.py utils/telemetry.py tests/test_script_guardian.py
git commit -m "feat: adiciona guardiao integral de roteiro"
```

---

### Task 8: Remove truncated/fail-open behavior from existing text stages

**Files:**
- Modify: `stages/adapter.py`
- Modify: `stages/validator.py`
- Modify: `stages/titler.py`
- Modify: `stages/metadata.py`
- Create: `tests/test_full_context_stages.py`
- Modify: `tests/test_titler.py`

**Interfaces:**
- Consumes: `split_lossless` and `ScriptReview.factual_context`.
- Produces: `StoryAdapter.adapt()` whose output covers every input chunk.
- Produces: title/hook/closing-hook methods with optional `factual_context: str` and no arbitrary raw prefix.
- Produces: `MetadataGenerator.generate(story: dict, language: str, part_number: int, total_parts: int, hook: str, narrator_gender: str, localized_script: str, factual_context: str) -> dict`.
- Legacy `ValidatorEngine` returns an explicit unavailable/rejected result and never silently publishes a best score.

- [ ] **Step 1: Write failing late-context tests**

```python
# tests/test_full_context_stages.py
import pytest

from stages.adapter import StoryAdapter
from stages.script_guardian import QualityRejected
from stages.titler import TitleGenerator
from stages.validator import Issue, ValidationResult, ValidatorEngine


def capturar_prompts(monkeypatch, generator):
    prompts = []
    monkeypatch.setattr(
        generator,
        "_groq_title",
        lambda original_title, context, language, hook_type: prompts.append(context) or "Titulo valido",
    )
    return prompts


def rejected_result():
    return ValidationResult(
        status="rejected", approved=False, score=10,
        issues=[Issue("texto", "problema", "correcao", "coerencia")], raw="{}",
    )


def test_adapter_envia_todos_os_chunks_ao_provedor(monkeypatch):
    story = {"id": "long", "title": "Title", "text": ("context. " * 900) + "LATE FACT"}
    seen = []
    adapter = StoryAdapter({"llm_enabled": True, "chunk_chars": 1000})
    monkeypatch.setattr(adapter, "_adapt_chunk_via_groq", lambda chunk, index, total: seen.append(chunk) or chunk)
    result = adapter.adapt(story)
    assert "".join(seen) == story["text"]
    assert "LATE FACT" in result["full_script"]


def test_titler_recebe_contexto_factual_do_fim(monkeypatch):
    generator = TitleGenerator({})
    prompts = capturar_prompts(monkeypatch, generator)
    generator.generate(
        story_text="localized story",
        language="pt",
        original_title="title",
        factual_context="A cirurgia nunca existiu; citação validada no fim.",
    )
    assert "cirurgia nunca existiu" in prompts[-1]
```

- [ ] **Step 2: Write failing validator state tests**

```python
def test_validator_sem_resposta_nao_aprova(tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    result = validator._parse_validation_json(None)
    assert result.status == "unavailable"
    assert not result.approved


def test_validator_nao_publica_melhor_score_reprovado(monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    monkeypatch.setattr(validator, "validate_script", lambda *args, **kwargs: rejected_result())
    with pytest.raises(QualityRejected):
        validator.validate_and_fix_script("texto", "pt", "female", "story")
```

- [ ] **Step 3: Run focused tests and confirm current truncation/fail-open failures**

Run: `python -m pytest tests/test_full_context_stages.py tests/test_titler.py -q`

Expected: FAIL against current 5,000/400/300/500-character and fail-open behavior.

- [ ] **Step 4: Adapt every lossless chunk and prove coverage**

Change the Groq adapter to process `split_lossless(full_text, chunk_chars)`. Each prompt contains chunk index/total and forbids adding an introduction, conclusion, or facts. Join outputs in source order. Reject a missing result; the deterministic cleaner may process the complete original only when the configured LLM path is unavailable. Use `env.groq_api_key("en")` before the generic key.

- [ ] **Step 5: Make legacy validator parsing fail closed**

Change the type to:

```python
@dataclass
class ValidationResult:
    status: Literal["approved", "rejected", "unavailable"]
    approved: bool
    score: int
    issues: list[Issue] = field(default_factory=list)
    raw: str = ""
```

`None`, malformed JSON without recoverable issues, invalid booleans, and provider errors become `unavailable`. Blocking issues override `approved=true`. Exhausting retries raises `QualityRejected`/`QualityUnavailable`; remove selection of the stochastic highest score.

`main.py` will stop using `ValidatorEngine` for scripts in Task 9, but this hardening protects remaining callers and tests from the old silent behavior.

- [ ] **Step 6: Replace raw prefixes with validated factual context**

Add `factual_context=""` to title, opening-hook, closing-hook, and metadata generation. When provided, use it in the prompt verbatim; do not also send a raw `story_text[:N]`. For metadata, use the localized `part_script`, not `story["text"]` in English. Keep existing defaults only for backward-compatible unit callers.

- [ ] **Step 7: Validate all generated public text through the guardian contract**

Prepare the methods so Task 9 can send title, opening hook, closing hook, description, and localized part text to `ScriptGuardian` with stages `title`, `opening_hook`, `closing_hook`, and `metadata`. Hashtags remain deterministic data and must not be rewritten as prose.

- [ ] **Step 8: Run focused tests**

Run: `python -m pytest tests/test_full_context_stages.py tests/test_titler.py -q`

Expected: PASS.

- [ ] **Step 9: Commit full-context stage hardening**

```bash
git add stages/adapter.py stages/validator.py stages/titler.py stages/metadata.py tests/test_full_context_stages.py tests/test_titler.py
git commit -m "fix: remove cortes e aprovacao silenciosa"
```

---

### Task 9: Integrate every quality checkpoint and quarantine failures

**Files:**
- Modify: `main.py`
- Modify: `scheduler/notifier.py`
- Create: `tests/test_pipeline_quality_gate.py`

**Interfaces:**
- Consumes: locked `NarratorProfile`, checked translations, `ScriptGuardian`, and typed gate exceptions.
- Produces: `quarantine_review(base_dir, review, candidate_text) -> Path` under `data/quarantine/{story_id}/`.
- Produces: `review_and_generate_audio(*, guardian, voice_generator, source_text: str, part_script: str, language: str, story_id: str, profile: NarratorProfile, part_number: int, audio_path: Path) -> tuple[str, bool]`; this is the only `main.py` helper allowed to call `VoiceGenerator.generate`.
- Produces: `cli(argv: list[str] | None = None) -> int`; `__main__` raises `SystemExit(cli())`.
- Error contract: content rejection skips that story/language and lets the daily batch seek another story; mandatory dependency outage exits non-zero and stops the job.

- [ ] **Step 1: Write failing no-TTS-on-rejection integration test**

```python
# tests/test_pipeline_quality_gate.py
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from main import cli, review_and_generate_audio
from stages.narrator_profile import NarratorProfile
from stages.script_guardian import QualityRejected, QualityUnavailable


def locked_profile():
    return NarratorProfile(
        profile_id="p1", story_id="s1", source_gender="female",
        narration_gender="female", confidence=1.0, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def test_gate_final_reprovado_nao_chama_voz(tmp_path):
    guardian = Mock()
    voice = Mock()
    guardian.review_and_fix.side_effect = QualityRejected(SimpleNamespace(status="rejected"))

    with pytest.raises(QualityRejected):
        review_and_generate_audio(
            guardian=guardian, voice_generator=voice, source_text="source",
            part_script="hook + story + closing", language="pt", story_id="s1",
            profile=locked_profile(), part_number=1, audio_path=tmp_path / "audio.mp3",
        )

    voice.generate.assert_not_called()
```

- [ ] **Step 2: Write failing checkpoint/order and dependency-outage tests**

```python
def test_gate_recebe_parte_com_hook_e_encerramento(tmp_path):
    guardian = Mock()
    voice = Mock()
    approved = "HOOK. Corpo. ENCERRAMENTO."
    guardian.review_and_fix.return_value = SimpleNamespace(approved_text=approved, status="approved")
    voice.generate.return_value = True

    text, ok = review_and_generate_audio(
        guardian=guardian, voice_generator=voice, source_text="source",
        part_script=approved, language="pt", story_id="s1",
        profile=locked_profile(), part_number=1, audio_path=tmp_path / "audio.mp3",
    )

    assert (text, ok) == (approved, True)
    assert guardian.review_and_fix.call_args.kwargs["candidate_text"] == approved
    voice.generate.assert_called_once_with(
        approved, "pt", tmp_path / "audio.mp3", narrator_gender="female"
    )


def test_dependencia_obrigatoria_indisponivel_retorna_codigo_nao_zero(monkeypatch):
    monkeypatch.setattr("main.run_pipeline", Mock(side_effect=QualityUnavailable(SimpleNamespace(status="unavailable"))))
    assert cli(["--test-story", "--lang", "pt"]) == 2
```

- [ ] **Step 3: Run the integration test and verify failure**

Run: `python -m pytest tests/test_pipeline_quality_gate.py -q`

Expected: FAIL because the guardian is not orchestrated by `main.py`.

- [ ] **Step 4: Assert mandatory dependencies before extraction**

Instantiate `ScriptGuardian(config["script_quality"], base_dir=BASE_DIR)` and call `assert_ready()` before Reddit extraction. A `QualityUnavailable` escapes to the CLI boundary and returns exit code `2`, making `generate_daily_batch.py` fail the workflow instead of publishing without review.

- [ ] **Step 5: Replace script validator checkpoints with guardian checkpoints**

Run `review_and_fix` after:

- EN adaptation, compared with complete expanded Reddit source;
- each target translation, compared with approved EN;
- naturalization, compared with approved target translation;
- title, opening hook, and closing hook, compared with factual context;
- injected hook;
- each split part;
- immediately before TTS with `final_gate=True`;
- localized metadata description before save/upload.

Always use `review.approved_text` downstream. Remove `translated_scripts.get(lang, clean_script)` and consume only successful checked translations.

Implement `review_and_generate_audio()` exactly in that order: final review, extract `approved_text`, then call `voice_generator.generate`. All thumbnail/video/organizer/queue code remains after this helper returns successfully, so an exception cannot reach those stages.

- [ ] **Step 6: Distinguish rejected content from unavailable infrastructure**

At EN-base rejection, quarantine and finish the story with success exit status so the batch can select another Reddit story. At per-language rejection, quarantine and `continue` that language. On `QualityUnavailable`, notify and re-raise so the process exits non-zero. Do not catch unrelated exceptions as quality rejection.

- [ ] **Step 7: Persist safe quarantine reports**

Write candidate text plus the structured review to `data/quarantine/{story_id}/{language}_{stage}[_partN].json` atomically. Include profile ID and source hashes; redact secrets using the same policy as the JSONL log. Never enqueue or organize quarantined content.

- [ ] **Step 8: Move metadata validation before expensive rendering**

Build metadata from localized `part_script` and `factual_context` before TTS. Validate its description through the guardian. Only after title/hooks/script/metadata are approved may the part enter voice, subtitles, thumbnail, video, organizer, and queues.

- [ ] **Step 9: Add Telegram quality summaries**

For rejection, send story title, language, stage, part, profile method/confidence, issue categories, and quarantine path. For unavailable dependencies, identify the dependency without including URLs containing secrets or raw provider responses.

- [ ] **Step 10: Run the focused integration tests**

Run: `python -m pytest tests/test_pipeline_quality_gate.py tests/test_pipeline_narrator_profile.py tests/test_generate_daily_batch.py -q`

Expected: PASS.

- [ ] **Step 11: Commit pipeline gate integration**

```bash
git add main.py scheduler/notifier.py tests/test_pipeline_quality_gate.py
git commit -m "feat: bloqueia roteiro ruim antes da voz"
```

---

### Task 10: Reproducible LanguageTool runtime in GitHub Actions and Oracle

**Files:**
- Create: `config/languagetool_runtime.env`
- Create: `scripts/check_languagetool.py`
- Create: `scripts/install_languagetool.sh`
- Create: `deploy/languagetool/languagetool.service`
- Create: `tests/test_languagetool_health.py`
- Create: `tests/test_languagetool_deployment.py`
- Modify: `.github/workflows/pipeline.yml`
- Modify: `tests/test_workflow_automation.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces CLI: `python scripts/check_languagetool.py --url URL --expected-version 6.6 --required-locales pt-BR en-US es --timeout-seconds 120`.
- Produces: idempotent root installer for Debian/Ubuntu and Oracle Linux/RHEL.
- GitHub runtime: `actions/setup-java@v6`, immutable archive cache, SHA verification on cache hit and miss, background server step, real endpoint warmup, guaranteed cancel step.

- [ ] **Step 1: Write failing health-check tests with a fake transport**

```python
# tests/test_languagetool_health.py
from scripts.check_languagetool import wait_until_ready


class FakeRequester:
    def __init__(self, languages, checks):
        self.languages = languages
        self.checks = checks
        self.warmed = []

    def get_json(self, url, timeout):
        assert url.endswith("/v2/languages")
        return self.languages

    def post_form_json(self, url, data, timeout):
        assert url.endswith("/v2/check")
        self.warmed.append(data["language"])
        return self.checks[data["language"]]


def test_health_confirma_versao_locales_e_aquece_tres_idiomas():
    requester = FakeRequester(
        languages=[{"code": "pt", "longCode": "pt-BR"}, {"code": "en", "longCode": "en-US"}, {"code": "es", "longCode": "es"}],
        checks={locale: {"software": {"version": "6.6"}, "matches": []} for locale in ("pt-BR", "en-US", "es")},
    )
    report = wait_until_ready(
        base_url="http://127.0.0.1:8081", expected_version="6.6",
        required_locales=("pt-BR", "en-US", "es"), timeout_seconds=1,
        requester=requester,
    )
    assert report.version == "6.6"
    assert requester.warmed == ["pt-BR", "en-US", "es"]
```

Add tests for URL already ending in `/v2`, wrong version, missing locale, transient connection refusal, invalid JSON, and timeout.

- [ ] **Step 2: Implement the stdlib readiness CLI and runtime manifest**

```dotenv
LANGUAGETOOL_VERSION=6.6
LANGUAGETOOL_ARCHIVE=LanguageTool-6.6.zip
LANGUAGETOOL_DIRECTORY=LanguageTool-6.6
LANGUAGETOOL_DOWNLOAD_URL=https://languagetool.org/download/LanguageTool-6.6.zip
LANGUAGETOOL_SHA256=53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631
```

Use `urllib.request` in the readiness script so it can run before `pip install`. Poll `/v2/languages`, then POST a real sentence to `/v2/check` for each locale. Retry only connection/HTTP transient failures until the deadline; wrong version, malformed JSON, or missing locale fails immediately.

- [ ] **Step 3: Add failing static workflow tests**

```python
def test_workflow_sobe_languagetool_pinado_antes_dos_testes():
    workflow = workflow_text()
    assert "actions/setup-java@v6" in workflow
    assert 'java-version: "17"' in workflow
    assert "LanguageTool-6.6.zip" in workflow
    assert "53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631" in workflow
    assert "sha256sum --check --strict" in workflow
    assert "background: true" in workflow
    assert "cancel: languagetool_server" in workflow
    assert workflow.index("check_languagetool.py") < workflow.index("python -m pytest")
```

- [ ] **Step 4: Add Java, immutable cache, checksum, and background server to the workflow**

Use:

```yaml
- name: Configurar Java 17
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"

- name: Restaurar pacote do LanguageTool
  uses: actions/cache@v4
  with:
    path: .cache/languagetool
    key: languagetool-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('config/languagetool_runtime.env') }}
```

Download the ZIP only when absent, but always run `sha256sum --check --strict`. Extract to `$RUNNER_TEMP/LanguageTool-6.6`. Start `languagetool-server.jar` with `background: true`, `id: languagetool_server`, Java heap bounds, port `8081`, and no `--public`/`--allow-origin`. Run the shared health/warmup CLI before pytest. End the job with a `cancel: languagetool_server` step.

- [ ] **Step 5: Export runtime environment to generation**

Set `LANGUAGETOOL_URL=http://127.0.0.1:8081/v2/check` and `LANGUAGETOOL_REQUIRED=true` for tests and generation. On health failure, print only `data/logs/languagetool.log`, then fail the job.

- [ ] **Step 6: Write failing static Oracle deployment tests**

Assert that the installer loads the runtime manifest, verifies SHA before extraction, creates a no-login `languagetool` user, installs under `/opt/languagetool/LanguageTool-6.6`, updates `/opt/languagetool/current` with `ln -sfn`, installs Temurin 17 for supported distro families, renders the service, enables/restarts it, and calls the shared health check. Assert the service has `User=languagetool`, `Group=languagetool`, `Restart=on-failure`, localhost network restrictions, and no `--public`.

- [ ] **Step 7: Implement the idempotent Oracle/Linux installer and systemd service**

The installer requires root, detects `apt` or `dnf`, installs Java 17/curl/unzip, verifies `java -version`, reuses only a checksum-valid cached ZIP, extracts to a versioned directory, creates the service user, installs the unit, and runs `systemctl daemon-reload`, `enable`, `restart`, then the health command. The unit uses `ProtectSystem=strict`, `PrivateTmp=true`, `NoNewPrivileges=true`, `IPAddressDeny=any`, `IPAddressAllow=localhost`, and binds no public interface.

- [ ] **Step 8: Update the requirements comment without adding a wrapper**

Change the `requests` comment to `cliente HTTP: Reddit autenticado e LanguageTool local`. Do not add `language_tool_python`, Docker, or a public API dependency.

- [ ] **Step 9: Run runtime and workflow tests**

Run:

```bash
python -m pytest tests/test_languagetool_health.py tests/test_languagetool_deployment.py tests/test_workflow_automation.py -q
bash -n scripts/install_languagetool.sh
```

Expected: PASS.

- [ ] **Step 10: Commit reproducible runtime support**

```bash
git add config/languagetool_runtime.env scripts/check_languagetool.py scripts/install_languagetool.sh deploy/languagetool/languagetool.service .github/workflows/pipeline.yml requirements.txt tests/test_languagetool_health.py tests/test_languagetool_deployment.py tests/test_workflow_automation.py
git commit -m "ci: executa languagetool local e pinado"
```

---

### Task 11: Documentation, full regression, review, and GitHub release

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `KNOWN_ISSUES.md`
- Modify: `PROJECT_HANDOFF.md`
- Modify: `.env.example`
- Modify: `main.py` docstring if stage numbering changed during integration

**Interfaces:**
- Documents the operational contract already implemented; introduces no new runtime behavior.
- Release target: fast-forward `origin/main` only; never force-push.

- [ ] **Step 1: Update authoritative documentation**

Document:

- stage 3.5 narrator profile and removal of per-language redetection;
- `source_gender` versus locked `narration_gender`;
- stable-hash behavior when evidence is absent;
- same-gender TTS policy and why uncontrolled gTTS is disabled;
- guardian checkpoints, quarantine paths, and blocking rules;
- contextual glossary ownership and human-reviewed promotion;
- LanguageTool 6.6/Java 17 URL, SHA, localhost-only policy, health command, GitHub cache, and Oracle installer;
- GitHub Actions remains active production; Oracle is a supported deployment target, not claimed as active production;
- `LANGUAGETOOL_URL` and `LANGUAGETOOL_REQUIRED` in `.env.example` with no secret values.

- [ ] **Step 2: Run targeted regression suites**

Run:

```bash
python -m pytest tests/test_text_chunks.py tests/test_narrator_profile.py tests/test_voice_gender.py -q
python -m pytest tests/test_language_tool.py tests/test_contextual_glossary.py tests/test_translator_quality.py tests/test_script_guardian.py -q
python -m pytest tests/test_pipeline_narrator_profile.py tests/test_pipeline_quality_gate.py tests/test_workflow_automation.py -q
```

Expected: all PASS.

- [ ] **Step 3: Run the entire existing and new suite**

Run: `python -m pytest tests -q`

Expected: zero failures, zero errors.

- [ ] **Step 4: Run static and repository safety checks**

Run:

```bash
git diff --check
bash -n scripts/install_languagetool.sh
git grep -nE '(gho_|AIza|AQ[A-Za-z0-9_-]{20,}|reddit_session=|client_secret)' -- ':!docs/superpowers' ':!.env.example'
git status --short
```

Expected: no whitespace errors, valid shell syntax, no secret value, and only intended changes.

- [ ] **Step 5: Commit documentation and any test-only final adjustments**

```bash
git add README.md AGENTS.md KNOWN_ISSUES.md PROJECT_HANDOFF.md .env.example main.py
git commit -m "docs: registra gates de qualidade do roteiro"
```

- [ ] **Step 6: Request an independent whole-branch code review**

Use `superpowers:requesting-code-review` against the merge-base with `origin/main`. Resolve only findings that violate the approved spec, tests, security, or established repository conventions; rerun the owning focused test after each correction.

- [ ] **Step 7: Re-run final verification after review fixes**

Run: `python -m pytest tests -q`

Expected: zero failures and errors in fresh output.

- [ ] **Step 8: Confirm fast-forward status and push without force**

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
git push origin HEAD:main
```

Expected: the ancestry check exits `0` and the push reports a normal fast-forward update.

- [ ] **Step 9: Verify the real GitHub runner without publishing**

```bash
gh workflow run pipeline.yml --ref main \
  -f idiomas="pt en es" \
  -f dry_run=true \
  -f apenas_gerar=true \
  -f historia_teste=true
gh run list --workflow pipeline.yml --limit 1
```

Watch the returned run until completion and verify that Java 17, checksum verification, LanguageTool readiness/warmup, pytest, and the dry-run generation all succeed. Because `dry_run=true` and `apenas_gerar=true`, this run must not upload or schedule a video.

- [ ] **Step 10: Record the release evidence**

Report the pushed commit, complete pytest count, GitHub Actions run URL/status, LanguageTool version, and whether any stories were quarantined during verification. Do not include secret values or raw authentication headers.
