"""
publisher.py
============
[MAPEADO — NÃO IMPLEMENTADO]

Este módulo será implementado após o pipeline de geração
estar estável e validado.

Publicação automática no YouTube via Data API v3.
Requer: google-api-python-client, google-auth-oauthlib

Funcionalidades planejadas:
    - Upload de vídeo com metadados completos
    - Agendamento de publicação
    - Fila gerenciada por SQLite
    - Delay de 2h entre uploads (evitar spam penalty)
    - Suporte a Shorts (< 60s) e vídeos longos
    - Publicação em 3 canais (PT / EN / ES) ou 1 canal multilíngue
"""
from __future__ import annotations



class YouTubePublisher:
    """[MAPEADO] Publicação automática no YouTube — implementar depois."""

    def __init__(self, config: dict, db=None):
        self.config  = config
        self.enabled = config.get("enabled", False)
        self.db      = db

    def upload(self, video_path, metadata: dict) -> str | None:
        """[NÃO IMPLEMENTADO] Fará upload do vídeo para o YouTube."""
        if not self.enabled:
            print("[publisher] Publicação automática ainda não implementada.")
            return None
        raise NotImplementedError(
            "publisher.py será implementado na Fase 2 do projeto."
        )
