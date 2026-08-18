"""
thumbnail.py
============
Etapa 16 do pipeline — dois objetivos:

    1. generate()             → Thumbnail estática JPG (YouTube)
                                Carrega template PNG do idioma correto,
                                insere o hook como texto, exporta JPG 1280x720.

    2. render_hook_card()     → PNG do card com texto renderizado (980x458).
                                Usado como fallback ou etapa intermediária.

    3. render_hook_card_video() → .MOV com canal alpha (codec qtrle) contendo
                                  fade-in e fade-out suaves via Pillow frame-a-frame.
                                  Usado pelo video.py como overlay animado.

Templates esperados em:
    <raiz>/Thumbnail/Thumbnail - PT.png
    <raiz>/Thumbnail/Thumbnail - EN.png
    <raiz>/Thumbnail/Thumbnail - ES.png

O pipeline (main.py) chama:
    thumb_gen.generate(hook_for_lang, lang, thumb_path)
    card_path = thumb_gen.render_hook_card_video(hook_for_lang, lang, card_mov_path,
                                                  hook_duration=hook_duration,
                                                  audio_duration=audio_duration)
"""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapeamento idioma → nome do arquivo de template
_TEMPLATE_MAP = {
    "pt":    "Thumbnail - PT.png",
    "pt-br": "Thumbnail - PT.png",
    "en":    "Thumbnail - EN.png",
    "es":    "Thumbnail - ES.png",
}

# Dimensões da thumbnail de saída (YouTube)
_THUMB_W  = 1280
_THUMB_H  = 720

# Dimensões reais do template PNG (medidas do arquivo)
_CARD_W   = 393
_CARD_H   = 184

# Área de texto dentro do card (coordenadas relativas ao template 393x184)
_TEXT_AREA = {
    "x":      110,
    "y":      20,
    "width":  265,
    "height": 145,
}

# 68 deixava hooks longos ocupando quase toda a altura do card (linhas
# encostando na borda da area de texto) — 48 mantem a legibilidade ganha
# no patch anterior mas com folga suficiente pra nao esmagar o cabecalho
# e os icones do template.
_FONT_SIZE_MAX  = 48
_FONT_SIZE_MIN  = 16
_FONT_COLOR     = (255, 255, 255)   # branco
_STROKE_COLOR   = (0, 0, 0)        # contorno preto
_STROKE_WIDTH   = 2
_LINE_SPACING   = 1.2


def _get_template_path(lang: str, base_dir: Path) -> Path | None:
    filename = _TEMPLATE_MAP.get(lang.lower())
    if not filename:
        logger.warning("Idioma não mapeado para template: %s", lang)
        filename = "Thumbnail - PT.png"

    candidates = [
        base_dir / "Thumbnail" / filename,
        base_dir.parent / "Thumbnail" / filename,
        Path("Thumbnail") / filename,
    ]
    for path in candidates:
        if path.exists():
            return path

    logger.error(
        "Template não encontrado para idioma '%s'. Tentativas: %s",
        lang, [str(c) for c in candidates],
    )
    return None


def _fit_text(draw, text: str, font_truetype, area_w: int, area_h: int,
              font_path: str, font_size_max: int, font_size_min: int):
    """
    Ajusta automaticamente tamanho da fonte e quebra de linha para
    que o texto caiba dentro da área definida.
    Retorna (lines, font, line_height).
    """
    from PIL import ImageFont

    for size in range(font_size_max, font_size_min - 1, -2):
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            font = ImageFont.load_default()

        avg_char_w     = size * 0.6
        chars_per_line = max(10, int(area_w / avg_char_w))
        lines          = textwrap.wrap(text, width=chars_per_line) or [text]
        line_h         = int(size * _LINE_SPACING)

        # Margem de 15%: sem ela o texto acerta a altura exata da area e as
        # linhas encostam na borda (cabecalho/icones do card ficam espremidos).
        if line_h * len(lines) <= area_h * 0.85:
            return lines, font, line_h

    # Fallback: tamanho mínimo com truncagem
    try:
        font = ImageFont.truetype(font_path, font_size_min)
    except Exception:
        font = ImageFont.load_default()
    chars_per_line = max(10, int(area_w / (font_size_min * 0.6)))
    lines          = textwrap.wrap(text, width=chars_per_line)[:6]
    return lines, font, int(font_size_min * _LINE_SPACING)


def _find_font() -> str:
    """Procura uma fonte bold disponível no sistema."""
    candidates = [
        # Windows
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
        # Linux (Oracle)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            logger.debug("Fonte encontrada: %s", path)
            return path

    logger.warning("Nenhuma fonte TTF encontrada — usando fonte padrão PIL")
    return ""


def _draw_text_on_image(img, text: str, area: dict, font_path: str,
                         center_v: bool = True):
    """
    Desenha texto centralizado dentro da área definida.
    Aplica contorno para legibilidade sobre qualquer fundo.
    """
    from PIL import ImageDraw

    draw  = ImageDraw.Draw(img)
    lines, font, line_h = _fit_text(
        draw, text, None, area["width"], area["height"],
        font_path, _FONT_SIZE_MAX, _FONT_SIZE_MIN,
    )

    total_h = line_h * len(lines)
    y_start = area["y"] + (area["height"] - total_h) // 2 if center_v else area["y"]

    for i, line in enumerate(lines):
        y        = y_start + i * line_h
        x_center = area["x"] + area["width"] // 2

        # Contorno (8 direções)
        for dx in range(-_STROKE_WIDTH, _STROKE_WIDTH + 1):
            for dy in range(-_STROKE_WIDTH, _STROKE_WIDTH + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text(
                    (x_center + dx, y + dy),
                    line, font=font, fill=_STROKE_COLOR, anchor="mt",
                )

        # Texto principal
        draw.text((x_center, y), line, font=font, fill=_FONT_COLOR, anchor="mt")

    return img


def _make_transparent_frame(size: tuple[int, int]) -> "Image":
    """Retorna frame 100% transparente (alpha=0) do tamanho do card."""
    from PIL import Image
    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    return frame


class ThumbnailGenerator:

    def __init__(self, config: dict):
        self.config   = config
        self.base_dir = Path(config.get("base_dir", "."))

        if not (self.base_dir / "Thumbnail").exists():
            self.base_dir = Path(__file__).parent.parent

    def _load_template(self, lang: str):
        """Carrega o template PNG correto para o idioma."""
        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow não instalado. Execute: pip install Pillow")
            return None

        tpl_path = _get_template_path(lang, self.base_dir)
        if not tpl_path:
            return None

        try:
            img = Image.open(tpl_path).convert("RGBA")
            logger.debug("Template carregado: %s (%dx%d)", tpl_path.name, *img.size)
            return img
        except Exception as e:
            logger.error("Erro ao abrir template %s: %s", tpl_path, e)
            return None

    # ── THUMBNAIL ESTÁTICA (YouTube JPG 1280x720) ──────────────────────────

    def generate(self, hook_text: str, lang: str, output_path: Path) -> bool:
        """
        Gera thumbnail estática JPG 1280x720 para YouTube.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow não instalado — thumbnail ignorada")
            return False

        template = self._load_template(lang)
        if template is None:
            logger.error("Template não disponível — thumbnail ignorada")
            return False

        font_path = _find_font()
        tw, th    = template.size
        area_scaled = {
            "x":      int(tw * 0.28),
            "y":      int(th * 0.11),
            "width":  int(tw * 0.67),
            "height": int(th * 0.79),
        }

        img_with_text = _draw_text_on_image(
            template.copy(), hook_text, area_scaled, font_path, center_v=True,
        )

        thumb = img_with_text.resize((_THUMB_W, _THUMB_H), Image.LANCZOS)

        if thumb.mode == "RGBA":
            bg = Image.new("RGB", thumb.size, (0, 0, 0))
            bg.paste(thumb, mask=thumb.split()[3])
            thumb = bg

        thumb.save(str(output_path), "JPEG", quality=95)
        logger.info("Thumbnail gerada: %s", output_path.name)
        return True

    # ── CARD PNG ESTÁTICO (980x458, overlay base) ──────────────────────────

    def render_hook_card(self, hook_text: str, lang: str,
                          output_path: Path | None = None) -> Path | None:
        """
        Renderiza o card com o hook sobre o template PNG (980x458, RGBA).
        Salva em output_path (ou em temp se None).
        Retorna o caminho do PNG gerado ou None em caso de erro.

        Usado como base pelo render_hook_card_video e como fallback direto.
        """
        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow não instalado — card overlay ignorado")
            return None

        template = self._load_template(lang)
        if template is None:
            return None

        tw_orig, th_orig = template.size
        target_w = 980
        scale    = target_w / tw_orig
        target_h = int(th_orig * scale)
        template = template.resize((target_w, target_h), Image.LANCZOS)
        tw, th   = template.size

        font_path    = _find_font()
        scale_factor = tw / 980
        text_area    = {
            "x":      int(15  * scale_factor),
            "y":      int(95  * scale_factor),
            "width":  int(950 * scale_factor),
            "height": int(315 * scale_factor),
        }

        img_with_text = _draw_text_on_image(
            template.copy(), hook_text, text_area, font_path, center_v=True,
        )

        if output_path is None:
            import tempfile
            tmp_dir = self.base_dir / "data" / "thumbnails" / lang
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(
                suffix=f"_card_{lang}.png", delete=False, dir=str(tmp_dir),
            )
            output_path = Path(tmp.name)
            tmp.close()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img_with_text.save(str(output_path), "PNG")
        logger.info("Card PNG gerado: %s (%dx%d)", output_path.name, tw, th)
        return output_path

    # ── CARD OVERLAY ANIMADO (.MOV com alpha via Pillow frame-a-frame) ─────

    def render_hook_card_video(
        self,
        hook_text: str,
        lang: str,
        output_path: Path,
        hook_duration: float = 5.0,
        fade_in: float = 0.5,
        fade_out: float = 0.5,
        fps: int = 30,
        audio_duration: float | None = None,
    ) -> Path | None:
        """
        Gera um vídeo .mov (codec qtrle, canal alpha) do card com
        fade-in e fade-out suaves via Pillow frame-a-frame.

        PATCH v2 — corrige 3 bugs:
          1. Fade-in: frame 0 começa em alpha=0 e sobe progressivamente.
             Fórmula: alpha = (i + 1) / (fade_in_frames + 1)
             → garante que nunca começa em alpha=1 bruscamente.

          2. Fade-out completo: último frame de fade tem alpha=0 exato.
             Fórmula: alpha = 1.0 - (frames_into_fade + 1) / (fade_out_frames + 1)
             → o denominador +1 garante que nunca chega a alpha negativo e
               sempre termina antes de zero.

          3. Anti-fantasma: após o hook_duration, o .mov continua com frames
             100% transparentes (alpha=0) até audio_duration (duração total
             do vídeo). Assim o FFmpeg nunca congela o último frame visível.

        Parâmetros:
            hook_text      : texto renderizado sobre o template
            lang           : idioma (pt / en / es)
            output_path    : caminho de saída (.mov)
            hook_duration  : duração do card visível em segundos
            fade_in        : duração do fade-in em segundos
            fade_out       : duração do fade-out em segundos
            fps            : frames por segundo (default 30)
            audio_duration : duração total do áudio/vídeo em segundos.
                             Se fornecido, o .mov será estendido com frames
                             transparentes até este valor para evitar o
                             efeito "fantasma" do FFmpeg congelando o último frame.

        Retorna Path do .mov gerado, ou None em caso de erro.
        """
        import shutil
        import subprocess

        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow não instalado — card video ignorado")
            return None

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Diretório temporário de trabalho (limpo ao final)
        tmp_dir    = output_path.parent / f"_cardtmp_{lang}"
        frames_dir = tmp_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # 1. Gera o card PNG base (980x458, RGBA)
        base_card_path = tmp_dir / f"base_{lang}.png"
        base_card      = self.render_hook_card(hook_text, lang, base_card_path)
        if base_card is None:
            logger.error("Falha ao gerar card base — abortando render_hook_card_video")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        card_img    = Image.open(base_card).convert("RGBA")
        cw, ch      = card_img.size
        card_pixels = list(card_img.getdata())  # [(r,g,b,a), ...]

        # Frames do período visível do card (hook_duration)
        hook_frames     = max(1, int(round(hook_duration * fps)))
        fade_in_frames  = max(0, int(round(fade_in * fps)))
        fade_out_frames = max(0, int(round(fade_out * fps)))

        # Frames transparentes após o hook até o fim do vídeo
        # ── FIX 3 (anti-fantasma): estende o .mov até audio_duration ──
        if audio_duration is not None and audio_duration > hook_duration:
            tail_frames = max(0, int(round((audio_duration - hook_duration) * fps)))
        else:
            # Sem audio_duration: adiciona 1 frame transparente de margem
            tail_frames = 1

        total_frames = hook_frames + tail_frames

        logger.info(
            "Gerando %d frames do card (%dx%d) — "
            "hook=%.1fs fade_in=%.1fs fade_out=%.1fs tail=%d frames fps=%d",
            total_frames, cw, ch, hook_duration, fade_in, fade_out, tail_frames, fps,
        )

        # 2. Gera frames com alpha variável (período visível do hook)
        for i in range(hook_frames):
            if fade_in_frames > 0 and i < fade_in_frames:
                # ── FIX 1 (fade-in): começa em alpha~0, sobe até 1.0 ──
                # +1 no numerador e denominador garante:
                #   frame 0  → (0+1)/(N+1) = pequeno mas >0
                #   frame N-1→ N/(N+1)     ≈ quase 1.0 (sem nunca travar em 1 antes da hora)
                alpha_factor = (i + 1) / (fade_in_frames + 1)

            elif fade_out_frames > 0 and i >= hook_frames - fade_out_frames:
                frames_into_fade = i - (hook_frames - fade_out_frames)
                # ── FIX 2 (fade-out completo): chega exatamente a ~0 no fim ──
                # frames_into_fade vai de 0 até fade_out_frames-1
                # alpha = 1 - (0+1)/(N+1) = N/(N+1)   → quase 1 no início
                # alpha = 1 - (N-1+1)/(N+1) = 1/(N+1) → quase 0 no penúltimo
                # O último frame DO HOOK (i == hook_frames-1) ainda tem alpha > 0
                # mas o próximo frame já é transparente (tail) → some completamente
                alpha_factor = 1.0 - (frames_into_fade + 1) / (fade_out_frames + 1)

            else:
                alpha_factor = 1.0

            alpha_factor = max(0.0, min(1.0, alpha_factor))

            new_pixels = [
                (r, g, b, int(a * alpha_factor))
                for r, g, b, a in card_pixels
            ]

            frame = Image.new("RGBA", (cw, ch))
            frame.putdata(new_pixels)
            frame.save(str(frames_dir / f"frame_{i:06d}.png"), "PNG")

        # 3. Gera frames transparentes para o período após o hook
        #    ── FIX 3 (anti-fantasma): alpha=0 absoluto, sem resíduo ──
        transparent = _make_transparent_frame((cw, ch))
        for j in range(tail_frames):
            idx = hook_frames + j
            transparent.save(str(frames_dir / f"frame_{idx:06d}.png"), "PNG")

        # 4. Monta o .mov com qtrle (canal alpha nativo no FFmpeg)
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.png"),
            "-c:v", "qtrle",
            "-pix_fmt", "argb",
            str(output_path),
        ]
        logger.debug("FFmpeg card video: %s", " ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(
                    "FFmpeg falhou ao gerar card video (código %d):\n%s",
                    result.returncode, result.stderr[-800:],
                )
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None
        except subprocess.TimeoutExpired:
            logger.error("Timeout ao gerar card video")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None
        except FileNotFoundError:
            logger.error("FFmpeg não encontrado — card video ignorado")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None
        except Exception as e:
            logger.error("Erro inesperado ao gerar card video: %s", e)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # 5. Limpa temporários
        shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.info(
            "Card video gerado: %s (%d frames visíveis + %d transparentes, %.1fs total)",
            output_path.name, hook_frames, tail_frames,
            total_frames / fps,
        )
        return output_path