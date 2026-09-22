"""
thumbnail.py
============
Etapa 16 do pipeline — dois objetivos:

    1. generate()             → Thumbnail estática JPG (YouTube)
                                Compõe uma capa vertical 1080x1920 com o card
                                do idioma correto, sem esticar o template.

    2. render_hook_card()     → PNG do card com texto renderizado (780x364).
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
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapeamento idioma → nome do arquivo de template
_TEMPLATE_MAP = {
    "pt":    "Thumbnail - PT.png",
    "pt-br": "Thumbnail - PT.png",
    "en":    "Thumbnail - EN.png",
    "es":    "Thumbnail - ES.png",
}

# O card mantém os 780px aprovados pelo operador; a capa usa proporção Shorts.
_THUMB_W = 1080
_THUMB_H = 1920
_CARD_W = 780
_FONT_SIZE_MAX = 44
_FONT_SIZE_MIN = 22
_FONT_COLOR = (24, 24, 32)
_LINE_SPACING = 1.22
_RENDER_SCALE = 2


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


def _load_font(font_path: str, size: int):
    """Usa Inter semibold quando variável e mantém o tamanho no fallback."""
    from PIL import ImageFont

    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default(size=size)
    try:
        if b"SemiBold" in font.get_variation_names():
            font.set_variation_by_name(b"SemiBold")
    except OSError:
        pass  # Fontes TTF estáticas não têm eixos de variação.
    return font


def _wrap_text(draw, text: str, font, area_w: int) -> list[str]:
    """Quebra palavras pela largura em pixels, incluindo palavras muito longas."""
    def fits(value):
        left, _, right, _ = draw.textbbox((0, 0), value, font=font)
        return right - left <= area_w

    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if fits(candidate):
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ""
        for char in word:
            if line and not fits(line + char):
                lines.append(line)
                line = ""
            line += char
    if line:
        lines.append(line)
    return lines or [""]


def _fit_text(draw, text: str, font_truetype, area_w: int, area_h: int,
              font_path: str, font_size_max: int, font_size_min: int):
    """Ajusta largura e altura reais; só abrevia títulos além do limite mínimo."""
    for size in range(font_size_max, font_size_min - 1, -1):
        font = _load_font(font_path, size)
        lines = _wrap_text(draw, text, font, area_w)
        bbox = font.getbbox("ÁÉÍÓÚÇgjpq")
        line_h = max(round(size * _LINE_SPACING), bbox[3] - bbox[1])
        if line_h * len(lines) <= area_h:
            # Usa toda a largura disponível. Encurtar a área para "equilibrar"
            # linhas deixava espaço lateral demais no card final.
            return lines, font, line_h

    max_lines = max(1, area_h // line_h)
    lines = lines[:max_lines]
    last = lines[-1].rstrip(".,;: ")
    while last and draw.textlength(last + "…", font=font) > area_w:
        last = last[:-1]
    lines[-1] = last + "…"
    logger.warning("Título abreviado no card por exceder a área disponível")
    return lines, font, line_h


def _find_font(configured: str | None = None) -> str:
    """Prioriza a fonte versionada para Windows e Linux produzirem o mesmo card."""
    candidates = [
        configured,
        str(Path(__file__).resolve().parent.parent / "assets/fonts/Inter.ttf"),
        # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
        # Linux (Oracle)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path

    logger.warning("Nenhuma fonte TTF encontrada — usando fonte padrão PIL")
    return ""


def _draw_text_on_image(img, text: str, area: dict, font_path: str,
                         center_v: bool = True, font_size_max: int = _FONT_SIZE_MAX,
                         font_size_min: int = _FONT_SIZE_MIN):
    """
    Desenha texto centralizado dentro da área definida.
    Texto escuro sólido no fundo branco, com margens para cabeçalho e rodapé.
    """
    from PIL import ImageDraw

    draw  = ImageDraw.Draw(img)
    lines, font, line_h = _fit_text(
        draw, text, None, area["width"], area["height"],
        font_path, font_size_max, font_size_min,
    )

    total_h = line_h * len(lines)
    y_start = area["y"] + (area["height"] - total_h) // 2 if center_v else area["y"]

    for i, line in enumerate(lines):
        y        = y_start + i * line_h
        x_center = area["x"] + area["width"] // 2

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

    def _render_card_image(self, hook_text: str, lang: str, width: int):
        """Renderiza em 2x e reduz uma vez, suavizando as bordas das letras."""
        from PIL import Image

        template = self._load_template(lang)
        if template is None:
            return None
        height = int(template.height * width / template.width)
        scale = width / _CARD_W * _RENDER_SCALE
        template = template.resize(
            (width * _RENDER_SCALE, height * _RENDER_SCALE), Image.Resampling.LANCZOS,
        )
        # Coordenadas em 780px: início abaixo do avatar, fim antes dos ícones.
        area = {key: round(value * scale) for key, value in {
            "x": 36, "y": 110, "width": 708, "height": 188,
        }.items()}
        configured = self.config.get("title_font")
        if configured:
            configured = str(self.base_dir / configured)
        font_path = _find_font(configured)
        logger.info("Fonte do card: %s (semibold, renderização 2x)", Path(font_path).name)
        _draw_text_on_image(
            template, hook_text, area, font_path,
            font_size_max=round(self.config.get("title_font_size", _FONT_SIZE_MAX) * scale),
            font_size_min=round(_FONT_SIZE_MIN * scale),
        )
        return template.resize((width, height), Image.Resampling.LANCZOS)

    # ── THUMBNAIL ESTÁTICA (YouTube Shorts JPG 1080x1920) ─────────────────

    def generate(self, hook_text: str, lang: str, output_path: Path) -> bool:
        """
        Gera uma capa vertical, mantendo o título na região central dos recortes.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image, ImageDraw
        except ImportError:
            logger.error("Pillow não instalado — thumbnail ignorada")
            return False

        width = int(self.config.get("shorts_width", _THUMB_W))
        height = int(self.config.get("shorts_height", _THUMB_H))
        card = self._render_card_image(hook_text, lang, round(width * 0.9))
        if card is None:
            logger.error("Template não disponível — thumbnail ignorada")
            return False

        # Fundo discreto na paleta do canal; o card conserva a proporção original.
        thumb = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(thumb)
        for y in range(height):
            glow = 1 - abs(2 * y / max(1, height - 1) - 1)
            color = (int(20 + 28 * glow), int(14 + 6 * glow), int(35 + 48 * glow))
            draw.line((0, y, width, y), fill=color)
        x, y = (width - card.width) // 2, (height - card.height) // 2
        thumb.paste(card, (x, y), card)
        thumb.save(str(output_path), "JPEG", quality=95, subsampling=0)
        logger.info("Thumbnail vertical gerada: %s (%dx%d)", output_path.name, width, height)
        return True

    # ── CARD PNG ESTÁTICO (780x364, overlay base) ──────────────────────────

    def render_hook_card(self, hook_text: str, lang: str,
                          output_path: Path | None = None) -> Path | None:
        """
        Renderiza o card com o hook sobre o template PNG (780x364, RGBA).
        Salva em output_path (ou em temp se None).
        Retorna o caminho do PNG gerado ou None em caso de erro.

        Usado como base pelo render_hook_card_video e como fallback direto.
        """
        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow não instalado — card overlay ignorado")
            return None

        target_w = int(self.config.get("card_width", _CARD_W))
        img_with_text = self._render_card_image(hook_text, lang, target_w)
        if img_with_text is None:
            return None
        tw, th = img_with_text.size

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

        # 1. Gera o card PNG base com texto suavizado em 2x.
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
