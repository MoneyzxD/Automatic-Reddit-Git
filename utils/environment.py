"""
utils/environment.py
====================
Resolucao central de "onde estou rodando e onde as coisas vivem".

Existe por um motivo especifico: o pipeline precisa rodar identicamente em
uma VM tradicional (Oracle Cloud, VPS) e em um runner efemero do GitHub
Actions, sem que main.py nem os stages saibam a diferenca. Toda pergunta
do tipo "de onde vem o background?" ou "onde fica o banco?" e respondida
aqui, a partir de variaveis de ambiente.

Principio de projeto — NAO QUEBRAR O QUE JA FUNCIONA:
    Todo default reproduz exatamente o comportamento local de hoje. Sem
    nenhuma variavel de ambiente definida, nada muda. Trocar de ambiente
    e trocar variavel de ambiente, nunca editar codigo.

Variaveis reconhecidas:
    PIPELINE_ENV            "local" (default) | "runner"
                            Apenas informativo/log — a decisao real vem das
                            variaveis especificas abaixo.

    BACKGROUND_SOURCE       "local" (default) | "remote"
    BACKGROUND_DIR          Pasta local de backgrounds (default:
                            <base>/background/Shorts)
    BACKGROUND_BASE_URL     Prefixo de URL para download em modo remote
                            (ex: releases do GitHub)
    BACKGROUND_CACHE_DIR    Onde guardar downloads (default: temp do SO)

    PIPELINE_DB_PATH        Caminho do SQLite (default: <base>/db/pipeline.db)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    """Le variavel de ambiente ja normalizada (sem espacos, sem aspas soltas)."""
    return os.environ.get(name, default).strip().strip('"').strip("'")


def current_env(base_dir: Path | None = None) -> str:
    """
    Nome do ambiente atual, apenas para log/diagnostico.
    Detecta runner do GitHub Actions automaticamente (GITHUB_ACTIONS=true),
    mas PIPELINE_ENV explicito sempre vence.
    """
    explicit = _env("PIPELINE_ENV")
    if explicit:
        return explicit
    if _env("GITHUB_ACTIONS").lower() == "true":
        return "runner"
    return "local"


# ── GROQ — UMA CHAVE POR IDIOMA ─────────────────────────────────────────────
#
# Motivo: PT/EN/ES rodando com uma unica chave competem pelo mesmo teto de
# tokens (por minuto E por dia) do free tier — quanto mais idiomas em
# producao, mais cedo esse teto compartilhado estoura (ja aconteceu: 200k
# TPD do gpt-oss-20b batido num dia de teste pesado). Cada idioma usar sua
# PROPRIA conta gratuita do Groq separa os orcamentos, sem duplicar
# trabalho nem contornar o limite de uma unica carga de trabalho — cada
# chave continua fazendo so o trabalho do seu proprio idioma.
#
# Variaveis: GROQ_API_KEY_PT, GROQ_API_KEY_EN, GROQ_API_KEY_ES
# Sem a chave especifica do idioma, cai para GROQ_API_KEY (comportamento
# atual preservado — nao quebra quem so tem uma chave configurada).

def groq_api_key(language: str = "") -> str:
    """
    Chave do Groq para o idioma informado. Tenta GROQ_API_KEY_<LANG> antes
    de cair para a chave generica GROQ_API_KEY.
    """
    if language:
        especifica = _env(f"GROQ_API_KEY_{language.upper()}")
        if especifica:
            return especifica
    return _env("GROQ_API_KEY")


# ── BACKGROUNDS ───────────────────────────────────────────────────────────────

def background_source() -> str:
    """
    "local" ou "remote". Default local — comportamento atual preservado.
    Se BACKGROUND_BASE_URL estiver definida e a fonte nao for explicitamente
    local, assume remote (evita configurar duas variaveis para o caso comum).
    """
    explicit = _env("BACKGROUND_SOURCE").lower()
    if explicit in ("local", "remote"):
        return explicit
    return "remote" if _env("BACKGROUND_BASE_URL") else "local"


def background_dir(base_dir: Path) -> Path:
    """Pasta local de backgrounds (usada em modo local e como fallback)."""
    custom = _env("BACKGROUND_DIR")
    if custom:
        return Path(custom)
    return base_dir / "background" / "Shorts"


def background_base_url() -> str:
    """Prefixo de URL dos backgrounds em modo remote (sem barra final)."""
    return _env("BACKGROUND_BASE_URL").rstrip("/")


def background_cache_dir() -> Path:
    """
    Onde os backgrounds baixados ficam durante a execucao.
    Em runner efemero isso morre junto com o job — o cache serve so para
    nao rebaixar o mesmo arquivo quando o job gera varios videos seguidos.
    """
    custom = _env("BACKGROUND_CACHE_DIR")
    if custom:
        path = Path(custom)
    else:
        path = Path(tempfile.gettempdir()) / "reddit_pipeline_backgrounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── BANCO DE DADOS ────────────────────────────────────────────────────────────

def db_path(base_dir: Path) -> Path:
    """
    Caminho do SQLite de dedupe/estado.

    Em VM (Oracle/VPS) o default local basta, porque o disco persiste. Em
    runner efemero o disco morre a cada execucao — por isso este ponto e
    configuravel: aponta para um volume restaurado por cache/artifact, ou
    (etapa futura) da lugar a um banco remoto sem tocar em nenhum stage.
    """
    custom = _env("PIPELINE_DB_PATH")
    if custom:
        path = Path(custom)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return base_dir / "db" / "pipeline.db"


# ── CREDENCIAIS DO YOUTUBE ────────────────────────────────────────────────────
#
# Em VM (Oracle/VPS) os tokens ficam em arquivo dentro de secrets/ e persistem.
# Em runner efemero nao existe disco persistente NEM navegador para o fluxo
# OAuth interativo — o token precisa chegar pronto por variavel de ambiente
# (GitHub Secret) e ser materializado em arquivo temporario, porque a
# biblioteca do Google le de arquivo.
#
# Variaveis:
#   YOUTUBE_TOKEN_<LANG>   conteudo JSON do token OAuth (ex: YOUTUBE_TOKEN_PT)
#   YOUTUBE_CREDENTIALS    conteudo JSON do client_secret (opcional)

def _materializar_json(conteudo: str, destino: Path) -> Path | None:
    """Grava um JSON vindo de variavel de ambiente em arquivo temporario."""
    conteudo = (conteudo or "").strip()
    if not conteudo:
        return None
    try:
        import json
        json.loads(conteudo)  # valida antes de gravar
    except Exception as e:
        logger_msg = f"JSON invalido em variavel de ambiente ({destino.name}): {e}"
        import logging
        logging.getLogger(__name__).error(logger_msg)
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return destino


def youtube_token_file(language: str, base_dir: Path) -> Path:
    """
    Caminho do token OAuth do YouTube para o idioma.

    Se YOUTUBE_TOKEN_<LANG> estiver definida (runner), materializa em arquivo
    temporario e devolve esse caminho. Caso contrario devolve o caminho
    tradicional em secrets/ (VM/local) — comportamento inalterado.
    """
    var = f"YOUTUBE_TOKEN_{language.upper().replace('-', '_')}"
    conteudo = _env(var)
    if conteudo:
        destino = background_cache_dir().parent / "yt_tokens" / f"token_{language}.json"
        caminho = _materializar_json(conteudo, destino)
        if caminho:
            return caminho
    return base_dir / "secrets" / f"youtube_token_{language}.json"


def youtube_credentials_file(base_dir: Path, padrao: str | None = None) -> Path:
    """
    Caminho do client_secret do YouTube. Aceita injecao por
    YOUTUBE_CREDENTIALS (runner) e mantem o arquivo local como default.
    """
    conteudo = _env("YOUTUBE_CREDENTIALS")
    if conteudo:
        destino = background_cache_dir().parent / "yt_tokens" / "credentials.json"
        caminho = _materializar_json(conteudo, destino)
        if caminho:
            return caminho
    if padrao:
        return Path(padrao)
    return base_dir / "secrets" / "youtube_credentials.json"


def oauth_interativo_permitido() -> bool:
    """
    False em runner: nao ha navegador para o fluxo OAuth. Serve para falhar
    com mensagem clara em vez de travar esperando um browser que nunca abre.
    """
    return current_env() != "runner"


# ── DIAGNOSTICO ───────────────────────────────────────────────────────────────

def describe(base_dir: Path) -> str:
    """Resumo de uma linha do ambiente resolvido — vai para o log no boot."""
    source = background_source()
    origem = background_base_url() if source == "remote" else background_dir(base_dir)
    return (
        f"env={current_env()} | backgrounds={source} ({origem}) | "
        f"db={db_path(base_dir)}"
    )
