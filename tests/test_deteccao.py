"""O recorte da Parte 2, com um detector falso.

Nenhum teste aqui precisa do ultralytics, de pesos ou de GPU. O detector falso
devolve as caixas que o teste mandar, e o que se verifica e tudo o que acontece
depois delas: corte, ordem de leitura, arquivos e manifesto.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from gondola.catalogo.manifesto import sha256_arquivo
from gondola.deteccao.detector import ErroDeteccao, caixas_de_saida_yolo
from gondola.deteccao.modelos import Caixa, ManifestoDeteccao
from gondola.deteccao.recorte import (
    NOME_ANOTADA,
    NOME_MANIFESTO,
    agrupar_em_fileiras,
    ajustar_a_foto,
    detectar_e_recortar,
)

VERMELHO = (200, 0, 0)
VERDE = (0, 200, 0)
AZUL = (0, 0, 200)
CINZA = (128, 128, 128)


class DetectorFalso:
    """Devolve sempre as mesmas caixas e lembra o tamanho da imagem que recebeu."""

    descricao = "falso"
    pesos_sha256 = "a" * 64

    def __init__(self, caixas: list[Caixa]) -> None:
        self.caixas = caixas
        self.tamanho_recebido: tuple[int, int] | None = None

    def detectar(self, imagem: Image.Image) -> list[Caixa]:
        self.tamanho_recebido = imagem.size
        return list(self.caixas)


def caixa(x1: float, y1: float, x2: float, y2: float, confianca: float = 0.9) -> Caixa:
    return Caixa(x1=x1, y1=y1, x2=x2, y2=y2, confianca=confianca)


@pytest.fixture()
def fazer_foto(tmp_path: Path) -> Callable[..., Path]:
    """Gera uma 'gondola' cinza com blocos coloridos nas posicoes pedidas."""
    origem = tmp_path / "fotos"
    origem.mkdir(exist_ok=True)

    def _fazer(
        nome: str = "gondola",
        *,
        largura: int = 400,
        altura: int = 300,
        blocos: list[tuple[tuple[int, int, int, int], tuple[int, int, int]]] | None = None,
    ) -> Path:
        imagem = Image.new("RGB", (largura, altura), CINZA)
        for retangulo, cor in blocos or []:
            imagem.paste(cor, retangulo)
        caminho = origem / f"{nome}.jpg"
        imagem.save(caminho, quality=95)
        return caminho

    return _fazer


@pytest.fixture()
def dir_saida(tmp_path: Path) -> Path:
    return tmp_path / "crops"


def test_salva_um_crop_por_caixa_com_o_conteudo_da_regiao(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto(blocos=[((10, 10, 60, 110), VERMELHO), ((100, 10, 150, 110), AZUL)])
    detector = DetectorFalso([caixa(10, 10, 60, 110), caixa(100, 10, 150, 110)])

    manifesto = detectar_e_recortar(foto, detector, dir_saida)

    assert [c.arquivo for c in manifesto.crops] == ["f01-p001.png", "f01-p002.png"]
    with Image.open(dir_saida / "gondola" / "f01-p001.png") as crop:
        assert crop.size == (50, 100)
        r, g, b = crop.getpixel((25, 50))  # type: ignore[misc]
        assert r > 150 and g < 50 and b < 50, "o primeiro crop deveria ser o bloco vermelho"
    with Image.open(dir_saida / "gondola" / "f01-p002.png") as crop:
        r, g, b = crop.getpixel((25, 50))  # type: ignore[misc]
        assert b > 150 and r < 50, "o segundo crop deveria ser o bloco azul"


def test_crops_sao_numerados_na_ordem_de_leitura_e_nao_na_do_detector(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    baixo_direita = caixa(200, 160, 250, 260)
    cima_direita = caixa(200, 10, 250, 110)
    baixo_esquerda = caixa(20, 160, 70, 260)
    cima_esquerda = caixa(20, 10, 70, 110)
    detector = DetectorFalso([baixo_direita, cima_direita, baixo_esquerda, cima_esquerda])

    manifesto = detectar_e_recortar(foto, detector, dir_saida)

    posicoes = [(c.fileira, c.posicao, c.x1, c.y1) for c in manifesto.crops]
    assert posicoes == [(1, 1, 20, 10), (1, 2, 200, 10), (2, 1, 20, 160), (2, 2, 200, 160)]
    assert manifesto.fileiras == 2


def test_produtos_de_alturas_diferentes_lado_a_lado_ficam_na_mesma_fileira() -> None:
    lata = caixa(0, 60, 40, 120)  # baixa, apoiada na prateleira
    garrafa = caixa(50, 0, 90, 120)  # alta, mesma prateleira
    lata_de_baixo = caixa(0, 200, 40, 260)

    fileiras = agrupar_em_fileiras([lata_de_baixo, garrafa, lata])

    assert fileiras == [[lata, garrafa], [lata_de_baixo]]


def test_caixa_abaixo_da_confianca_e_descartada_e_contada(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detector = DetectorFalso([caixa(10, 10, 60, 110, 0.9), caixa(100, 10, 150, 110, 0.1)])

    manifesto = detectar_e_recortar(foto, detector, dir_saida, confianca_minima=0.25)

    assert len(manifesto.crops) == 1
    assert manifesto.descartadas_confianca == 1


def test_caixa_menor_que_o_lado_minimo_e_descartada_e_contada(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detector = DetectorFalso([caixa(10, 10, 60, 110), caixa(100, 10, 110, 110)])  # 10px de largura

    manifesto = detectar_e_recortar(foto, detector, dir_saida, lado_minimo=24)

    assert len(manifesto.crops) == 1
    assert manifesto.descartadas_pequenas == 1


def test_caixa_que_vaza_a_foto_e_cortada_na_borda() -> None:
    ajustada = ajustar_a_foto(caixa(-5.5, -3.2, 60.1, 410.0), largura=400, altura=300)

    assert ajustada is not None
    assert (ajustada.x1, ajustada.y1, ajustada.x2, ajustada.y2) == (0, 0, 61, 300)


def test_caixa_inteira_fora_da_foto_e_descartada_e_contada(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto(largura=400, altura=300)
    detector = DetectorFalso([caixa(10, 10, 60, 110), caixa(500, 10, 560, 110)])

    manifesto = detectar_e_recortar(foto, detector, dir_saida)

    assert len(manifesto.crops) == 1
    assert manifesto.descartadas_fora == 1


def test_foto_de_celular_e_girada_pelo_exif_antes_de_detectar(
    tmp_path: Path, dir_saida: Path
) -> None:
    # Gravada deitada (400x300) com a etiqueta "gire 90 graus": na tela ela e 300x400.
    foto = tmp_path / "celular.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (400, 300), CINZA).save(foto, exif=exif)
    detector = DetectorFalso([caixa(10, 10, 60, 110)])

    manifesto = detectar_e_recortar(foto, detector, dir_saida)

    assert detector.tamanho_recebido == (300, 400)
    assert (manifesto.largura, manifesto.altura) == (300, 400)
    assert manifesto.girada_pelo_exif is True


def test_foto_sem_exif_nao_e_marcada_como_girada(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    manifesto = detectar_e_recortar(fazer_foto(), DetectorFalso([]), dir_saida)

    assert manifesto.girada_pelo_exif is False


def test_manifesto_em_disco_registra_foto_pesos_e_caixas(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detector = DetectorFalso([caixa(10, 10, 60, 110, 0.87)])

    detectar_e_recortar(foto, detector, dir_saida, confianca_minima=0.3)

    destino = dir_saida / "gondola"
    lido = ManifestoDeteccao.model_validate(
        json.loads((destino / NOME_MANIFESTO).read_text(encoding="utf-8"))
    )
    assert lido.foto == "gondola.jpg"
    assert lido.foto_sha256 == sha256_arquivo(foto)
    assert lido.pesos_sha256 == "a" * 64
    assert lido.detector == "falso"
    assert lido.confianca_minima == 0.3
    assert (lido.crops[0].x1, lido.crops[0].y2, lido.crops[0].confianca) == (10, 110, 0.87)
    assert (destino / NOME_ANOTADA).is_file()


def test_foto_sem_nenhuma_caixa_gera_manifesto_vazio(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    manifesto = detectar_e_recortar(fazer_foto(), DetectorFalso([]), dir_saida)

    assert manifesto.crops == []
    assert manifesto.fileiras == 0
    assert (dir_saida / "gondola" / NOME_MANIFESTO).is_file()


def test_recusa_refazer_foto_ja_detectada_sem_substituir(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detectar_e_recortar(foto, DetectorFalso([caixa(10, 10, 60, 110)]), dir_saida)

    with pytest.raises(ErroDeteccao, match="substituir"):
        detectar_e_recortar(foto, DetectorFalso([caixa(10, 10, 60, 110)]), dir_saida)


def test_substituir_apaga_crops_antigos_mas_preserva_arquivo_alheio(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detectar_e_recortar(
        foto, DetectorFalso([caixa(10, 10, 60, 110), caixa(100, 10, 150, 110)]), dir_saida
    )
    destino = dir_saida / "gondola"
    (destino / "minhas-notas.txt").write_text("nao apagar", encoding="utf-8")

    detectar_e_recortar(foto, DetectorFalso([caixa(10, 10, 60, 110)]), dir_saida, substituir=True)

    assert sorted(p.name for p in destino.glob("f*.png")) == ["f01-p001.png"]
    assert (destino / "minhas-notas.txt").read_text(encoding="utf-8") == "nao apagar"


def test_falha_ao_abrir_a_foto_deixa_a_rodada_anterior_intacta(
    fazer_foto: Callable[..., Path], dir_saida: Path
) -> None:
    foto = fazer_foto()
    detectar_e_recortar(foto, DetectorFalso([caixa(10, 10, 60, 110)]), dir_saida)
    foto.write_bytes(b"isto nao e uma imagem")

    with pytest.raises(ErroDeteccao, match="legivel"):
        detectar_e_recortar(foto, DetectorFalso([]), dir_saida, substituir=True)

    destino = dir_saida / "gondola"
    assert (destino / "f01-p001.png").is_file()
    assert (destino / NOME_MANIFESTO).is_file()


def test_saida_do_yolo_vira_caixas() -> None:
    caixas = caixas_de_saida_yolo([[1.0, 2.0, 30.0, 40.0], [5.0, 6.0, 7.0, 8.0]], [0.9, 0.4])

    assert caixas == [caixa(1, 2, 30, 40, 0.9), caixa(5, 6, 7, 8, 0.4)]


def test_saida_do_yolo_com_listas_de_tamanhos_diferentes_e_erro() -> None:
    with pytest.raises(ErroDeteccao, match="inconsistente"):
        caixas_de_saida_yolo([[1.0, 2.0, 30.0, 40.0]], [0.9, 0.4])
