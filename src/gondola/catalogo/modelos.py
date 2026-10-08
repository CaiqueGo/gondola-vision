"""Os tipos do catalogo.

Por que Pydantic e nao um dicionario solto: o manifesto e um arquivo que voce vai
editar a mao durante meses. Um schema tipado transforma "esqueci a variante" ou
"escrevi o tamanho como texto" em erro na hora de carregar, e nao em bug
silencioso tres partes adiante.

Por que marca/linha/variante/tamanho sao obrigatorios e nao "nice to have": e
deles que sai, de graca, a lista de negativos dificeis da Parte 8. Dois SKUs da
mesma marca e mesma linha que so diferem na variante formam exatamente o par que
o encoder precisa aprender a separar. Cadastro sujo aqui vira treino ruim la.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Forma canonica de um campo de texto, usada para agrupar e comparar.

    Minuscula, sem espaco duplicado, sem espaco nas pontas. Nao remove acento de
    proposito: 'limao' e 'limão' sao grafias diferentes do mesmo produto, e a
    verificacao deve *reclamar* disso em vez de esconder o problema.
    """
    return _ESPACOS.sub(" ", texto.strip()).casefold()


class Unidade(StrEnum):
    """Unidade do campo ``tamanho``."""

    ML = "ml"
    L = "l"
    G = "g"
    KG = "kg"
    UN = "un"


class Embalagem(StrEnum):
    """Tipo de embalagem. Entra na identidade visual do produto."""

    LATA = "lata"
    PET = "pet"
    VIDRO = "vidro"
    CAIXA = "caixa"
    SACHE = "sache"
    POTE = "pote"
    OUTRO = "outro"


class Packshot(BaseModel):
    """Uma imagem de referencia de um SKU.

    O par ``sha256`` + ``bytes`` e o que da rastreabilidade. Quando a marca
    redesenha a embalagem e alguem substitui o arquivo mantendo o nome, a
    verificacao acusa. Sem isso a acuracia cai semanas depois e voce nao tem como
    saber por que.

    ``sha256`` nulo significa "ainda nao selado": o arquivo foi declarado mas
    nunca teve o hash gravado. E um estado valido no meio de um cadastro, e a
    verificacao trata como erro para voce nao esquecer de fechar.
    """

    model_config = ConfigDict(extra="forbid")

    arquivo: str = Field(description="Nome do arquivo dentro do diretorio de packshots.")
    sha256: str | None = Field(
        default=None,
        description="Hash do conteudo. Nulo ate rodar 'catalogo selar'.",
        pattern=r"^[0-9a-f]{64}$",
    )
    bytes: int | None = Field(default=None, ge=0, description="Tamanho em bytes.")
    largura: int | None = Field(default=None, gt=0, description="Largura em pixels.")
    altura: int | None = Field(default=None, gt=0, description="Altura em pixels.")
    selado_em: datetime | None = Field(default=None, description="Quando o hash foi gravado.")

    @property
    def selado(self) -> bool:
        return self.sha256 is not None


class SKU(BaseModel):
    """Uma unidade de catalogo.

    Coca Zero lata 350ml e Coca Zero garrafa 600ml sao SKUs diferentes. Essa
    distincao e o problema inteiro do projeto, entao ela e obrigatoria no schema.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        description="Identificador curto e estavel, usado como rotulo em todo o pipeline.",
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    nome: str = Field(description="Nome legivel, como aparece na embalagem.")
    marca: str = Field(description="Fabricante ou marca guarda-chuva, ex.: 'Coca-Cola'.")
    linha: str = Field(description="Linha de produto dentro da marca, ex.: 'Original'.")
    variante: str = Field(
        description="O que distingue dentro da linha: 'zero', 'tradicional', 'limao'.",
    )
    tamanho: float = Field(gt=0, description="Valor numerico do conteudo.")
    unidade: Unidade = Field(description="Unidade do tamanho.")
    embalagem: Embalagem = Field(description="Tipo de embalagem.")
    ean: str | None = Field(
        default=None,
        description="Codigo de barras, quando houver.",
        pattern=r"^[0-9]{8,14}$",
    )
    packshots: list[Packshot] = Field(
        default_factory=list,
        description="Imagens de referencia deste SKU. Uma ja funciona; mais de uma ajuda.",
    )
    registrado_em: datetime = Field(description="Quando este SKU entrou no catalogo.")
    observacoes: str | None = Field(default=None, description="Notas suas sobre o produto.")

    @property
    def chave_linha(self) -> tuple[str, str]:
        """(marca, linha) normalizados. Agrupa candidatos a negativo dificil."""
        return (normalizar(self.marca), normalizar(self.linha))

    @property
    def chave_variante(self) -> tuple[str, str, str]:
        """(marca, linha, variante) normalizados. Dentro dele, so muda o tamanho."""
        return (*self.chave_linha, normalizar(self.variante))

    @property
    def chave_tamanho(self) -> tuple[float, str]:
        """(tamanho, unidade). Dois SKUs com a mesma chave so diferem na variante."""
        return (self.tamanho, self.unidade.value)

    @property
    def rotulo_tamanho(self) -> str:
        """Como o tamanho aparece na tela, ex.: '350ml'."""
        valor = int(self.tamanho) if self.tamanho.is_integer() else self.tamanho
        return f"{valor}{self.unidade.value}"


class Catalogo(BaseModel):
    """O catalogo inteiro. E este arquivo que vai para o git."""

    model_config = ConfigDict(extra="forbid")

    versao_schema: int = Field(default=1, description="Versao do formato deste arquivo.")
    categoria: str = Field(
        default="",
        description="O recorte do projeto, ex.: 'bebidas-nao-alcoolicas'.",
    )
    skus: list[SKU] = Field(default_factory=list)

    def por_id(self, id_sku: str) -> SKU | None:
        return next((s for s in self.skus if s.id == id_sku), None)

    @property
    def total_packshots(self) -> int:
        return sum(len(s.packshots) for s in self.skus)
