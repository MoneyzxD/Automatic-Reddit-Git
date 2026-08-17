"""
video.py
========
Renderiza vídeos verticais 1080x1920 (9:16) para Shorts/TikTok.

v5 — card animado de hook:
    - Seleciona ALEATORIAMENTE vídeo da pasta background/Shorts/
    - Loop com crossfade suave (0.5s) quando background < áudio
    - Trim automático quando background >= áudio
    - Subtítulos ASS word-by-word com estilo Impact vermelho
    - Fallback para cor sólida se pasta/arquivo não encontrado
    - CRF, FPS e audio_bitrate variáveis por publishing.yaml (anti-block)
    - Remoção de metadata EXIF do FFmpeg (anti-block)
    - [NOVO v5] Card overlay animado do hook:
        * .MOV com canal alpha (qtrle/argb) gerado pelo thumbnail.py
        * Fade-in e fade-out embutidos nos frames via Pillow
        * Overlay direto via format=auto — sem manipulação FFmpeg de alpha
        * Fallback para PNG estático se .mov não disponível
        * Centralizado horizontalmente, ~30% do topo vertical

Uso pelo main.py:
    vid_ren.render(
        audio_path     = audio_path,
        subtitle_path  = ass_path,
        output_path    = video_path,
        story_id       = story_id,
        hook_card_path = card_mov_path,   # .mov com alpha (ou .png fallback)
        hook_duration  = hook_audio_dur,  # duração do hook em segundos
    )
"""
from __future__ import annotations

import logging
import random
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_VIDEO_EXTS         = {".mp4", ".mov", ".mkv", ".webm"}
_CROSSFADE_DURATION = 0.5

# Delay antes do card aparecer (usado apenas no fallback PNG)
_CARD_DELAY    = 0.2
_CARD_FADE_IN  = 0.4
_CARD_FADE_OUT = 0.4

_PUBLISHING_YAML_PATHS = [
    Path("config/publishing.yaml"),
    Path("../config/publishing.yaml"),
    Path(__file__).parent.parent / "config" / "publishing.yaml",
]


def _load_fingerprint_config() -> dict:
    for path in _PUBLISHING_YAML_PATHS:
        if path.exists():
            try:
                import yaml
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                fp = data.get("video_fingerprint_variation", {})
                if fp.get("enabled", False):
                    return fp
            except Exception as e:
                logger.debug("Erro ao carregar publishing.yaml: %s", e)
            break
    return {}


def _pick_fingerprint(config: dict) -> tuple[int, int, str]:
    fp = _load_fingerprint_config()
    if not fp:
        return (
            config.get("crf", 23),
            config.get("fps", 30),
            config.get("audio_bitrate", "192k"),
        )

    crf_range     = fp.get("crf_range", [23, 23])
    fps_options   = fp.get("fps_options", [30])
    bitrate_opts  = fp.get("audio_bitrate_options", ["192k"])
    crf           = random.randint(crf_range[0], crf_range[1])
    fps           = random.choice(fps_options)
    audio_bitrate = random.choice(bitrate_opts)

    logger.info("Fingerprint sorteado: crf=%d fps=%d audio=%s", crf, fps, audio_bitrate)
    return crf, fps, audio_bitrate


def _exif_removal_flags() -> list:
    fp = _load_fingerprint_config()
    if not fp.get("remove_exif", True):
        return []
    return [
        "-metadata", "encoder=",
        "-metadata", "creation_time=",
        "-metadata", "comment=",
        "-metadata", "title=",
    ]


def _build_card_overlay_filter(
    card_label: str,
    bg_label: str,
    out_label: str,
    hook_duration: float,
    w: int,
    h: int,
    is_video_card: bool = False,
) -> str:
    """
    Constrói o filtro FFmpeg para o overlay do card.

    Dois modos:

    is_video_card=True (.mov com canal alpha qtrle/argb):
        - Overlay direto com format=auto — o FFmpeg usa o canal alpha dos frames
        - Fade embutido nos próprios frames (gerado pelo Pillow no thumbnail.py)
        - Sem controle de tempo via enable — o .mov já tem duração correta

    is_video_card=False (PNG estático — fallback):
        - Overlay com enable='between(t, ...)' para controlar janela de tempo
        - Aparece instantaneamente (sem fade real)

    Posição: centralizado horizontalmente, 30% do topo vertical.
    """
    pos_x = "(W-w)/2"
    pos_y = str(int(h * 0.30))

    if is_video_card:
        # .mov com alpha nativo — overlay direto
        card_filter = (
            f"[{card_label}]format=argb[card_alpha];"
            f"[{bg_label}][card_alpha]overlay={pos_x}:{pos_y}:format=auto[{out_label}]"
        )
    else:
        # PNG estático — controla janela de tempo via enable
        fade_in_start  = _CARD_DELAY
        fade_in_end    = fade_in_start + _CARD_FADE_IN
        fade_out_start = fade_in_start + hook_duration - _CARD_FADE_OUT
        fade_out_end   = fade_out_start + _CARD_FADE_OUT

        if fade_out_start < fade_in_end:
            fade_out_start = fade_in_end
            fade_out_end   = fade_out_start + _CARD_FADE_OUT

        card_filter = (
            f"[{card_label}]format=yuv420p[card_yuv];"
            f"[{bg_label}][card_yuv]overlay={pos_x}:{pos_y}:"
            f"enable='between(t,{fade_in_start:.3f},{fade_out_end:.3f})'[v_overlay];"
            f"[v_overlay]format=yuv420p[{out_label}]"
        )

    return card_filter


class VideoRenderer:

    def __init__(self, config: dict):
        self.config   = config
        self.width    = config.get("width", 1080)
        self.height   = config.get("height", 1920)
        self.bg_color = config.get("background_color", "#0D0D0D")
        self.bg_file  = Path(config.get("background_file", ""))
        self.bg_dir   = Path(config.get("background_dir", "background/Shorts"))
        self.preset   = config.get("preset", "fast")
        # Provider de background: decide se o arquivo vem da pasta local ou
        # e baixado (runner efemero). Injetavel para teste; se nao vier
        # pronto, e construido sob demanda em _select_background().
        self._bg_provider = config.get("background_provider")

    def _hex_to_ffmpeg(self, hex_color: str) -> str:
        return "0x" + hex_color.lstrip("#")

    def _escape_ass_path(self, path: Path) -> str:
        s = str(path).replace("\\", "/")
        s = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s)
        return s

    def _get_duration(self, file_path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning("ffprobe falhou para %s: %s", file_path.name, e)
        return 0.0

    def _select_background(self) -> Path | None:
        """
        Delega a escolha ao provider (local ou remoto). O render nao sabe
        nem precisa saber de onde o arquivo veio — recebe um caminho local.
        """
        if self._bg_provider is None:
            from stages.backgrounds import build_provider
            self._bg_provider = build_provider(
                base_dir=Path(__file__).parent.parent,
                bg_dir=self.bg_dir,
            )
        return self._bg_provider.get()

    def _apply_subtitle_filter(self, input_label: str, output_label: str,
                                subtitle_path: Path | None) -> str:
        if subtitle_path and Path(subtitle_path).exists():
            sub_escaped = self._escape_ass_path(Path(subtitle_path))
            sub_ext     = Path(subtitle_path).suffix.lower()
            if sub_ext == ".ass":
                return f"[{input_label}]ass='{sub_escaped}'[{output_label}]"
            else:
                return (
                    f"[{input_label}]subtitles='{sub_escaped}'"
                    f":force_style='FontName=Impact,FontSize=72,"
                    f"PrimaryColour=&H000000FF,OutlineColour=&H00000000,"
                    f"Outline=4,Shadow=3,Alignment=5,MarginV=120'[{output_label}]"
                )
        return f"[{input_label}]copy[{output_label}]"

    def _output_flags(self, output_path: Path, crf: int, audio_bitrate: str) -> list:
        return [
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-shortest", "-movflags", "+faststart",
        ] + _exif_removal_flags() + [str(output_path)]

    def _build_filter_complex(
        self,
        scale_filter: str,
        subtitle_path: Path | None,
        card_path: Path | None,
        hook_duration: float,
        w: int,
        h: int,
        has_card: bool,
    ) -> tuple[str, list[str]]:
        """
        Monta o filter_complex completo, com ou sem card overlay.

        Detecta automaticamente se o card é .mov (com alpha) ou .png (fallback),
        e constrói o filtro adequado para cada caso.

        Retorna:
            (filter_complex_string, extra_inputs)
        """
        extra_inputs = []

        if has_card and card_path and Path(card_path).exists():
            is_video_card = Path(card_path).suffix.lower() in {".mov", ".mp4", ".webm"}

            sub_filter  = self._apply_subtitle_filter("bg_raw", "bg_subbed", subtitle_path)
            card_filter = _build_card_overlay_filter(
                card_label="2:v",
                bg_label="bg_subbed",
                out_label="v",
                hook_duration=hook_duration,
                w=w,
                h=h,
                is_video_card=is_video_card,
            )
            filter_complex = scale_filter + ";" + sub_filter + ";" + card_filter
            extra_inputs   = ["-i", str(card_path)]

            mode = "video .mov (alpha nativo)" if is_video_card else "PNG estático (fallback)"
            logger.info(
                "Card overlay ativado [%s]: hook_duration=%.2fs card=%s",
                mode, hook_duration, Path(card_path).name,
            )

        else:
            if not has_card:
                logger.debug("Card overlay desativado (sem hook_card_path)")
            elif not card_path or not Path(card_path).exists():
                logger.warning("Card não encontrado (%s) — renderizando sem overlay", card_path)

            sub_filter     = self._apply_subtitle_filter("bg_raw", "v", subtitle_path)
            filter_complex = scale_filter + ";" + sub_filter
            extra_inputs   = []

        return filter_complex, extra_inputs

    def _build_loop_command(
        self, audio_path, subtitle_path, output_path,
        bg_video, audio_duration, bg_duration,
        w, h, fps, crf, audio_bitrate,
        card_path=None, hook_duration=0.0,
    ):
        logger.info(
            "Background %.1fs < áudio %.1fs → loop automático com crossfade %.1fs",
            bg_duration, audio_duration, _CROSSFADE_DURATION,
        )

        scale_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps}[bg_raw]"
        )

        has_card = bool(card_path and hook_duration > 0)
        filter_complex, extra_inputs = self._build_filter_complex(
            scale_filter, subtitle_path, card_path, hook_duration, w, h, has_card,
        )

        inputs = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(bg_video),
            "-i", str(audio_path),
        ] + extra_inputs

        return inputs + [
            "-filter_complex", filter_complex,
            "-t", str(audio_duration),
        ] + self._output_flags(output_path, crf, audio_bitrate)

    def _build_trim_command(
        self, audio_path, subtitle_path, output_path,
        bg_video, audio_duration,
        w, h, fps, crf, audio_bitrate,
        card_path=None, hook_duration=0.0,
    ):
        logger.info("Background maior que áudio → trim direto em %.1fs", audio_duration)

        scale_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps}[bg_raw]"
        )

        has_card = bool(card_path and hook_duration > 0)
        filter_complex, extra_inputs = self._build_filter_complex(
            scale_filter, subtitle_path, card_path, hook_duration, w, h, has_card,
        )

        inputs = ["ffmpeg", "-y", "-i", str(bg_video), "-i", str(audio_path)] + extra_inputs

        return inputs + [
            "-filter_complex", filter_complex,
        ] + self._output_flags(output_path, crf, audio_bitrate)

    def _build_color_command(
        self, audio_path, subtitle_path, output_path,
        color, w, h, fps, crf, audio_bitrate,
        card_path=None, hook_duration=0.0,
    ):
        logger.info("Usando fundo sólido (cor: %s)", self.bg_color)

        scale_filter = "[0:v]null[bg_raw]"

        has_card = bool(card_path and hook_duration > 0)
        filter_complex, extra_inputs = self._build_filter_complex(
            scale_filter, subtitle_path, card_path, hook_duration, w, h, has_card,
        )

        inputs = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:size={w}x{h}:r={fps}",
            "-i", str(audio_path),
        ] + extra_inputs

        return inputs + [
            "-filter_complex", filter_complex,
        ] + self._output_flags(output_path, crf, audio_bitrate)

    def render(
        self,
        audio_path: Path,
        subtitle_path: Path | None,
        output_path: Path,
        story_id: str | None = None,
        hook_card_path: Path | None = None,
        hook_duration: float = 0.0,
    ) -> bool:
        """
        Renderiza o vídeo final.

        Parâmetros do card overlay (v5):
            hook_card_path : Path para o .mov com alpha gerado por
                             ThumbnailGenerator.render_hook_card_video().
                             Aceita também .png como fallback estático.
                             Se None, renderiza sem overlay.
            hook_duration  : Duração em segundos do hook (usado para o PNG
                             fallback; no .mov o tempo é intrínseco ao arquivo).
                             Se 0, overlay desativado mesmo com hook_card_path.
        """
        output_path = Path(output_path)
        audio_path  = Path(audio_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not audio_path.exists():
            logger.error("Áudio não encontrado: %s", audio_path)
            return False

        audio_duration        = self._get_duration(audio_path)
        crf, fps, audio_bitrate = _pick_fingerprint(self.config)

        bg_video = self._select_background()
        if bg_video is None and self.bg_file and self.bg_file.exists():
            logger.info("Usando background_file do settings: %s", self.bg_file.name)
            bg_video = self.bg_file

        w, h  = self.width, self.height
        color = self._hex_to_ffmpeg(self.bg_color)

        # Resolve e valida card_path
        card_path = Path(hook_card_path) if hook_card_path else None
        if card_path and not card_path.exists():
            logger.warning("hook_card_path não existe: %s — overlay desativado", card_path)
            card_path = None

        if bg_video and bg_video.exists():
            bg_duration = self._get_duration(bg_video)
            needs_loop  = bg_duration > 0 and audio_duration > 0 and bg_duration < audio_duration
            if needs_loop:
                cmd = self._build_loop_command(
                    audio_path, subtitle_path, output_path,
                    bg_video, audio_duration, bg_duration,
                    w, h, fps, crf, audio_bitrate,
                    card_path=card_path, hook_duration=hook_duration,
                )
            else:
                cmd = self._build_trim_command(
                    audio_path, subtitle_path, output_path,
                    bg_video, audio_duration,
                    w, h, fps, crf, audio_bitrate,
                    card_path=card_path, hook_duration=hook_duration,
                )
        else:
            cmd = self._build_color_command(
                audio_path, subtitle_path, output_path,
                color, w, h, fps, crf, audio_bitrate,
                card_path=card_path, hook_duration=hook_duration,
            )

        logger.debug("FFmpeg: %s", " ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                logger.info("Vídeo renderizado: %s", output_path.name)
                return True

            logger.error(
                "FFmpeg erro (código %d):\n%s",
                result.returncode, result.stderr[-1200:],
            )

            # Fallback 1: tenta sem card overlay
            if card_path:
                logger.warning("Tentando fallback sem card overlay...")
                return self.render(
                    audio_path     = audio_path,
                    subtitle_path  = subtitle_path,
                    output_path    = output_path,
                    story_id       = story_id,
                    hook_card_path = None,
                    hook_duration  = 0.0,
                )

            # Fallback 2: fundo sólido
            if bg_video:
                logger.warning("Tentando fallback com fundo sólido...")
                cmd_fb    = self._build_color_command(
                    audio_path, subtitle_path, output_path,
                    color, w, h, fps, crf, audio_bitrate,
                )
                result_fb = subprocess.run(
                    cmd_fb, capture_output=True, text=True, timeout=600,
                )
                if result_fb.returncode == 0:
                    logger.info(
                        "Vídeo renderizado com fallback (fundo sólido): %s",
                        output_path.name,
                    )
                    return True

            return False

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timeout (600s) para %s", output_path.name)
            return False
        except FileNotFoundError:
            logger.error("FFmpeg não encontrado. Windows: winget install FFmpeg")
            return False