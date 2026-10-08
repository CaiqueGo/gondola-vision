"""Conferir o catalogo contra o disco e contra si mesmo.

Tres familias de checagem, por ordem de gravidade:

1. **Integridade** — o arquivo existe, e imagem, e ainda bate com o hash selado.
   Sem isso voce nao sabe contra qual versao do catalogo mediu.
2. **Armadilhas conhecidas** — packshot compartilhado entre dois SKUs e grafia
   inconsistente no cadastro. Ambas passam despercebidas por meses e so aparecem
   como treino instavel na Parte 9. Sao baratas de pegar aqui.
3. **Prontidao para a Parte 8** — quantos pares confundiveis o cadastro ja e
   capaz de gerar. Nao e erro; e o sinal de que o catalogo tem o que o treino
   vai precisar.
"""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gondola.catalogo.manifesto import dimensoes, sha256_arquivo
from gondola.catalogo.modelos import SKU, Catalogo, normalizar

LADO_MINIMO = 256
"""Menor lado aceitavel de um packshot, em pixels.

Abaixo disso a imagem nao sobrevive a augmentation da Parte 7: voce vai reduzir
de proposito para simular crop de prateleira, e nao da para reduzir o que ja
nasceu pequeno.
"""

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".webp"}


class Nivel(StrEnum):
    ERRO = "erro"
    AVISO = "aviso"


class Codigo(StrEnum):
    """O que a verificacao sabe encontrar."""

    ID_DUPLICADO = "id_duplicado"
    SKU_SEM_PACKSHOT = "sku_sem_packshot"
    PACKSHOT_AUSENTE = "packshot_ausente"
    PACKSHOT_NAO_SELADO = "packshot_nao_selado"
    HASH_DIVERGENTE = "hash_divergente"
    IMAGEM_ILEGIVEL = "imagem_ilegivel"
    IMAGEM_PEQUENA = "imagem_pequena"
    PACKSHOT_ORFAO = "packshot_orfao"
    PACKSHOT_COMPARTILHADO = "packshot_compartilhado"
    GRAFIA_INCONSISTENTE = "grafia_inconsistente"


class Achado(BaseModel):
    """Um problema encontrado, com o SKU que o causou quando aplicavel."""

    model_config = ConfigDict(extra="forbid")

    nivel: Nivel
    codigo: Codigo
    mensagem: str
    sku: str | None = None


class GrupoConfundivel(BaseModel):
    """Um (marca, linha) e os pares de SKU que o encoder vai ter de separar."""

    model_config = ConfigDict(extra="forbid")

    marca: str
    linha: str
    skus: int
    pares_variante: int = Field(description="Mesmo tamanho, variante diferente.")
    pares_tamanho: int = Field(description="Mesma variante, tamanho diferente.")

    @property
    def pares(self) -> int:
        return self.pares_variante + self.pares_tamanho


class Relatorio(BaseModel):
    """O resultado completo de uma verificacao."""

    model_config = ConfigDict(extra="forbid")

    total_skus: int
    total_packshots: int
    selados: int
    achados: list[Achado] = Field(default_factory=list)
    grupos: list[GrupoConfundivel] = Field(default_factory=list)

    @property
    def erros(self) -> list[Achado]:
        return [a for a in self.achados if a.nivel is Nivel.ERRO]

    @property
    def avisos(self) -> list[Achado]:
        return [a for a in self.achados if a.nivel is Nivel.AVISO]

    @property
    def ok(self) -> bool:
        return not self.erros

    @property
    def total_pares(self) -> int:
        return sum(g.pares for g in self.grupos)


def _checar_ids(catalogo: Catalogo) -> list[Achado]:
    vistos: dict[str, int] = defaultdict(int)
    for sku in catalogo.skus:
        vistos[sku.id] += 1
    return [
        Achado(
            nivel=Nivel.ERRO,
            codigo=Codigo.ID_DUPLICADO,
            sku=id_sku,
            mensagem=f"id aparece {n} vezes no manifesto",
        )
        for id_sku, n in sorted(vistos.items())
        if n > 1
    ]


def _checar_packshots(catalogo: Catalogo, dir_packshots: Path) -> tuple[list[Achado], int]:
    """Integridade de cada packshot. Devolve os achados e quantos estao selados."""
    achados: list[Achado] = []
    selados = 0
    dono_do_hash: dict[str, str] = {}

    for sku in sorted(catalogo.skus, key=lambda s: s.id):
        if not sku.packshots:
            achados.append(
                Achado(
                    nivel=Nivel.ERRO,
                    codigo=Codigo.SKU_SEM_PACKSHOT,
                    sku=sku.id,
                    mensagem="nenhuma imagem de referencia; o SKU nunca sera reconhecido",
                )
            )
            continue

        for packshot in sku.packshots:
            caminho = dir_packshots / packshot.arquivo
            if not caminho.is_file():
                achados.append(
                    Achado(
                        nivel=Nivel.ERRO,
                        codigo=Codigo.PACKSHOT_AUSENTE,
                        sku=sku.id,
                        mensagem=f"{packshot.arquivo}: esperado em {caminho}",
                    )
                )
                continue

            tamanho = dimensoes(caminho)
            if tamanho is None:
                achados.append(
                    Achado(
                        nivel=Nivel.ERRO,
                        codigo=Codigo.IMAGEM_ILEGIVEL,
                        sku=sku.id,
                        mensagem=f"{packshot.arquivo}: nao e imagem legivel",
                    )
                )
                continue
            if min(tamanho) < LADO_MINIMO:
                achados.append(
                    Achado(
                        nivel=Nivel.AVISO,
                        codigo=Codigo.IMAGEM_PEQUENA,
                        sku=sku.id,
                        mensagem=(
                            f"{packshot.arquivo}: {tamanho[0]}x{tamanho[1]}px, "
                            f"menor lado abaixo de {LADO_MINIMO}px"
                        ),
                    )
                )

            selado = packshot.sha256
            if selado is None:
                achados.append(
                    Achado(
                        nivel=Nivel.ERRO,
                        codigo=Codigo.PACKSHOT_NAO_SELADO,
                        sku=sku.id,
                        mensagem=f"{packshot.arquivo}: sem hash; rode 'catalogo selar'",
                    )
                )
                continue

            selados += 1
            atual = sha256_arquivo(caminho)
            if atual != selado:
                achados.append(
                    Achado(
                        nivel=Nivel.ERRO,
                        codigo=Codigo.HASH_DIVERGENTE,
                        sku=sku.id,
                        mensagem=(
                            f"{packshot.arquivo}: selado {selado[:12]}..., "
                            f"em disco {atual[:12]}... (embalagem redesenhada?)"
                        ),
                    )
                )
                continue

            dono = dono_do_hash.get(atual)
            if dono is not None and dono != sku.id:
                achados.append(
                    Achado(
                        nivel=Nivel.ERRO,
                        codigo=Codigo.PACKSHOT_COMPARTILHADO,
                        sku=sku.id,
                        mensagem=(
                            f"{packshot.arquivo}: imagem identica a de '{dono}'. "
                            "Dois SKUs com o mesmo packshot sao inseparaveis por imagem."
                        ),
                    )
                )
            else:
                dono_do_hash[atual] = sku.id

    return achados, selados


def _checar_orfaos(catalogo: Catalogo, dir_packshots: Path) -> list[Achado]:
    if not dir_packshots.is_dir():
        return []
    referenciados = {p.arquivo for s in catalogo.skus for p in s.packshots}
    achados = []
    for caminho in sorted(dir_packshots.iterdir()):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_IMAGEM:
            continue
        if caminho.name not in referenciados:
            achados.append(
                Achado(
                    nivel=Nivel.AVISO,
                    codigo=Codigo.PACKSHOT_ORFAO,
                    mensagem=f"{caminho.name}: em disco mas nao referenciado por nenhum SKU",
                )
            )
    return achados


def _checar_grafia(catalogo: Catalogo) -> list[Achado]:
    """Duas grafias que normalizam igual sao a mesma coisa escrita de dois jeitos.

    Isso quebra o agrupamento da Parte 8 em silencio: 'Coca-Cola' e 'coca cola'
    viram dois grupos, e os negativos dificeis entre eles nunca sao minerados.
    """
    achados: list[Achado] = []
    for campo in ("marca", "linha", "variante"):
        grafias: dict[str, set[str]] = defaultdict(set)
        for sku in catalogo.skus:
            valor: str = getattr(sku, campo)
            grafias[normalizar(valor)].add(valor)
        for chave, valores in sorted(grafias.items()):
            if len(valores) > 1:
                lista = ", ".join(f"'{v}'" for v in sorted(valores))
                achados.append(
                    Achado(
                        nivel=Nivel.AVISO,
                        codigo=Codigo.GRAFIA_INCONSISTENTE,
                        mensagem=f"{campo} '{chave}' escrito de {len(valores)} formas: {lista}",
                    )
                )
    return achados


def _agrupar_confundiveis(catalogo: Catalogo) -> list[GrupoConfundivel]:
    """Conta os pares de SKU que diferem em exatamente um eixo.

    Um par so conta quando compartilha (marca, linha) e difere *ou* na variante
    *ou* no tamanho — nunca nos dois. Par que difere nos dois eixos e visualmente
    mais facil, e inflar a conta com ele daria uma falsa sensacao de catalogo
    bem preparado.
    """
    por_linha: dict[tuple[str, str], list[SKU]] = defaultdict(list)
    for sku in catalogo.skus:
        por_linha[sku.chave_linha].append(sku)

    grupos: list[GrupoConfundivel] = []
    for (marca, linha), skus in por_linha.items():
        pares_variante = 0
        pares_tamanho = 0
        for a, b in combinations(skus, 2):
            mesma_variante = a.chave_variante == b.chave_variante
            mesmo_tamanho = a.chave_tamanho == b.chave_tamanho
            if mesmo_tamanho and not mesma_variante:
                pares_variante += 1
            elif mesma_variante and not mesmo_tamanho:
                pares_tamanho += 1
        if pares_variante or pares_tamanho:
            grupos.append(
                GrupoConfundivel(
                    marca=marca,
                    linha=linha,
                    skus=len(skus),
                    pares_variante=pares_variante,
                    pares_tamanho=pares_tamanho,
                )
            )
    return sorted(grupos, key=lambda g: (-g.pares, g.marca, g.linha))


def verificar(catalogo: Catalogo, dir_packshots: Path) -> Relatorio:
    """Roda todas as checagens e devolve um relatorio unico."""
    achados_packshots, selados = _checar_packshots(catalogo, dir_packshots)
    achados = [
        *_checar_ids(catalogo),
        *achados_packshots,
        *_checar_orfaos(catalogo, dir_packshots),
        *_checar_grafia(catalogo),
    ]
    return Relatorio(
        total_skus=len(catalogo.skus),
        total_packshots=catalogo.total_packshots,
        selados=selados,
        achados=achados,
        grupos=_agrupar_confundiveis(catalogo),
    )
