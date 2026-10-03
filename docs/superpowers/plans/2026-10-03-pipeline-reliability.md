# Confiabilidade e recuperação do pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recuperar falhas temporárias e estado do runner sem perder histórias,
trocar o narrador, publicar conteúdo reprovado ou duplicar uploads.

**Architecture:** Mudanças estreitas no guardião e na seleção por idioma,
mais snapshots privados verificáveis de DB/fila/mídia. SQLite mantém estado de
geração; a fila mantém estado de upload. Um gravador serializado publica
payloads antes do manifesto, e resultado externo incerto bloqueia reenvio.

**Tech Stack:** Python 3.11 no Actions, SQLite/stdlib, requests/PyYAML/pytest,
SDK Groq e Google já instalados; LanguageTool 6.6/Temurin 17 e FFmpeg existentes.

**Spec:** [desenho aprovado](../specs/2026-10-03-pipeline-reliability-design.md).

## Global Constraints

- Produção continua no GitHub Actions, com stack gratuita, geração/publicação no mesmo job e renovação manual de OAuth.
- Preservar `approved/rejected/unavailable`, citações literais, patches verificáveis, perfil imutável e todos os gates.
- Revisão indisponível continua interrompendo o lote; nenhum fallback local aprova conteúdo.
- Chave fixa por idioma, sem rotação de contas.
- Meta inicial três, teto três partes por história e excedente máximo uma para amanhã.
- Código fica público; snapshots ficam em repositório **privado**.
- Credentials, tokens, cookie, `.env` e logs brutos ficam fora por lista permitida.
- Manter três snapshots completos de recuperação; mídia pendente é retida enquanto referenciada.
- Ativar limpeza externa exige aprovação específica.
- Comentários/logs novos em português; nomes/status técnicos seguem o código existente.
- Trabalhar em `_export_repo_publico/`; preservar os Markdown pendentes e não executar `sync_repo_publico.py`.

## Review Focus

1. `Retry-After` enorme, negativo ou não finito: nunca tentar antes da espera exigida nem prender o job; teste na tarefa 1.
2. História legada sem evidência de conclusão por idioma: não liberá-la como inédita após migração; teste na tarefa 2.
3. Fila corrompida ou disco sem espaço: erro visível, arquivo anterior preservado e nenhuma conclusão aparente; teste na tarefa 3.
4. Snapshot Windows/Linux com path traversal, link ou hash errado: rejeitar antes de alterar DB/fila da raiz destino; teste na tarefa 4.
5. YouTube aceitou o vídeo, mas o checkpoint falhou: conservar incerteza e impedir segundo envio, thumbnail/limpeza não vêm antes da confirmação; teste na tarefa 6.

## Execução e mapa de arquivos

Esta é uma entrega conectada de confiabilidade, não implementação dos agentes.
Recomendação: execução **nativa**, tarefas sequenciais e revisão independente
da branch ao final. Antes de implementar, o operador revisa este plano e confirma
o método. Usar worktree conforme a skill de execução, sem mover alterações do
usuário. O commit local de spec `051953d` ainda não foi enviado ao GitHub.

| Responsabilidade | Arquivos principais |
|---|---|
| Classificação segura e orçamento semântico | `stages/script_guardian.py`, `utils/groq_client.py`, `config/settings.yaml` |
| Estado de geração por idioma e migração | `utils/db.py`, `stages/filter.py` |
| Fonte/checkpoints locais aprovados | novo `utils/pipeline_recovery.py`, `main.py` |
| Enfileiramento atômico/idempotente | `scheduler/queue.py`, `stages/organizer.py` |
| Bundle verificável, sem rede | novo `utils/pipeline_snapshot.py` |
| Transporte privado e CLI | novos `utils/pipeline_state.py`, `scripts/pipeline_state.py` |
| Confirmação durável do upload | `scheduler/uploader.py`, `publish.py` |
| Rollout e bootstrap | `.github/workflows/pipeline.yml`, `.env.example`, `.gitignore`, README/handoff |

Os módulos novos não conhecem Groq, TTS ou Analytics. Não criar framework,
dashboard, daemon nem novos pacotes. Fonte/roteiros de recuperação ficam em
`data/recovery/`; staging/recibos locais em `data/state/`, ambos gitignorados.
Nenhum snapshot deve entrar nos artifacts públicos do workflow.

Comandos abaixo usam `python` no Actions/venv ativado. Neste Windows, usar
`& '../venv/Scripts/python.exe' -m pytest tests -q` na pasta de produção. Um bloqueio
do executável pelo sandbox requer escalada, não reinstalação de dependências.

---

### Tarefa 1: Classificar indisponibilidade e eliminar retries multiplicados

**Files:** Modify `stages/script_guardian.py`, `utils/groq_client.py`,
`config/settings.yaml`, `tests/test_script_guardian.py`; Create
`tests/test_groq_retry_control.py`.

**Interfaces:**
- Preserve `tracked_groq(api_key: str, stage: str)` para chamadores legados.
- Add kwargs `sdk_max_retries: int | None = None`, `retry_rate_limit: bool = True`,
  `timeout: float | None = None` a `tracked_groq` e seus wrappers.
- Add `SemanticFailure(code: str, http_status: int | None, mode: str,
  attempts: int, context_chars: int)` em `script_guardian.py`.
- `_ReviewUnavailable` recebe `failure: SemanticFailure | None`; nunca recebe
  mensagem bruta de exceção externa. Relatório adiciona `semantic_failure`.

- [ ] **1. Escrever testes vermelhos no arquivo que já possui fixtures do guardião.**

```python
@pytest.mark.parametrize("status,expected", [
    (401, "authentication"), (403, "authorization"),
    (413, "context_limit"), (429, "rate_limit"), (503, "provider_error"),
])
def test_indisponibilidade_tem_classe_sem_vazar(tmp_path, perfil_feminino, status, expected):
    class ProviderError(RuntimeError):
        status_code = status
    class Reviewer:
        def review(self, **kwargs):
            raise ProviderError("Authorization=SEGREDO_TESTE")
    guardian = guardian_fake(tmp_path, Reviewer(), semantic_retry_wait_seconds=0)
    with pytest.raises(QualityUnavailable):
        revisar(guardian, perfil_feminino)
    event = json.loads(guardian.report_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["semantic_failure"]["code"] == expected
    assert event["semantic_failure"]["http_status"] == status
    assert "SEGREDO_TESTE" not in json.dumps(event)

def test_json_invalido_nao_e_erro_do_provider(tmp_path, perfil_feminino):
    guardian = guardian_fake(tmp_path, FakeSemanticReviewer(["bad"] * 3))
    with pytest.raises(QualityUnavailable):
        revisar(guardian, perfil_feminino)
    event = json.loads(guardian.report_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["semantic_failure"]["code"] == "invalid_json"
    assert event["status"] == "unavailable"
```

- [ ] **2. Rodar `python -m pytest tests/test_script_guardian.py -q`.**
  Esperar falha por ausência do campo, não erro de import/fixture.
- [ ] **3. Implementar classificação por atributos/tipos seguros e validações explícitas.**

```python
def provider_failure_code(exc):
    status = getattr(exc, "status_code", None)
    status = status if type(status) is int else None
    if status in {401, 403, 413, 429}:
        return {401: "authentication", 403: "authorization",
                413: "context_limit", 429: "rate_limit"}[status], status
    if status is not None:
        return "provider_error", status
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
        return "timeout", None
    if isinstance(exc, ConnectionError) or type(exc).__name__ == "APIConnectionError":
        return "connection", None
    return "provider_error", None
```

JSON que não decodifica → `invalid_json`; estrutura/tipos inválidos →
`invalid_schema`; citação fora da fonte → `nonliteral_evidence`; texto/contexto
acima do teto → `context_limit`. Manter a aprovação estrita atual. Campos
serializados vêm da dataclass, não de `exc.__dict__`, body ou headers completos.

Se necessário para distinguir HTTP 400, ler apenas `error.code` e traduzir
valores conhecidos (`json_validate_failed`, `context_length_exceeded`,
`model_not_found`, `invalid_api_key`) para enums locais; valor desconhecido
vira `other`. Nunca copiar message/failed_generation. Metadados opcionais de
resposta registram apenas finish_reason conhecido e contagens numéricas de
tokens, permitindo distinguir truncamento de resposta de JSON/schema inválido.

- [ ] **4. Centralizar tentativas em `_request`; testar o transporte também.**

```python
# _GroqReviewer: o SDK/wrapper não repetem a mesma chamada escondidos.
client = tracked_groq(key, "script_guardian", sdk_max_retries=0,
                      retry_rate_limit=False, timeout=self.config["semantic_timeout_seconds"])
```

Config inicial: `semantic_max_attempts: 3`, `semantic_timeout_seconds: 60`,
`semantic_retry_wait_seconds: 15`, `semantic_max_retry_wait_seconds: 120`.
Todos positivos/finitos, salvo espera padrão zero permitida em testes. Três
tentativas incluem a primeira; o teto é por requisição `facts/chunk/global`.
Normalizar defaults antes de construir `_GroqReviewer`, preservando chamadas
com config `{}`. Fixtures `guardian_fake` e `pipeline` definem espera zero;
testes de espera usam relógio/sleep falsos, sem introduzir pausas na suíte.
401/403/413 e 4xx permanentes encerram sem nova chamada. 429/408/409/5xx,
timeout/conexão e resposta inválida usam o orçamento; conteúdo `rejected` não
é retry de transporte. Preservar o loop de reparos semânticos existente.

Ler apenas `Retry-After` numérico/data e opcional `retry-after-ms`, sem logá-los
brutos. Se a espera exigida ultrapassa o teto, incluindo infinito positivo,
encerrar `unavailable`, nunca encurtar e tentar antes. Negativo, NaN ou texto
inválido usam espera configurada. Esperas
longas no executor são divididas em blocos de até 60s para permitir updates.

```python
@pytest.mark.parametrize("header", ["86400", "inf"])
def test_espera_excessiva_nao_provoca_retry(tmp_path, perfil_feminino, header):
    calls = []
    class Reviewer:
        def review(self, **kwargs):
            calls.append(kwargs)
            exc = RuntimeError("SEGREDO_TESTE")
            exc.status_code = 429
            exc.response = SimpleNamespace(headers={"Retry-After": header})
            raise exc
    guardian = guardian_fake(tmp_path, Reviewer(), semantic_max_retry_wait_seconds=120)
    with pytest.raises(QualityUnavailable):
        revisar(guardian, perfil_feminino)
    assert len(calls) == 1
```

Para negativo/NaN/texto, testar três chamadas e `sleep` falso com espera padrão.
Em `test_groq_retry_control.py`, monkeypatch de `groq.Groq` captura kwargs;
assertar SDK `max_retries=0`, timeout configurado e uma chamada no wrapper.
Assertar que o uso legado mantém seus defaults e telemetria. Atualizar o fake
`tracked` do teste existente do guardião para aceitar/inspecionar kwargs.

- [ ] **5. Rodar os dois arquivos e testes de interfaces de narrador; commit fechado.**

```bash
python -m pytest tests/test_script_guardian.py tests/test_groq_retry_control.py tests/test_narrator_stage_interfaces.py -q
git add stages/script_guardian.py utils/groq_client.py config/settings.yaml tests/test_script_guardian.py tests/test_groq_retry_control.py
git commit -m "fix: classificar falhas semanticas e controlar retries"
```

### Tarefa 2: Estado aditivo de geração e seleção por idioma

**Files:** Modify `utils/db.py`, `stages/filter.py`; Create `tests/test_pipeline_recovery_db.py`.

**Interfaces:**
- Keep `story_exists/insert_story/update_status/get_pending` compatíveis.
- Add `register_story(story: dict, languages: list[str], source_hash: str) -> None`.
- Add `processing_languages(story_id: str, languages: list[str]) -> list[str]`.
- Add `set_language_status(story_id: str, language: str, status: str,
  *, profile_id: str | None = None, reason_code: str = "") -> None`.
- Add `retry_candidates(languages: list[str]) -> list[str]`, ordenado pela
  última atualização; somente fonte gerenciada e estados retomáveis.
- `StoryFilter(config, db=None, *, languages: list[str] | None = None)`;
  sem `languages`, mantém dedupe legado. Normalização PT acontece na entrada.

- [ ] **1. Escrever testes cobrindo retomada, conclusão parcial e legado.**

```python
from utils.db import PipelineDB
from stages.filter import StoryFilter

def test_falha_temporaria_nao_vira_duplicada(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1", "title": "source"}, ["pt", "en"], "a" * 64)
    db.set_language_status("s1", "pt", "processing")
    db.set_language_status("s1", "pt", "unavailable", reason_code="rate_limit")
    assert db.processing_languages("s1", ["pt", "en"]) == ["pt", "en"]
    assert not StoryFilter({}, db, languages=["pt"]).is_already_processed("s1")

def test_pt_exportado_nao_impede_en(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.register_story({"id": "s1"}, ["pt", "en"], "a" * 64)
    db.set_language_status("s1", "pt", "processing", profile_id="p1")
    db.set_language_status("s1", "pt", "exported", profile_id="p1")
    assert db.processing_languages("s1", ["pt", "en"]) == ["en"]

def test_legado_desconhecido_permanece_bloqueado(tmp_path):
    db = PipelineDB(tmp_path / "pipeline.db")
    db.insert_story({"id": "old"})
    assert db.processing_languages("old", ["pt", "en", "es"]) == []
    assert StoryFilter({}, db, languages=["en"]).is_already_processed("old")
```

- [ ] **2. Rodar esse arquivo e confirmar falhas de métodos ausentes.**
- [ ] **3. Migrar sem reset: coluna `stories.source_sha256` e tabela nova.**

```sql
CREATE TABLE IF NOT EXISTS story_languages (
    story_id TEXT NOT NULL,
    language TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    profile_id TEXT,
    reason_code TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (story_id, language)
);
```

Consultar `PRAGMA table_info(stories)` antes de executar
`ALTER TABLE stories ADD COLUMN source_sha256 TEXT`.
`register_story` usa transação: insere fonte nova e linhas `pending`; fonte
legada sem hash ou hash alterado exige reconciliação, não conversão automática.
Fontes gerenciadas podem receber novo idioma ainda não processado. Status de
geração: `pending`, `processing`, `unavailable`, `rejected`, `exported`.
Não duplicar status de upload do YouTube nessa tabela.

```python
# Regra de seleção; row/rows obtidos por SQL parametrizado na mesma leitura.
if row is None:
    return languages.copy()
if row["source_sha256"] is None:
    return []
statuses = {entry["language"]: entry["status"] for entry in rows}
return [lang for lang in languages
        if statuses.get(lang, "pending") in {"pending", "unavailable"}]
```

Transições `pending/unavailable → processing → exported/rejected/unavailable`.
Idempotência aceita repetir o mesmo terminal, mas não `exported → processing`
nem alterar `profile_id` já fixado. `processing` abandonado pede reconciliação.
Validar idiomas/status e SHA-256 hexadecimal de 64 caracteres; SQL sempre com
parâmetros. Testar migração
duas vezes, linhas de partes preservadas, fonte alterada bloqueada e outro
personagem não afetado por perfil. Uploads legados continuam na fila intactos.

- [ ] **4. Rodar DB, lote diário e volume diário; commit.**

```bash
python -m pytest tests/test_pipeline_recovery_db.py tests/test_generate_daily_batch.py tests/test_daily_volume_plan.py -q
git add utils/db.py stages/filter.py tests/test_pipeline_recovery_db.py
git commit -m "fix: separar dedupe de conclusao por idioma"
```

### Tarefa 3: Retomar fonte/perfil/roteiros e enfileirar o idioma inteiro

**Files:** Create `utils/pipeline_recovery.py`; Modify `main.py`,
`stages/organizer.py`, `scheduler/queue.py`, `tests/test_pipeline_quality_gate.py`,
`tests/test_queue_tiktok.py`; Create `tests/test_recovery_checkpoints.py`.

**Interfaces:**
- Consumes a API DB da tarefa 2, `source_sha256(title, original_text)`,
  `load_profile/save_profile` de `stages/narrator_profile.py`.
- Add `save_source(base_dir: Path, story: dict, source_hash: str,
  *, expanded_source: str) -> Path` e
  `load_source(base_dir: Path, story_id: str, source_hash: str) -> dict`.
- Add `save_approved_step(base_dir: Path, story_id: str, language: str,
  stage: str, payload: dict) -> None` e
  `load_approved_step(base_dir: Path, story_id: str, language: str,
  stage: str, source_hash: str, profile_id: str) -> dict | None`.
  Payload: source hash, profile ID, texto, ledger factual quando houver,
  partes/metadados preparados quando houver, hash do conteúdo e versão do formato.
- Add `enqueue_many(language: str, items: list[dict], *, generation_key: str) -> list[str]`.
  Items usam campos do `enqueue` atual; API antiga conserva sufixos `_v2`.
- Add `FileOrganizer.organize_batch(outputs: list[dict], *, generation_key: str) -> list[dict]`.
  `organize_output` continua disponível, mas erro de fila não vira sucesso.

- [ ] **1. Adicionar teste de retomada na fixture `pipeline` existente.**

```python
def test_retomada_nao_gera_pt_duas_vezes(pipeline):
    from scheduler.queue import get_pending
    pipeline.fail = "translation"
    pipeline.fail_language = "es"
    pipeline.outage = True
    with pytest.raises(QualityUnavailable):
        main.run_pipeline(pipeline.config, ["pt", "es"], test_story=True)
    assert len(get_pending("pt")) == 1
    prior_audios = len(pipeline.audios)
    prior_pt = get_pending("pt")[0]["metadata"]["narrator_profile_id"]
    pipeline.fail = None
    main.run_pipeline(pipeline.config, ["pt", "es"], test_story=True)
    assert len(get_pending("pt")) == len(get_pending("es")) == 1
    assert get_pending("es")[0]["metadata"]["narrator_profile_id"] == prior_pt
    assert all(language == "es" for _, language, _ in pipeline.audios[prior_audios:])
```

Adicionar caso adaptação indisponível: todos os idiomas solicitados ficam
retomáveis, sem mídia. Reprovação de conteúdo bloqueia somente o escopo afetado;
adaptação comum reprovada bloqueia a história nos idiomas solicitados.

- [ ] **2. Cobrir corrupção de fila e falha de escrita antes de alterar loader.**

```python
def test_fila_corrompida_nao_vira_fila_vazia(tmp_path):
    path = tmp_path / "pt.json"  # fixture autouse use_temp_queue já isola a pasta
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(queue_module.QueueStateError):
        queue_module.get_pending("pt")
    assert path.read_text(encoding="utf-8") == "{broken"
```

Em novo teste, monkeypatch `os.replace` para lançar `OSError`, chamar
`enqueue_many` e assertar bytes originais, zero itens novos e erro propagado.
Chamar o mesmo batch duas vezes retorna mesmos IDs; mesma chave com conteúdo
ou total diferente dá `QueueStateError`. Uma parte com arquivo ausente impede
enfileirar todas. Não quebrar os testes legados de colisão com `_v2`.

- [ ] **3. Rodar os testes novos e confirmar os sintomas reproduzidos.**
- [ ] **4. Implementar fonte privada e checkpoints JSON atômicos.**

```python
with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                 dir=path.parent, delete=False) as handle:
    json.dump(payload, handle, ensure_ascii=False)
    handle.flush()
    os.fsync(handle.fileno())
    temporary = Path(handle.name)
os.replace(temporary, path)
```

Validar IDs alfanuméricos do Reddit/teste, stage allowlist, idioma e caminhos
sob `data/recovery/`. SHA inclui título/fonte completos conforme helper atual.
Fonte privada contém story bruto e `expanded_source` imutável; validar
`source_sha256(story['title'], expanded_source)` sem importar `main` na utility.
`load_source` retorna esse envelope, não um story parcialmente reconstruído.
Cache aprovado só é reutilizado com fonte/perfil/conteúdo/versão compatíveis;
invalidade exige erro ou nova revisão, nunca aprovação implícita. O gate
`pre_tts` permanece obrigatório inclusive após retomada de checkpoint.

- [ ] **5. Integrar na orquestração sem refatorar etapas de mídia.**

Antes da extração, procurar `retry_candidates` com fonte privada validada.
Na ausência, seguir extração/filtragem existente com `languages=languages`.
Registrar fonte/idiomas; carregar perfil já salvo antes de resolver novamente.
Se DB possui perfil e arquivo válido não está disponível, bloquear retomada.
Marcar `processing` antes do trabalho; `unavailable` em falha temporária,
`rejected` em quarentena, inclusive os gates comuns anteriores à tradução.

```python
remaining = db.processing_languages(story_id, languages)
if not remaining:
    return
# Depois de preparar/renderizar TODAS as partes de lang:
organizer.organize_batch(completed, generation_key=generation_key)
db.set_language_status(story_id, lang, "exported", profile_id=profile.profile_id)
```

`generation_key` é SHA-256 de JSON canônico com story ID, idioma, source hash e
profile ID. Salvar passos aprovados antes de avançar e o conjunto preparado
antes de mídia. Só mudar `parts_done` após exportação/enfileiramento completo.
Falhas de áudio/legenda/render tornam idioma retomável sem fila parcial.
Dry-run não grava fonte/checkpoints. Test-story continua sem Reddit; re-render
voluntário usa namespace de validação novo, não reseta estado de produção.

- [ ] **6. Tornar fila atomicamente gravável e batch idempotente.**

`_load_queue`: ausência permite fila nova apenas no bootstrap/root validado;
JSON inválido propaga `QueueStateError`. `_save_queue` usa temp+fsync+replace e
propaga erro; nenhuma exceção de enfileiramento é engolida no organizer.
`enqueue_many` valida todos os arquivos/partes antes de uma única gravação,
anexa generation key + story/part/total nos itens e reconcilia replay. Copiar
MP4/JPG/metadados antes da fila; atualizar DB por parte depois da fila durável
local. Se cair nessa janela, a mesma chave recupera IDs sem criar `_v2`.

- [ ] **7. Rodar gates, filas e lote; commit incluindo `.gitignore` para recovery.**

```bash
python -m pytest tests/test_pipeline_quality_gate.py tests/test_queue_tiktok.py tests/test_recovery_checkpoints.py tests/test_generate_daily_batch.py -q
git add main.py stages/organizer.py scheduler/queue.py utils/pipeline_recovery.py tests/test_pipeline_quality_gate.py tests/test_queue_tiktok.py tests/test_recovery_checkpoints.py .gitignore
git commit -m "fix: retomar idiomas e enfileirar historias atomicamente"
```

### Tarefa 4: Snapshot local verificável e restauração segura

**Files:** Create `utils/pipeline_snapshot.py`, `tests/test_pipeline_snapshot.py`;
Modify `.gitignore` para `data/state/`.

**Interfaces:**
- `SnapshotError(RuntimeError)` com mensagem segura.
- `Snapshot(snapshot_id: str, namespace: str, manifest: dict,
  payload_path: Path, media: dict[str, Path])`, dataclass congelada.
- `build_snapshot(base_dir: Path, db_path: Path, *, snapshot_id: str,
  namespace: str, run_id: str, commit: str, run_attempt: int = 1) -> Snapshot`.
- `verify_snapshot(snapshot: Snapshot) -> None`.
- `restore_snapshot(snapshot: Snapshot, target_dir: Path) -> None`.
  Conteúdo validado antes de tocar paths ativos; recibo em `data/state/ready.json`.

- [ ] **1. Criar fixture `snapshot_fixture` com DB real temporário e vídeo fake.**

No fixture: `PipelineDB(base/'db/pipeline.db')`, fonte `s1` gerenciada, perfil/
source/checkpoint pelos helpers da tarefa 3 e fila temporária monkeypatchada.
Criar `data/exports/pt/a.mp4` com bytes `b'video'`, `a.jpg`, metadata JSON e
`enqueue_many`; concluir geração. Retornar `(base, db)`. É teste de storage,
não teste de codec/renderização. Acrescentar `.env` e `secrets/token.json`
sintéticos para comprovar exclusão, nunca usar credencial real.

```python
def test_snapshot_restaura_fila_e_midia_em_outra_raiz(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import build_snapshot, restore_snapshot
    base, db = snapshot_fixture
    snapshot = build_snapshot(base, db.db_path, snapshot_id="test-1",
                              namespace="validation-test", run_id="1", commit="abc")
    destination = tmp_path / "restored"
    restore_snapshot(snapshot, destination)
    queue = json.loads((destination / "data/queue/pt.json").read_text(encoding="utf-8"))
    video = Path(queue["items"][0]["video_path"])
    assert video.is_relative_to(destination)
    assert video.read_bytes() == b"video"
    assert not (destination / "secrets").exists()
    assert not (destination / ".env").exists()
```

- [ ] **2. Rodar e confirmar import ausente; adicionar corrupção antes do código.**

```python
def test_hash_errado_nao_sobrescreve_destino(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import build_snapshot, restore_snapshot, SnapshotError
    base, db = snapshot_fixture
    snapshot = build_snapshot(base, db.db_path, snapshot_id="bad-1",
                              namespace="validation-test", run_id="1", commit="abc")
    snapshot.payload_path.write_bytes(b"corrupt")
    target = tmp_path / "target"
    (target / "db").mkdir(parents=True)
    prior = target / "db/pipeline.db"
    prior.write_bytes(b"prior")
    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, target)
    assert prior.read_bytes() == b"prior"
```

Adicionar parametrização de membros `../escape`, `/absolute`, `C:/outside`,
`data\\..\\escape`, symlink e hardlink. Recriar arquivo TAR/hash corretamente
nesses testes para atingir validação de caminhos, não só hash. Assertar que
nenhum arquivo fora do destino foi criado. Testar membro duplicado, limite
descompactado, DB inválido, perfil incompatível e fila com MP4 faltando.

- [ ] **3. Implementar bundle sem rede e inventário allowlist.**

Manifesto versão 1: ID, namespace, run/run_attempt/commit/sequence, SHA do payload,
`files` com paths POSIX/tamanho/hash, media por hash e `queue_paths` para
remapear referências. Control-plane até 100 MiB descompactado; arquivo de
mídia até 1 GiB; exceder bloqueia sem truncar. Valores configuráveis validados,
não aumento automático de cota. Medir tamanhos reais no rollout.

Allowlist: backup DB via `sqlite3.Connection.backup`, JSON das filas canônicas
`pt/pt-br/en/es`, recovery/fontes/passos e perfis referenciados por gerações
gerenciadas, scripts/metadados necessários, MP4/JPG referenciados pendentes.
Incluir JPG/MP4 ainda preservados para capa falha, sem reenviar vídeo. Excluir
todo `secrets/`, `.env*`, credentials/token files e `data/logs/`. Rejeitar
referências fora da raiz ou links em paths de origem; não percorrer workspace
inteiro. Hashes são de bytes; SQL `PRAGMA quick_check` precisa retornar `ok`.

```python
def safe_member_name(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or path.is_absolute()
            or ".." in path.parts or str(path) != name):
        raise SnapshotError("Caminho inválido no snapshot")
    return path
```

Extrair manualmente apenas arquivos regulares previamente verificados, sem
`extractall`. Staging em pasta dedicada; remapear `video_path/thumbnail_path`
pelos mappings verificáveis, não por basename. Validar tudo antes de substituir
DB/fila. Commit local de restauração tem marker `restoring` antes de substituir
e `ready` só depois; falha no meio bloqueia processos, conservando a cópia
privada/preimagem para recuperação assistida. Restaurar novamente é idempotente.

- [ ] **4. Rodar arquivo inteiro com paths adversariais e commit.**

```bash
python -m pytest tests/test_pipeline_snapshot.py -q
git add utils/pipeline_snapshot.py tests/test_pipeline_snapshot.py .gitignore
git commit -m "feat: verificar e restaurar snapshots do pipeline"
```

### Tarefa 5: Transporte de estado privado e CLI

**Files:** Create `utils/pipeline_state.py`, `scripts/pipeline_state.py`,
`tests/test_pipeline_state.py`; Modify `.env.example` apenas nomes sem valores.

**Interfaces:**
- Consumes `Snapshot`, build/verify/restore da tarefa 4.
- `StateError(RuntimeError)`; somente mensagens seguras.
- `PrivateStateStore(repo: str, token: str, namespace: str, *, session=None)`.
- Methods `validate_target() -> None`, `publish(snapshot: Snapshot) -> dict`,
  `fetch_latest() -> Snapshot`, `from_environment(base_dir: Path) -> PrivateStateStore`.
- `checkpoint_from_environment(base_dir: Path, *, reason: str) -> dict` constrói,
  verifica e publica snapshot; falha propaga, não substitui manifesto anterior.
- CLI `main(argv: list[str] | None = None) -> int`, comandos `verify`, `save`,
  `restore`, `bootstrap`; inputs `--base-dir`, `--namespace`, `--db-path`.
  `verify --legacy-report PATH` produz relatório de bootstrap; bootstrap recebe
  `--reconciliation-file PATH --confirm-digest SHA256` ou
  `--allow-empty-validation` exclusivamente para namespace de teste novo.

- [ ] **1. Testar destino público/diferente antes de implementar rede.**

```python
from unittest.mock import Mock
from utils.pipeline_state import PrivateStateStore, StateError

def test_destino_publico_bloqueia_escrita():
    session = Mock()
    response = Mock(status_code=200)
    response.json.return_value = {"full_name": "MoneyzxD/Automatic-Reddit-State", "private": False}
    session.request.return_value = response
    store = PrivateStateStore("MoneyzxD/Automatic-Reddit-State", "opaque", "production", session=session)
    with pytest.raises(StateError):
        store.validate_target()
    assert all(call.args[0] == "GET" for call in session.request.call_args_list)
```

Mesma estrutura para `private=True` com `full_name` diferente; nenhum POST.
Testar 401/403/404 sanitizados, Secret ausente, namespace inválido, resposta
malformada, paginação e falha no último upload: head anterior não é substituído.

- [ ] **2. Rodar tests e confirmar ausência da implementação.**
- [ ] **3. Implementar API GitHub restrita; publicar manifesto por último.**

`PIPELINE_STATE_REPO=MoneyzxD/Automatic-Reddit-State`, `PIPELINE_STATE_TOKEN`
e `PIPELINE_STATE_NAMESPACE` são obrigatórios no runner habilitado. Token nunca
vem implicitamente de `gh auth token` ou do `GITHUB_TOKEN` público. Sessão
requests sem proxy herdado, HTTPS/SSL verificado, timeout de conexão/leitura;
Authorization só para `api.github.com`/`uploads.github.com`. Download de asset
trata 200/302 e retira Authorization no destino de redirecionamento permitido.
Nunca registrar URL assinada, body de erro ou objeto Session/headers.

Uma release por run/namespace, assets imutáveis únicos por sequência e hash.
Criar/listar release no repositório privado; upload mídia por hash antes do
payload; após verificar os assets, enviar `complete-<sequence>.json` contendo
manifesto e IDs dos assets. Esse último asset é o commit marker. Não usar
`--clobber`, delete do head, tag `latest` ou newest timestamp sem verificação.

```python
# Sequência de publicação; todos os métodos são da PrivateStateStore.
self.validate_target()
verify_snapshot(snapshot)
release = self._ensure_release(snapshot.manifest["run_id"])
media_ids = self._upload_media(release, snapshot.media)
payload_id = self._upload_asset(release, snapshot.payload_path)
receipt = {"snapshot_id": snapshot.snapshot_id, "namespace": self.namespace,
           "manifest": snapshot.manifest, "payload_id": payload_id, "media_ids": media_ids}
self._upload_completion(release, receipt)
return receipt
```

Helpers privados definidos nesta tarefa: `_ensure_release(run_id: str) -> dict`,
`_upload_media(release: dict, media: dict[str, Path]) -> dict[str, int]`,
`_upload_asset(release: dict, path: Path) -> int`,
`_upload_completion(release: dict, receipt: dict) -> None`. API responses são
checadas para IDs inteiros, asset state/tamanho/hash antes do commit marker.
Snapshots já enviados retornam o mesmo recibo; payload órfão não vira head.
`fetch_latest` pagina todos os marcadores do namespace, usa sequência monotônica
com run/attempt para ordenar, verifica o último completo. Se esse completo foi
corrompido, bloquear: voltar a anterior requer reconciliação assistida.

`checkpoint_from_environment` converte `SnapshotError` e falha de IO em
`StateError` sanitizado, para o upload interromper corretamente em qualquer
falha de confirmação. Sequência incrementa com recibo local atômico; cada
subprocesso usa os mesmos run/attempt, sem resetar o contador a cada chamada.

Retenção seleciona pelo menos três completos para recuperação. Ainda não
executar nenhum DELETE de release/asset; mídia referenciada permanece. Limite
de capacidade gera alerta/erro, não perda silenciosa nem cleanup não aprovado.

- [ ] **4. Implementar CLI com bootstrap explícito e marker de prontidão.**

`restore`: deve existir snapshot íntegro; escreve recibo `ready.json` após
restauração. `save`: exige recibo válido do mesmo namespace/root e grava nova
sequência. `verify`: valida estado/snapshot e imprime só ID/namespace/contagens.
`verify --legacy-report`: grava JSON privado com data, hashes de DB/filas,
snapshot candidato, IDs confirmados/incertos, legado/arquivos faltantes e
fontes recuperáveis. `bootstrap` exige hash desse relatório e hashes atuais
iguais; mudança entre revisão e confirmação invalida a operação. IDs externos
que precisarem de conferência são confirmados no Studio pelo operador.
Não aceita cache como verdade sem essa reconciliação e não marca desconhecidos
como inéditos. Processamento abandonado é reconciliado pela combinação de
fonte/checkpoints + batch inteiro na fila; com qualquer efeito externo incerto,
fica bloqueado. Não apaga cache nem gera histórias nessa operação.

`--allow-empty-validation` exige namespace `validation-*`, destino privado
validado e prova de ausência de head obtida por listagem autorizada completa.
Cria DB/fila vazios e primeiro snapshot de teste; nunca funciona em production
e nunca interpreta 401/403/404 do repo como ausência de estado. Havendo head,
usa restore, sem sobrescrever. Isso é bootstrap explícito, não fallback.
Relatório/confirmacão ficam privados; tokens são lidos do ambiente, não da CLI.
Código de erro é não-zero e mensagem segura; nenhuma operação executa upload YouTube.

- [ ] **5. Exercitar o transporte com mocks e round-trip local; commit.**

```bash
python -m pytest tests/test_pipeline_state.py tests/test_pipeline_snapshot.py -q
python scripts/pipeline_state.py --help
git add utils/pipeline_state.py scripts/pipeline_state.py tests/test_pipeline_state.py .env.example
git commit -m "feat: persistir estado em releases privadas"
```

### Tarefa 6: Confirmar upload duravelmente antes de thumbnail/limpeza

**Files:** Modify `scheduler/uploader.py`, `scheduler/queue.py`, `publish.py`,
`scripts/generate_daily_batch.py`; Create `tests/test_upload_recovery.py`;
Modify `tests/test_publish_overflow.py`, `tests/test_queue_tiktok.py`.

**Interfaces:**
- Consumes `checkpoint_from_environment` e StateError da tarefa 5.
- `YouTubeUploader.upload(item: dict, publish_at: str | None = None,
  *, on_video_uploaded=None) -> dict`: callback recebe resultado inicial com
  `status/video_id/url/publish_at`, antes de thumbnail. Chamadores legados
  sem callback permanecem compatíveis.
- Add `queue.get_item(language: str, item_id: str) -> dict | None` para reler
  estado antes de cada efeito; add `get_uncertain(language: str) -> list[dict]`.
- `uploaded/uploading` do YouTube nunca voltam para `pending` implicitamente.

- [ ] **1. Testar ordem do callback e a falha de persistência.**

Usar `YouTubeUploader.__new__` com fake `_get_service`, `MediaFileUpload` e
`_think_time` monkeypatchados; request `next_chunk` retorna `(None, {'id':'vid1'})`.
Fake thumbnail `.execute` anexa `thumbnail` a `events`. O callback anexa
`checkpoint`. `upload` deve produzir `events == ['checkpoint','thumbnail']`.

```python
def test_callback_falho_nao_e_engolido_apos_video_aceito(youtube_fake):
    uploader, item, events = youtube_fake
    from utils.pipeline_state import StateError
    def failed_checkpoint(result):
        events.append("checkpoint")
        assert result["video_id"] == "vid1"
        raise StateError("Checkpoint privado indisponível")
    with pytest.raises(StateError):
        uploader.upload(item, on_video_uploaded=failed_checkpoint)
    assert events == ["checkpoint"]
```

Fixture `youtube_fake` constrói o fake acima em pasta temporária, com MP4/JPG
sintéticos. Não chamar API real nesse teste. Outro teste em fila temporária:
marcar `uploading`, simular queda e chamar publicação novamente; nenhum
`videos.insert` adicional e item aparece em `get_uncertain`. Item `uploaded`
com thumbnail 403 também não pode reenviar. Confirmar atualização idempotente
de `uploaded_at`, contadores e `video_id`.

- [ ] **2. Rodar arquivo e garantir falha pelo comportamento atual.**
- [ ] **3. Integrar checkpoints respeitando a ordem dos efeitos externos.**

```python
update_status(language, item_id, "youtube", "uploading")
checkpoint_from_environment(base_dir, reason="before_youtube_upload")

def confirm_video(result):
    update_status(language, item_id, "youtube", "uploaded",
                  video_id=result["video_id"], url=result["url"],
                  publish_at=result.get("publish_at"))
    checkpoint_from_environment(base_dir, reason="youtube_video_confirmed")
```

Passar `confirm_video` ao uploader no modo runner de estado obrigatório. Callback
roda assim que houver ID válido, antes de thumbnail/pausa. `StateError` escapa
dos catches genéricos e interrompe a rodada; não converter confirmação falha
em erro de conteúdo ou retry automático de upload. A fila remota anterior
continua `uploading`, portanto bloqueia reenvio em caso de queda.
Sem ID válido após iniciar transporte, tratar resultado como incerto salvo
rejeição comprovada anterior ao envio. Alertar reconciliação pelo notifier
existente, sem body de erro. Não alterar títulos nem visibilidade.

Após thumbnail, atualizar somente campos de capa e salvar outro checkpoint;
falha de capa não rebaixa upload. Só depois da confirmação durável executar
limpeza local já existente; se limpeza falhar, vídeo não volta a pending.
Checkpoint pós-limpeza registra paths removidos. Token/oauth JSON nunca entra
em snapshots. Atualizar os fakes de upload que precisarem aceitar o callback.

- [ ] **4. Proteger publicação/contagem contra filas incompletas.**

Falha comprovada de autenticação/preflight antes de iniciar transporte pode
manter item recuperável, sem novo intento no mesmo job. Geração conta essa
mídia já pronta ao renovar tokens; não cria novos vídeos só para substituir
uploads aguardando credencial. Resultado após iniciar transporte permanece
incerto salvo prova específica de rejeição sem criação.

`publish.py` bloqueia idioma com `get_uncertain`, relê item antes de cada upload,
e não gera slots além de meta+excedente. Contagem usa agendamentos confirmados
e pending com mídia íntegra; histórico confirmado não conta duas vezes.
`generate_daily_batch` diferencia código 2 indisponível de conteúdo pulado;
não gira novas histórias para esconder outage. Meta e janelas ficam intactas.

- [ ] **5. Rodar publicação, filas e plano diário; commit.**

```bash
python -m pytest tests/test_upload_recovery.py tests/test_publish_overflow.py tests/test_queue_tiktok.py tests/test_generate_daily_batch.py tests/test_daily_volume_plan.py -q
git add scheduler/uploader.py scheduler/queue.py publish.py scripts/generate_daily_batch.py tests/test_upload_recovery.py tests/test_publish_overflow.py tests/test_queue_tiktok.py
git commit -m "fix: confirmar uploads antes de avancar efeitos externos"
```

### Tarefa 7: Bootstrap privado, CI isolado e validação real

**Files:** Modify `.github/workflows/pipeline.yml`, `main.py`, README, AGENTS/handoff e
KNOWN_ISSUES somente trechos afetados; Create `tests/test_pipeline_state_workflow.py`.

**Interfaces:**
- Workflow inputs `state_action` (`normal/bootstrap/verify`) e `validation_namespace`
  opcional, validado `validation-[a-z0-9-]+`; default de geração sem publicação
  é `validation-<run_id>`. Cron/live em main usa `production`.
- ENV `PIPELINE_STATE_REQUIRED=true`, `PIPELINE_STATE_REPO`, `PIPELINE_STATE_TOKEN`,
  `PIPELINE_STATE_NAMESPACE`; secret somente nos passos que precisam dele.
- Bootstrap/verify não geram nem publicam vídeos. Dry-run não cria snapshot de
  produção; namespace de validação nunca publica nem escreve no head production.

- [ ] **1. Testar contratos do YAML antes de adicionar os novos passos.**

Usar `yaml.BaseLoader`, que preserva a chave `on`. Assertar que restore aparece
antes de geração/publicação, checkpoint final usa `always()` mais recibo válido,
produção/teste têm grupos de concorrência distintos e que snapshot/recovery
nunca aparecem em `actions/upload-artifact`. Testar que falta de Secret não
vira fallback ao cache e que `state_action=verify/bootstrap` impede publicação.
Não tratar esse parse como prova de que expressões Actions executaram.

- [ ] **2. Ajustar workflow sem separar geração/publicação.**

```yaml
- name: Restaurar estado privado verificado
  env:
    PIPELINE_STATE_TOKEN: ${{ secrets.PIPELINE_STATE_TOKEN }}
    PIPELINE_STATE_REPO: ${{ vars.PIPELINE_STATE_REPO }}
    PIPELINE_STATE_NAMESPACE: ${{ env.PIPELINE_STATE_NAMESPACE }}
  run: python scripts/pipeline_state.py restore --base-dir .
```

Adicionar resolução de namespace/ação antes de restore, por Python com inputs
em ENV, sem interpolar input livre em comando shell. Execução live só em main,
sem test-story/dry-run/apenas-gerar. Bootstrap de production é permitido em
branch revisada via disparo manual e relatório confirmado, sem geração/publicação;
assim prepara o armazenamento antes de integrar o workflow novo.
Namespace compartilhado de validação permite
segundo run `verify` restaurar o primeiro sem nova geração. Concorrência continua
serializando o estado production; namespaces de teste não tocam suas filas.

Um preview novo invoca explicitamente `bootstrap --allow-empty-validation`
antes de gerar. Verify/restauração de namespace existente não usa essa flag.
Cache pode acelerar downloads; DB/fila cacheados são só candidatos ao bootstrap,
não restauração autoritativa. Save em falha exige receipt/marker ready válido;
não sobrescrever estado após falha de restore. Artifacts públicos mantêm somente
os logs já sanitizados e mídia aprovada pela política existente. Estado privado
não é artifact. Integrar checkpoints obrigatórios também em `main.py`: depois
de registrar/salvar fonte, depois de persistir perfil, após conjuntos de passos
aprovados e após exportar/enfileirar cada idioma. Assim queda durante geração
não depende exclusivamente do save final. Tokens de estado ficam nos steps de
geração/publicação que chamam esses checkpoints, nunca no step de testes.
Falha de checkpoint interrompe antes de novos efeitos; unit tests usam fake de
storage isolado. Grupo de concorrência production preserva o nome atual
`pipeline-videos`, inclusive bootstrap, para serializar com workflows antigos;
validação usa grupo distinto por namespace. Atualizar comentário falso de
commit de estado e instruções de recuperação. Preservar documentação pendente
do operador.

- [ ] **3. Criar o repositório privado autorizado, com checagem antes/depois.**

```powershell
gh repo view MoneyzxD/Automatic-Reddit-State --json nameWithOwner,visibility
# Apenas se não existe; autenticação/permissão falha não significa inexistência.
gh repo create MoneyzxD/Automatic-Reddit-State --private --add-readme --description "Estado privado recuperavel do pipeline Reddit"
gh repo view MoneyzxD/Automatic-Reddit-State --json nameWithOwner,visibility
```

Exigir identidade/visibilidade corretas; repo preexistente inesperado pede
direção, não sobrescrita. Criar token fine-grained no GitHub, limitado somente
a este repo, Contents read/write. Operador disponibiliza Secret
`PIPELINE_STATE_TOKEN` no repo de produção; não colar token no chat nem ecoar
no terminal. Variável `PIPELINE_STATE_REPO` aponta para o nome aprovado. Isso
não renova nem substitui Secrets do YouTube/Groq/Reddit.

- [ ] **4. Reconciliar/importar estado atual sem limpar cache.**

Obter cópia recente do DB/fila no runner; inventário privado lista video IDs
confirmados, uploadings, filas sem arquivos, fontes gerenciadas/legadas e hashes.
Conferir IDs já enviados antes de aceitar bootstrap. Histórias legadas ficam
bloqueadas sem prova específica; `1wfduc8` só torna-se retomável com fonte
recuperada íntegra e confirmação de ausência de upload. Se a fonte original
não foi preservada, registrar impossibilidade de replay exato, não fabricar
o texto a partir da quarentena redigida.

Operador confirma o relatório antes de trocar autoridade. Primeiro snapshot
production completo é verificado/restaurado em raiz de teste; só então ativar
workflow novo em main. Não deletar caches, filas, snapshots nem vídeos remotos.

- [ ] **5. Rodar suíte/revisão da branch e validar serviços reais sem upload.**

```bash
python -m pytest tests -q
git diff --check
python -m compileall -q main.py publish.py utils scheduler stages scripts
```

Revisor independente verifica diff, migração, allowlist, retry budget e janela
de upload incerto. Corrigir e testar defeitos concretos até resolvidos; não
parar por número arbitrário de rodadas. Nenhum achado promove glossário sozinho.
Na branch, GitHub Actions real: PT/EN/ES, `historia_teste=true`,
`apenas_gerar=true`, `dry_run=false`, namespace de validação. Verificar qualidade
semântica real, fonte/profile IDs, MP4/ASS/card e `ffprobe` de duração/resolução.
Segundo run verify restaura DB/fila/mídia em outro runner sem gerar/publicar.

Se revisão continuar unavailable, a nova classe/status e contagem precisam
explicar qual mecanismo atacar. Reproduzir esse mecanismo com teste isolado
e corrigir estreitamente antes de declarar a etapa resolvida. Não substituir
a prova por mais testes falsos nem inferir 429. Falta de credencial/restrição
do serviço é bloqueio operacional a informar, não sucesso.

- [ ] **6. Liberar main e confirmar uma rodada dentro da meta normal.**

Somente após bootstrap e validação real bem-sucedidos, integrar/push e usar
uma rodada normal (não uploads de teste extras). Confirmar IDs/publishAt por
idioma, checkpoint pós-upload e a restauração seguinte sem duplicatas.
Registrar run IDs/commit e limitações no handoff. Se banco/snapshot/serviço
falharem, gates bloqueiam publicação e o operador recebe diagnóstico seguro.

```bash
git add .github/workflows/pipeline.yml main.py tests/test_pipeline_state_workflow.py README.md AGENTS.md PROJECT_HANDOFF.md KNOWN_ISSUES.md
git commit -m "feat: restaurar estado privado no Actions com bootstrap seguro"
```

Rollback de código conserva schema aditivo e snapshots. Antes de rodar versão
anterior, reconciliar os IDs externos; não descartar tabela nova nem voltar
a cache velho automaticamente. Limpeza externa permanece desativada.

## Aceite final e próxima entrega

- [ ] Diagnóstico/retries provados por testes e por chamada Groq real.
- [ ] Idioma incompleto retomado com identidade/roteiro conservados; terminal não duplicado.
- [ ] Snapshot privado restaura DB/fila/mídia e protege caminhos/segredos.
- [ ] Upload confirmado preservado; resultado incerto bloqueado e reconciliável.
- [ ] Uma rodada normal confirmada nos três idiomas, sem alterar meta/janelas.
- [ ] Evidências registradas separando mocks, geração real, upload e agendamento.

Após esses itens, manutenção observadora ganha seu próprio contrato/CLI/relatório;
crescimento começa por inventário/Analytics de leitura ou exports reais, conforme
[a proposta existente](../../YOUTUBE_GROWTH_AGENT.md). Não implementar esses
agentes ou alterar conteúdo editorial como efeito colateral deste plano.

## Referências técnicas conferidas

- [SDK Groq: erros, retries e timeouts](https://github.com/groq/groq-python#retries):
  permite desabilitar retry automático e configurar timeout; nenhum body precisa
  ser logado para ler HTTP status.
- [Autenticação Actions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token):
  permissão adicional requer credencial apropriada; token do repo público não
  é uma autorização implícita para o armazenamento privado.
- [Assets de release](https://docs.github.com/en/rest/releases/assets):
  download pode responder 200/302; acesso privado requer permissão e validação.
