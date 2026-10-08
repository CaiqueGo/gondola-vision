"""Os tipos da deteccao.

A deteccao devolve **caixa, nunca identidade**. Nada aqui sabe qual SKU esta
dentro do crop — isso e a Parte 5. O que este modulo garante e que cada crop salvo
em disco carrega de onde veio: qual foto (com hash), qual detector (com hash dos
pesos), qual caixa e em que fileira da gondola. A Parte 3 rotula esses crops, a
Parte 11 usa a fileira e a Parte 13 conta facings a partir deles.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Caixa(BaseModel):
    """Uma caixa como o detector devolve: pixels da foto, em ponto flutuante.

    ``(x1, y1)`` e o canto superior esquerdo e ``(x2, y2)`` o inferior direito. As
    coordenadas podem sair um pouco fora da foto — detector nenhum promete o
    contrario —, e e o recorte que ajusta.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float
    confianca: float = Field(ge=0, le=1)

    @property
    def altura(self) -> float:
        return self.y2 - self.y1

    @property
    def centro_y(self) -> float:
        return (self.y1 + self.y2) / 2


class Crop(BaseModel):
    """Um facing recortado e salvo em disco.

    ``fileira`` e ``posicao`` comecam em 1: fileira 1 e a prateleira mais alta,
    posicao 1 e o produto mais a esquerda dela. E a ordem de leitura de quem esta
    na frente da gondola, e e o que a Parte 11 precisa para olhar o vizinho.
    """

    model_config = ConfigDict(extra="forbid")

    arquivo: str = Field(description="Nome do PNG dentro do diretorio desta foto.")
    fileira: int = Field(ge=1)
    posicao: int = Field(ge=1)
    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    x2: int = Field(gt=0)
    y2: int = Field(gt=0)
    confianca: float = Field(ge=0, le=1)


class ManifestoDeteccao(BaseModel):
    """O registro de uma rodada de deteccao sobre uma foto.

    E gravado **por ultimo**, depois de todos os crops. A presenca dele e o que
    diz que a rodada terminou: diretorio com crops e sem manifesto e sobra de uma
    execucao interrompida.
    """

    model_config = ConfigDict(extra="forbid")

    versao_schema: int = 1
    foto: str = Field(description="Nome do arquivo de origem.")
    foto_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    largura: int = Field(gt=0, description="Largura da foto ja na orientacao correta.")
    altura: int = Field(gt=0, description="Altura da foto ja na orientacao correta.")
    girada_pelo_exif: bool = Field(
        description="Se a foto precisou ser girada pela orientacao EXIF antes de detectar.",
    )
    detector: str = Field(description="O que detectou, ex.: 'yolo:sku110k.pt'.")
    pesos_sha256: str | None = Field(
        default=None,
        description="Hash dos pesos do detector. Nulo so para detector sem arquivo de pesos.",
    )
    confianca_minima: float = Field(ge=0, le=1)
    lado_minimo: int = Field(gt=0)
    detectado_em: datetime
    crops: list[Crop] = Field(default_factory=list)
    descartadas_confianca: int = Field(
        default=0, ge=0, description="Caixas abaixo de confianca_minima."
    )
    descartadas_pequenas: int = Field(
        default=0, ge=0, description="Caixas com algum lado abaixo de lado_minimo."
    )
    descartadas_fora: int = Field(
        default=0, ge=0, description="Caixas sem area dentro da foto."
    )

    @property
    def fileiras(self) -> int:
        return max((c.fileira for c in self.crops), default=0)
