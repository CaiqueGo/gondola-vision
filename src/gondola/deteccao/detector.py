"""O detector: imagem entra, caixas saem.

O resto do projeto conversa com um ``Detector`` (o protocolo abaixo), nunca com o
ultralytics diretamente. Dois motivos:

1. O recorte, a ordenacao por fileira e o manifesto sao testaveis com um detector
   falso de tres linhas, sem GPU, sem pesos e sem o ultralytics instalado.
2. Trocar de detector (outro YOLO, outro framework) mexe em uma classe so.

Sobre os pesos: arquivo ``.pt`` e um pickle do PyTorch, e carregar pickle executa
codigo. Pesos de origem desconhecida sao, literalmente, um programa que voce roda
sem ler. Por isso o hash dos pesos vai para o manifesto de cada foto: voce sabe
exatamente qual arquivo produziu cada crop, e uma troca de pesos nunca e
silenciosa.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from PIL import Image

from gondola.catalogo.manifesto import sha256_arquivo
from gondola.deteccao.modelos import Caixa

CONFIANCA_DE_PISO = 0.05
"""Confianca minima pedida ao YOLO.

E baixa de proposito. O corte de verdade (``confianca_minima``) e aplicado depois,
no recorte, para que o manifesto possa contar quantas caixas ficaram abaixo dele.
Esse numero e o que diz se abaixar o limiar recuperaria produto perdido.
"""

MAX_DETECCOES = 1000
"""Teto de caixas por foto.

O padrao do ultralytics e 300, e uma gondola de bebidas fotografada de longe passa
disso. Teto baixo demais corta produto em silencio — o pior tipo de perda, porque
parece que o detector nao viu.
"""


class ErroDeteccao(Exception):
    """Erro esperado da deteccao, com mensagem para o usuario."""


class Detector(Protocol):
    """Qualquer coisa que receba uma foto e devolva caixas."""

    @property
    def descricao(self) -> str:
        """Identificacao curta que vai para o manifesto, ex.: 'yolo:sku110k.pt'."""
        ...

    @property
    def pesos_sha256(self) -> str | None:
        """Hash dos pesos, ou None para detector sem arquivo de pesos."""
        ...

    def detectar(self, imagem: Image.Image) -> list[Caixa]:
        """Caixas em pixels de ``imagem``, ja na orientacao em que ela foi passada."""
        ...


def caixas_de_saida_yolo(xyxy: Sequence[Sequence[float]], conf: Sequence[float]) -> list[Caixa]:
    """Converte as listas que o ultralytics devolve em ``Caixa``.

    Separado da classe para ser testavel sem o ultralytics instalado.
    """
    if len(xyxy) != len(conf):
        raise ErroDeteccao(f"saida do YOLO inconsistente: {len(xyxy)} caixas e {len(conf)} notas")
    return [
        Caixa(x1=x1, y1=y1, x2=x2, y2=y2, confianca=c)
        for (x1, y1, x2, y2), c in zip(xyxy, conf, strict=True)
    ]


class DetectorYolo:
    """YOLO do ultralytics, carregado de um arquivo de pesos local."""

    def __init__(self, pesos: Path, *, tamanho_entrada: int = 640) -> None:
        if not pesos.is_file():
            raise ErroDeteccao(
                f"pesos do detector nao encontrados: {pesos} "
                "(veja docs/partes/02-deteccao.md, secao 'Os pesos')"
            )
        try:
            from ultralytics import YOLO
        except ImportError as erro:
            raise ErroDeteccao(
                "ultralytics nao esta instalado; rode: uv pip install -e \".[dev,deteccao]\""
            ) from erro

        self._pesos_sha256 = sha256_arquivo(pesos)
        self._descricao = f"yolo:{pesos.name}"
        self._tamanho_entrada = tamanho_entrada
        self._modelo = YOLO(str(pesos))

    @property
    def descricao(self) -> str:
        return self._descricao

    @property
    def pesos_sha256(self) -> str | None:
        return self._pesos_sha256

    def detectar(self, imagem: Image.Image) -> list[Caixa]:
        resultado = self._modelo.predict(
            imagem,
            conf=CONFIANCA_DE_PISO,
            imgsz=self._tamanho_entrada,
            max_det=MAX_DETECCOES,
            verbose=False,
        )[0]
        return caixas_de_saida_yolo(
            resultado.boxes.xyxy.tolist(),
            resultado.boxes.conf.tolist(),
        )
