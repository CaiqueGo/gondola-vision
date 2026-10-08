"""Da foto aos crops: filtrar caixas, ordenar por fileira, recortar e registrar.

Tudo aqui recebe o detector e os caminhos por parametro, como na Parte 1. E o que
permite testar o recorte inteiro com um detector falso em ``tmp_path``.

O que este modulo decide, e por que:

- **Orientacao EXIF antes de tudo.** Foto de celular costuma vir gravada de lado,
  com uma etiqueta dizendo "gire 90 graus para mostrar". O Pillow nao aplica essa
  etiqueta sozinho. Sem girar, o detector ve a gondola deitada e as caixas saem
  em coordenadas que nao batem com o que voce ve na tela.
- **Corte de confianca aqui, nao no detector.** O detector entrega quase tudo; o
  corte e aplicado aqui para o manifesto contar o que ficou de fora.
- **Caixa minuscula e descartada.** Abaixo de ``lado_minimo`` pixels nao ha
  rotulo legivel, e o encoder da Parte 4 so veria borrao.
- **PNG, nao JPEG.** A foto ja passou por uma compressao com perda no celular.
  Salvar o crop em JPEG somaria uma segunda, que nao existe na prateleira de
  verdade e que o encoder aprenderia como se fosse sinal.
"""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from gondola.catalogo.manifesto import sha256_arquivo
from gondola.deteccao.detector import Detector, ErroDeteccao
from gondola.deteccao.modelos import Caixa, Crop, ManifestoDeteccao

CONFIANCA_MINIMA_PADRAO = 0.25
LADO_MINIMO_PADRAO = 24

FRACAO_TOLERANCIA_FILEIRA = 0.5
"""Quanto o centro vertical de uma caixa pode se afastar da fileira e ainda ser dela.

Medido em alturas tipicas (a mediana das caixas). Meia altura separa duas
prateleiras — que ficam a pelo menos uma altura de produto de distancia — e
tolera o desalinhamento natural de produtos de alturas diferentes lado a lado.
"""

NOME_MANIFESTO = "deteccao.json"
NOME_ANOTADA = "anotada.jpg"
_ORIENTACAO_EXIF = 0x0112

_CORES_FILEIRA = [
    (230, 25, 75),
    (60, 180, 75),
    (0, 130, 200),
    (245, 130, 48),
    (145, 30, 180),
    (70, 240, 240),
]


def abrir_foto(caminho: Path) -> tuple[Image.Image, bool]:
    """Abre a foto em RGB e ja na orientacao correta.

    Devolve a imagem e se ela precisou ser girada pela etiqueta EXIF.
    """
    try:
        with Image.open(caminho) as bruta:
            girada = bruta.getexif().get(_ORIENTACAO_EXIF, 1) != 1
            imagem = ImageOps.exif_transpose(bruta).convert("RGB")
    except (UnidentifiedImageError, OSError) as erro:
        raise ErroDeteccao(f"nao e imagem legivel: {caminho}") from erro
    return imagem, girada


def ajustar_a_foto(caixa: Caixa, largura: int, altura: int) -> Caixa | None:
    """Arredonda a caixa para pixels inteiros e corta o que sair da foto.

    Arredonda para fora (``floor`` no canto de cima, ``ceil`` no de baixo): um
    pixel a mais de borda nao atrapalha ninguem, um pixel a menos pode cortar o
    rotulo. Devolve None se nao sobrar area dentro da foto.
    """
    x1 = max(0, math.floor(caixa.x1))
    y1 = max(0, math.floor(caixa.y1))
    x2 = min(largura, math.ceil(caixa.x2))
    y2 = min(altura, math.ceil(caixa.y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return Caixa(x1=x1, y1=y1, x2=x2, y2=y2, confianca=caixa.confianca)


def agrupar_em_fileiras(caixas: list[Caixa]) -> list[list[Caixa]]:
    """Agrupa as caixas em fileiras (de cima para baixo) e ordena cada uma da esquerda.

    Varre as caixas pelo centro vertical; uma caixa entra na fileira corrente se o
    centro dela estiver a no maximo ``FRACAO_TOLERANCIA_FILEIRA`` alturas tipicas
    da media da fileira, e abre uma fileira nova se nao estiver.

    Onde falha: foto muito inclinada, em que a mesma prateleira desce da esquerda
    para a direita mais de meia altura de produto. Nesse caso a fileira se parte
    em duas — a anotada.jpg mostra isso pelas cores.
    """
    if not caixas:
        return []
    tolerancia = statistics.median(c.altura for c in caixas) * FRACAO_TOLERANCIA_FILEIRA

    fileiras: list[list[Caixa]] = []
    centros: list[float] = []
    for caixa in sorted(caixas, key=lambda c: (c.centro_y, c.x1)):
        if fileiras and abs(caixa.centro_y - centros[-1]) <= tolerancia:
            fileiras[-1].append(caixa)
            centros[-1] = statistics.fmean(c.centro_y for c in fileiras[-1])
        else:
            fileiras.append([caixa])
            centros.append(caixa.centro_y)

    return [sorted(fileira, key=lambda c: (c.x1, c.y1)) for fileira in fileiras]


def nome_do_crop(fileira: int, posicao: int) -> str:
    """Nome estavel do arquivo: a ordem de leitura da gondola, nao a do detector."""
    return f"f{fileira:02d}-p{posicao:03d}.png"


def _limpar_saida_anterior(destino: Path) -> None:
    """Apaga so o que uma rodada anterior gerou; qualquer outro arquivo fica."""
    if not destino.is_dir():
        return
    for caminho in destino.glob("f[0-9][0-9]-p[0-9][0-9][0-9].png"):
        caminho.unlink()
    for nome in (NOME_ANOTADA, NOME_MANIFESTO):
        (destino / nome).unlink(missing_ok=True)


def desenhar_anotada(imagem: Image.Image, crops: list[Crop]) -> Image.Image:
    """A foto com as caixas desenhadas, uma cor por fileira.

    E o arquivo para olhar com os olhos: caixa faltando sobre um produto e
    deteccao perdida; duas cores na mesma prateleira e fileira partida.
    """
    anotada = imagem.copy()
    desenho = ImageDraw.Draw(anotada)
    espessura = max(2, round(min(imagem.size) / 400))
    fonte = ImageFont.load_default(size=max(12, imagem.height // 90))
    for crop in crops:
        cor = _CORES_FILEIRA[(crop.fileira - 1) % len(_CORES_FILEIRA)]
        desenho.rectangle((crop.x1, crop.y1, crop.x2, crop.y2), outline=cor, width=espessura)
        desenho.text(
            (crop.x1 + espessura, crop.y1 + espessura),
            f"{crop.fileira}.{crop.posicao}",
            fill=cor,
            font=fonte,
        )
    return anotada


def detectar_e_recortar(
    foto: Path,
    detector: Detector,
    dir_saida: Path,
    *,
    confianca_minima: float = CONFIANCA_MINIMA_PADRAO,
    lado_minimo: int = LADO_MINIMO_PADRAO,
    substituir: bool = False,
) -> ManifestoDeteccao:
    """Detecta os produtos de uma foto e salva um crop por facing.

    Grava em ``dir_saida/<nome da foto sem extensao>/``: os crops, a
    ``anotada.jpg`` e, por ultimo, o ``deteccao.json``.

    Recusa sobrescrever uma rodada ja concluida sem ``substituir=True``. Os
    rotulos da Parte 3 apontam para estes arquivos pelo nome; refazer a deteccao
    em silencio poderia trocar o produto que esta por tras de um nome ja rotulado.
    """
    destino = dir_saida / foto.stem
    if (destino / NOME_MANIFESTO).exists() and not substituir:
        raise ErroDeteccao(
            f"{foto.name} ja foi detectada em {destino} (use --substituir para refazer)"
        )

    imagem, girada = abrir_foto(foto)
    largura, altura = imagem.size

    aceitas: list[Caixa] = []
    descartadas_confianca = descartadas_pequenas = descartadas_fora = 0
    for caixa in detector.detectar(imagem):
        if caixa.confianca < confianca_minima:
            descartadas_confianca += 1
            continue
        ajustada = ajustar_a_foto(caixa, largura, altura)
        if ajustada is None:
            descartadas_fora += 1
            continue
        if min(ajustada.x2 - ajustada.x1, ajustada.altura) < lado_minimo:
            descartadas_pequenas += 1
            continue
        aceitas.append(ajustada)

    crops = [
        Crop(
            arquivo=nome_do_crop(n_fileira, n_posicao),
            fileira=n_fileira,
            posicao=n_posicao,
            x1=int(caixa.x1),
            y1=int(caixa.y1),
            x2=int(caixa.x2),
            y2=int(caixa.y2),
            confianca=caixa.confianca,
        )
        for n_fileira, fileira in enumerate(agrupar_em_fileiras(aceitas), start=1)
        for n_posicao, caixa in enumerate(fileira, start=1)
    ]

    manifesto = ManifestoDeteccao(
        foto=foto.name,
        foto_sha256=sha256_arquivo(foto),
        largura=largura,
        altura=altura,
        girada_pelo_exif=girada,
        detector=detector.descricao,
        pesos_sha256=detector.pesos_sha256,
        confianca_minima=confianca_minima,
        lado_minimo=lado_minimo,
        detectado_em=datetime.now(UTC),
        crops=crops,
        descartadas_confianca=descartadas_confianca,
        descartadas_pequenas=descartadas_pequenas,
        descartadas_fora=descartadas_fora,
    )

    # So mexe no disco depois que a deteccao deu certo: uma falha acima deixa a
    # rodada anterior intacta.
    _limpar_saida_anterior(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for crop in crops:
        imagem.crop((crop.x1, crop.y1, crop.x2, crop.y2)).save(destino / crop.arquivo)
    desenhar_anotada(imagem, crops).save(destino / NOME_ANOTADA, quality=85)
    (destino / NOME_MANIFESTO).write_text(manifesto.model_dump_json(indent=2), encoding="utf-8")
    return manifesto
