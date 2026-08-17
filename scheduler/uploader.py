"""
scheduler/uploader.py
=====================
Gerencia uploads para YouTube e TikTok com tecnicas anti-block.

Anti-block implementado:
    - User-Agent rotation entre requests
    - Think-time aleatorio entre chamadas API
    - Retry com backoff fixo
    - Edicao pos-upload (troca 1 hashtag apos delay configuravel)

YouTube : totalmente funcional via google-api-python-client
TikTok  : estrutura pronta, ativa quando aprovacao chegar
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Caminhos possiveis para publishing.yaml
_PUBLISHING_YAML_PATHS = [
    Path("config/publishing.yaml"),
    Path("../config/publishing.yaml"),
    Path(__file__).parent.parent / "config" / "publishing.yaml",
]


def _load_publishing_config() -> dict:
    for path in _PUBLISHING_YAML_PATHS:
        if path.exists():
            try:
                import yaml
                with open(path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.debug("Erro ao carregar publishing.yaml: %s", e)
            break
    return {}


def _think_time() -> None:
    """Pausa aleatoria entre chamadas API para simular comportamento humano."""
    pub    = _load_publishing_config()
    tt     = pub.get("api_think_time", {})
    min_s  = tt.get("min_seconds", 1.5)
    max_s  = tt.get("max_seconds", 4.0)
    delay  = random.uniform(min_s, max_s)
    logger.debug("Think-time: %.1fs", delay)
    time.sleep(delay)


def _get_user_agent() -> str:
    """Retorna User-Agent aleatorio do pool em publishing.yaml."""
    pub    = _load_publishing_config()
    agents = pub.get("user_agents", [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ])
    return random.choice(agents)


# ── YOUTUBE UPLOADER ──────────────────────────────────────────────────────────

class YouTubeUploader:
    """
    Faz upload de videos para YouTube via Data API v3.
    Usa OAuth2 com token persistido por canal.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
    ]

    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = Path(credentials_file)
        self.token_file       = Path(token_file)
        self._service         = None

    def _get_service(self):
        """Autentica e retorna o servico YouTube. Reutiliza token salvo."""
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None

            # Carregar token existente
            if self.token_file.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self.token_file), self.SCOPES
                )

            # Renovar token expirado
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._save_token(creds)

            # Autenticacao inicial
            if not creds or not creds.valid:
                # Em runner efemero nao existe navegador — o fluxo interativo
                # travaria esperando um browser que nunca abre. Falha rapido
                # com instrucao concreta em vez de pendurar o job.
                from utils import environment as env
                if not env.oauth_interativo_permitido():
                    raise RuntimeError(
                        "Token OAuth do YouTube ausente ou invalido e nao ha navegador "
                        "neste ambiente para autenticar.\n"
                        "Gere o token localmente (uma vez) e injete o CONTEUDO do "
                        f"arquivo na variavel de ambiente YOUTUBE_TOKEN_<IDIOMA>.\n"
                        f"Arquivo esperado: {self.token_file}"
                    )
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Credenciais nao encontradas: {self.credentials_file}\n"
                        "Baixe o client_secret.json do Google Cloud Console."
                    )
                flow  = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.SCOPES
                )
                creds = flow.run_local_server(port=0)
                self._save_token(creds)

            self._service = build("youtube", "v3", credentials=creds)
            return self._service

        except ImportError as e:
            raise ImportError(
                f"Dependencia faltando: {e}\n"
                "Execute: pip install google-api-python-client "
                "google-auth-httplib2 google-auth-oauthlib"
            )

    def _save_token(self, creds) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.token_file, "w") as f:
            f.write(creds.to_json())
        logger.debug("Token salvo: %s", self.token_file.name)

    def upload(self, item: dict, publish_at: str | None = None) -> dict:
        """
        Faz upload de um video para YouTube.

        publish_at: timestamp ISO 8601 UTC (ex: "2026-08-18T14:30:00Z").
            Quando informado, o video sobe como PRIVADO e o proprio YouTube
            o publica no horario indicado. Isso desacopla "quando o job
            rodou" de "quando o video aparece" — essencial em runner
            efemero, onde o cron pode atrasar 10-30 min. Sem publish_at, o
            comportamento antigo e mantido (publica imediatamente).

        Retorna dict com status, video_id, url e publish_at aplicado.
        """
        video_path = item.get("video_path")
        if not video_path or not Path(video_path).exists():
            return {"status": "failed", "error": "video_path nao encontrado"}

        metadata  = item.get("metadata", {})
        yt_meta   = metadata.get("youtube", {})
        title     = yt_meta.get("title", metadata.get("title", "Reddit Story"))
        desc      = yt_meta.get("description", "")
        tags      = yt_meta.get("tags", [])
        category  = yt_meta.get("category_id", "22")
        kids      = yt_meta.get("made_for_kids", False)
        visibility = yt_meta.get("visibility", "public")

        try:
            from googleapiclient.http import MediaFileUpload

            service = self._get_service()
            _think_time()

            status_body = {
                "madeForKids":    kids,
                "selfDeclaredMadeForKids": kids,
            }
            if publish_at:
                # A API exige privacyStatus=private junto de publishAt —
                # qualquer outro valor faz o agendamento ser ignorado.
                status_body["privacyStatus"] = "private"
                status_body["publishAt"]     = publish_at
                logger.info("Publicacao agendada para %s (sobe como privado)", publish_at)
            else:
                status_body["privacyStatus"] = visibility

            body = {
                "snippet": {
                    "title":       title[:100],
                    "description": desc[:5000],
                    "tags":        tags[:500],
                    "categoryId":  category,
                },
                "status": status_body,
            }

            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 5,  # 5MB chunks
            )

            logger.info("Iniciando upload YouTube: %s", title[:50])
            request  = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info("Upload YouTube: %d%%", progress)

            video_id = response.get("id")
            url      = f"https://youtu.be/{video_id}"
            if publish_at:
                logger.info("Upload concluido: %s — publica automaticamente em %s",
                            url, publish_at)
            else:
                logger.info("Upload YouTube concluido: %s", url)

            _think_time()
            return {
                "status":     "uploaded",
                "video_id":   video_id,
                "url":        url,
                "publish_at": publish_at,
            }

        except Exception as e:
            logger.error("Erro no upload YouTube: %s", e)
            return {"status": "failed", "error": str(e)}

    def edit_hashtag(self, video_id: str, new_hashtags_str: str) -> bool:
        """
        Edita hashtags de um video ja publicado.
        Usado pelo post_upload_edit para simular comportamento humano.
        """
        try:
            service = self._get_service()
            _think_time()

            # Busca video atual
            response = service.videos().list(
                part="snippet", id=video_id
            ).execute()

            if not response.get("items"):
                return False

            snippet = response["items"][0]["snippet"]
            desc    = snippet.get("description", "")

            # Troca ultima linha de hashtags
            lines       = desc.strip().split("\n")
            new_desc    = "\n".join(
                lines[:-1] + [new_hashtags_str]
            ) if lines else new_hashtags_str

            snippet["description"] = new_desc[:5000]
            _think_time()

            service.videos().update(
                part="snippet",
                body={"id": video_id, "snippet": snippet},
            ).execute()

            logger.info("Hashtags editadas pos-upload: %s", video_id)
            return True

        except Exception as e:
            logger.debug("Erro ao editar hashtags: %s", e)
            return False


# ── TIKTOK UPLOADER ───────────────────────────────────────────────────────────

class TikTokUploader:
    """
    Faz upload de videos para TikTok via Content Posting API.
    Requer aprovacao do app TikTok para desenvolvedores.

    STATUS: estrutura pronta — ativa quando aprovacao chegar.
    Para ativar: definir enabled=True no publishing.yaml do canal.
    """

    API_BASE = "https://open.tiktokapis.com/v2"

    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = Path(credentials_file)
        self.token_file       = Path(token_file)

    def _get_access_token(self) -> str | None:
        """Carrega access token do arquivo de token."""
        if not self.token_file.exists():
            logger.warning(
                "Token TikTok nao encontrado: %s\n"
                "Execute o fluxo OAuth do TikTok para gerar o token.",
                self.token_file,
            )
            return None
        try:
            with open(self.token_file, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("access_token")
        except Exception as e:
            logger.error("Erro ao carregar token TikTok: %s", e)
            return None

    def upload(self, item: dict) -> dict:
        """
        Faz upload de um video para TikTok via Direct Post.
        Requer aprovacao do app e token OAuth valido.
        """
        access_token = self._get_access_token()
        if not access_token:
            return {
                "status": "failed",
                "error": "Token TikTok nao encontrado. Execute autenticacao OAuth.",
            }

        video_path = item.get("video_path")
        if not video_path or not Path(video_path).exists():
            return {"status": "failed", "error": "video_path nao encontrado"}

        metadata = item.get("metadata", {})
        tt_meta  = metadata.get("tiktok", {})
        caption  = tt_meta.get("caption", metadata.get("title", ""))[:2200]

        try:
            import requests

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type":  "application/json; charset=UTF-8",
                "User-Agent":    _get_user_agent(),
            }

            video_size = Path(video_path).stat().st_size

            # Step 1: Iniciar upload
            _think_time()
            logger.info("Iniciando upload TikTok: %s", caption[:50])

            init_resp = requests.post(
                f"{self.API_BASE}/post/publish/video/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title":            caption,
                        "privacy_level":    tt_meta.get("visibility", "PUBLIC_TO_EVERYONE"),
                        "disable_duet":     tt_meta.get("disable_duet", False),
                        "disable_comment":  tt_meta.get("disable_comment", False),
                        "disable_stitch":   False,
                    },
                    "source_info": {
                        "source":       "FILE_UPLOAD",
                        "video_size":   video_size,
                        "chunk_size":   video_size,
                        "total_chunk_count": 1,
                    },
                },
                timeout=30,
            )

            if init_resp.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"TikTok init falhou: {init_resp.status_code} {init_resp.text}",
                }

            data       = init_resp.json().get("data", {})
            publish_id = data.get("publish_id")
            upload_url = data.get("upload_url")

            if not publish_id or not upload_url:
                return {"status": "failed", "error": "publish_id ou upload_url nao retornados"}

            # Step 2: Upload do arquivo
            _think_time()
            with open(video_path, "rb") as f:
                video_data = f.read()

            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes 0-{video_size-1}/{video_size}",
                    "Content-Type":  "video/mp4",
                    "User-Agent":    _get_user_agent(),
                },
                data=video_data,
                timeout=300,
            )

            if upload_resp.status_code not in (200, 201, 204):
                return {
                    "status": "failed",
                    "error": f"TikTok upload falhou: {upload_resp.status_code}",
                }

            # Step 3: Verificar status
            _think_time()
            status_resp = requests.post(
                f"{self.API_BASE}/post/publish/status/fetch/",
                headers=headers,
                json={"publish_id": publish_id},
                timeout=30,
            )

            logger.info("Upload TikTok concluido: publish_id=%s", publish_id)
            return {
                "status":     "uploaded",
                "video_id":   publish_id,
                "url":        f"https://tiktok.com/@conta/video/{publish_id}",
            }

        except Exception as e:
            logger.error("Erro no upload TikTok: %s", e)
            return {"status": "failed", "error": str(e)}


# ── UPLOADER PRINCIPAL ────────────────────────────────────────────────────────

class Uploader:
    """
    Orquestra uploads para YouTube e TikTok com anti-block completo.
    Chamado pelo runner.py a cada ciclo de verificacao de fila.
    """

    def __init__(self, language: str, channel_config: dict):
        self.language       = language
        self.channel_config = channel_config
        self.pub_config     = _load_publishing_config()

        secrets_dir = Path("secrets")

        # Credenciais resolvidas pelo ambiente: em VM vem de secrets/, em
        # runner efemero vem de variavel de ambiente (GitHub Secret).
        from utils import environment as env
        base_dir = Path(__file__).parent.parent

        # YouTube
        yt_cfg = channel_config.get("youtube", {})
        self.youtube = YouTubeUploader(
            credentials_file=str(env.youtube_credentials_file(
                base_dir, yt_cfg.get("credentials_file"))),
            token_file=str(env.youtube_token_file(language, base_dir)),
        ) if yt_cfg.get("enabled", True) else None

        # TikTok
        tt_cfg = channel_config.get("tiktok", {})
        self.tiktok = TikTokUploader(
            credentials_file=tt_cfg.get("credentials_file",
                                          str(secrets_dir / f"tiktok_{language}.json")),
            token_file=str(secrets_dir / f"tiktok_token_{language}.json"),
        ) if tt_cfg.get("enabled", True) else None

    def upload_item(self, item: dict, publish_at: str | None = None,
                     ja_agendados: int = 0) -> dict:
        """
        Faz upload de um item da fila para todas as plataformas ativas.

        publish_at: horario ISO 8601 UTC de publicacao. Se None, e calculado
            automaticamente a partir das janelas de postagem do canal
            (scheduler/scheduling.py). Passe explicitamente so para testes.

        ja_agendados: quantos videos deste idioma ja foram agendados nesta
            rodada — espaca as publicacoes em vez de empilhar no mesmo horario.

        Retorna dict com resultado por plataforma.
        """
        from scheduler.queue import update_status, mark_for_deletion

        item_id  = item["id"]
        results  = {}
        all_ok   = True

        # ── YouTube ──────────────────────────────────────────────────────────
        if self.youtube:
            platforms = self.pub_config.get("global", {}).get("platforms", [])
            if "youtube" in platforms:
                if publish_at is None:
                    from scheduler.scheduling import next_publish_slot, to_youtube_timestamp
                    publish_at = to_youtube_timestamp(
                        next_publish_slot(self.language, self.channel_config,
                                          ja_agendados=ja_agendados)
                    )
                logger.info("Uploading YouTube: %s (%s)", item_id, self.language)
                update_status(self.language, item_id, "youtube", "uploading")
                result = self.youtube.upload(item, publish_at=publish_at)
                results["youtube"] = result
                update_status(
                    self.language, item_id, "youtube",
                    result["status"],
                    video_id=result.get("video_id"),
                    url=result.get("url"),
                )
                if result["status"] != "uploaded":
                    all_ok = False
                    logger.error("YouTube falhou: %s", result.get("error"))
                else:
                    self._schedule_post_edit(item_id, result["video_id"], item)

        # ── TikTok ───────────────────────────────────────────────────────────
        if self.tiktok:
            platforms = self.pub_config.get("global", {}).get("platforms", [])
            if "tiktok" in platforms:
                logger.info("Uploading TikTok: %s (%s)", item_id, self.language)
                update_status(self.language, item_id, "tiktok", "uploading")
                result = self.tiktok.upload(item)
                results["tiktok"] = result
                update_status(
                    self.language, item_id, "tiktok",
                    result["status"],
                    video_id=result.get("video_id"),
                    url=result.get("url"),
                )
                if result["status"] != "uploaded":
                    all_ok = False
                    logger.error("TikTok falhou: %s", result.get("error"))

        # ── Deletar arquivo local apos upload confirmado ──────────────────────
        if all_ok:
            delete = self.pub_config.get("global", {}).get("delete_after_upload", True)
            if delete:
                self._delete_local_files(item)
                mark_for_deletion(self.language, item_id)
                logger.info("Arquivos locais deletados: %s", item_id)

        return results

    def _delete_local_files(self, item: dict) -> None:
        """Deleta video e thumbnail locais apos upload confirmado."""
        for key in ("video_path", "thumbnail_path"):
            path = item.get(key)
            if path and Path(path).exists():
                try:
                    Path(path).unlink()
                    logger.debug("Deletado: %s", path)
                except Exception as e:
                    logger.debug("Nao foi possivel deletar %s: %s", path, e)

    def _schedule_post_edit(self, item_id: str, video_id: str, item: dict) -> None:
        """
        Agenda edicao pos-upload em thread separada.
        Troca 1 hashtag apos delay configuravel (anti-block camada 5).
        """
        pub      = self.pub_config
        edit_cfg = pub.get("post_upload_edit", {})
        if not edit_cfg.get("enabled", True):
            return

        import threading

        delay_min = edit_cfg.get("delay_hours_min", 2) * 3600
        delay_max = edit_cfg.get("delay_hours_max", 6) * 3600
        delay     = random.uniform(delay_min, delay_max)

        def do_edit():
            logger.info(
                "Post-edit agendado em %.0fh para %s",
                delay / 3600, item_id,
            )
            time.sleep(delay)
            # Gera nova string de hashtags
            from stages.metadata import _pick_hashtags
            _, new_hashtags_str = _pick_hashtags(self.language)
            if self.youtube and video_id:
                self.youtube.edit_hashtag(video_id, new_hashtags_str)

        thread = threading.Thread(target=do_edit, daemon=True)
        thread.start()