from pathlib import Path

from sync_repo_publico import varrer_segredos


def _copiar_fonte(raiz):
    fonte = raiz / "assets/fonts/Inter.ttf"
    fonte.parent.mkdir(parents=True)
    original = Path(__file__).resolve().parents[1] / "assets/fonts/Inter.ttf"
    fonte.write_bytes(original.read_bytes())
    return fonte


def test_fonte_publica_oficial_nao_gera_falso_positivo(tmp_path):
    _copiar_fonte(tmp_path)
    assert varrer_segredos(tmp_path) == []


def test_fonte_modificada_continua_sendo_verificada(tmp_path):
    fonte = _copiar_fonte(tmp_path)
    # Segredo sintético para verificar que a exceção depende do conteúdo.
    fonte.write_bytes(fonte.read_bytes() + b"\ngsk_" + b"A" * 24)
    assert ("chave Groq", str(fonte.relative_to(tmp_path))) in varrer_segredos(tmp_path)
