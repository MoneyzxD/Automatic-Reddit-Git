from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pytest

from stages.thumbnail import ThumbnailGenerator, _find_font, _fit_text, _load_font


def test_fit_respeita_largura_real_das_letras():
    draw = ImageDraw.Draw(Image.new("RGB", (800, 400)))
    title = "WWW WWW WWW WWW WWW WWW WWW WWW"
    lines, font, line_h = _fit_text(
        draw, title, None, 300, 250, _find_font(), 48, 16,
    )
    assert " ".join(lines) == title
    assert all(draw.textbbox((0, 0), line, font=font)[2] <= 300 for line in lines)
    assert len(lines) * line_h <= 250


def test_fonte_padrao_versionada_funciona_em_todos_os_sistemas():
    font_path = Path(_find_font())
    assert font_path.name == "Inter.ttf"
    assert ImageFont.truetype(str(font_path), 44).getname()[0] == "Inter"


def test_fonte_ausente_mantem_tamanho_legivel(tmp_path):
    font = _load_font(str(tmp_path / "inexistente.ttf"), 44)
    left, top, right, bottom = font.getbbox("Título")
    assert right - left > 70
    assert bottom - top >= 30


@pytest.mark.parametrize("title", [
    "Recusei hospedar o namorado da minha colega e ela passou a me tratar como inimiga",
    "I refused to let my roommate's boyfriend stay in our home and she turned against me",
    "Me negué a alojar al novio de mi compañera y ella empezó a tratarme como una enemiga",
])
def test_titulos_com_acentos_cabem_sem_perder_palavras(title):
    draw = ImageDraw.Draw(Image.new("RGB", (780, 364)))
    lines, font, line_h = _fit_text(draw, title, None, 708, 188, _find_font(), 44, 22)
    assert " ".join(lines) == title
    assert line_h * len(lines) <= 188
    assert all(draw.textlength(line, font=font) <= 708 for line in lines)


def test_card_usa_toda_a_largura_disponivel_para_o_texto():
    draw = ImageDraw.Draw(Image.new("RGB", (780, 364)))
    title = (
        "Cortei o apoio financeiro de quinze mil reais ao filho quando descobri "
        "que a cirurgia que ele dizia precisar nunca existia."
    )

    lines, font, _ = _fit_text(draw, title, None, 708, 188, _find_font(), 44, 22)

    assert max(draw.textlength(line, font=font) for line in lines) > 650


def test_card_mantem_dimensoes_e_transparencia(tmp_path):
    generator = ThumbnailGenerator({})
    output = tmp_path / "card.png"
    generator.render_hook_card(
        "Neguei um terno azul ao meu filho para o casamento da minha enteada", "pt", output,
    )
    with Image.open(output) as card:
        assert card.size == (780, 364)
        assert card.mode == "RGBA"
        assert card.getpixel((0, 0))[3] < 255


def test_thumbnail_vertical_para_shorts(tmp_path):
    generator = ThumbnailGenerator({})
    for lang in ("pt", "en", "es"):
        output = tmp_path / f"thumb_{lang}.jpg"
        assert generator.generate("Uma escolha que dividiu minha família", lang, output)
        with Image.open(output) as thumbnail:
            assert thumbnail.size == (1080, 1920)
            assert thumbnail.mode == "RGB"
        assert output.stat().st_size < 2 * 1024 * 1024
