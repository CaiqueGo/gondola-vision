"""Ler, gravar, cadastrar e selar o manifesto do catalogo.

Todas as funcoes daqui recebem os caminhos por parametro. Nenhuma le configuracao
global por conta propria — isso e o que torna o modulo testavel sem mexer no
catalogo de verdade.
"""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict

from gondola.catalogo.modelos import SKU, Catalogo, Embalagem, Packshot, Unidade

TAMANHO_BLOCO = 1024 * 1024


class ErroCatalogo(Exception):
    """Erro esperado de operacao sobre o catalogo, com mensagem para o usuario."""


def sha256_arquivo(caminho: Path) -> str:
    """Hash SHA-256 do conteudo, lido em blocos para nao carregar a imagem inteira."""
    digest = hashlib.sha256()
    with caminho.open("rb") as fh:
        while bloco := fh.read(TAMANHO_BLOCO):
            digest.update(bloco)
    return digest.hexdigest()


def dimensoes(caminho: Path) -> tuple[int, int] | None:
    """(largura, altura) da imagem, ou None se o arquivo nao for imagem legivel."""
    try:
        with Image.open(caminho) as img:
            return img.size
    except (UnidentifiedImageError, OSError):
        return None


def carregar_catalogo(caminho: Path) -> Catalogo:
    """Le o manifesto do disco. Arquivo inexistente vira catalogo vazio."""
    if not caminho.exists():
        return Catalogo()
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return Catalogo.model_validate(dados)


def salvar_catalogo(catalogo: Catalogo, caminho: Path) -> None:
    """Grava o manifesto em YAML ordenado por id.

    Ordenar e um detalhe que importa: mantem o diff do git legivel quando voce
    cadastra um SKU no meio da lista, e o diff e como voce revisa mudanca de
    catalogo.
    """
    ordenado = catalogo.model_copy(update={"skus": sorted(catalogo.skus, key=lambda s: s.id)})
    conteudo = ordenado.model_dump(mode="json", exclude_none=True)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        yaml.safe_dump(conteudo, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def adicionar_sku(
    catalogo: Catalogo,
    *,
    id_sku: str,
    nome: str,
    marca: str,
    linha: str,
    variante: str,
    tamanho: float,
    unidade: Unidade,
    embalagem: Embalagem,
    packshots: list[Path],
    dir_packshots: Path,
    ean: str | None = None,
    observacoes: str | None = None,
    substituir: bool = False,
) -> SKU:
    """Copia os packshots para o catalogo e registra o SKU no manifesto.

    Nao sela: o hash entra em 'catalogo selar'. Separar as duas coisas e de
    proposito, para que cadastrar em lote e fechar o hash sejam passos distintos
    e revisaveis.

    O catalogo e alterado no lugar; gravar em disco e responsabilidade de quem
    chamou (a CLI), para que um erro no meio do caminho nao deixe um manifesto
    pela metade.
    """
    existente = catalogo.por_id(id_sku)
    if existente is not None and not substituir:
        raise ErroCatalogo(f"ja existe SKU com id '{id_sku}' (use --substituir)")

    if not packshots:
        raise ErroCatalogo(f"SKU '{id_sku}' precisa de pelo menos um packshot")

    dir_packshots.mkdir(parents=True, exist_ok=True)
    registrados: list[Packshot] = []
    for indice, origem in enumerate(packshots, start=1):
        if not origem.is_file():
            raise ErroCatalogo(f"packshot nao encontrado: {origem}")
        sufixo = f"-{indice}" if len(packshots) > 1 else ""
        destino = dir_packshots / f"{id_sku}{sufixo}{origem.suffix.lower()}"
        if destino.resolve() != origem.resolve():
            shutil.copy2(origem, destino)
        registrados.append(Packshot(arquivo=destino.name))

    sku = SKU(
        id=id_sku,
        nome=nome,
        marca=marca,
        linha=linha,
        variante=variante,
        tamanho=tamanho,
        unidade=unidade,
        embalagem=embalagem,
        ean=ean,
        packshots=registrados,
        registrado_em=datetime.now(UTC),
        observacoes=observacoes,
    )

    if existente is not None:
        catalogo.skus = [s for s in catalogo.skus if s.id != id_sku]
    catalogo.skus.append(sku)
    return sku


class ResultadoSelagem(BaseModel):
    """O que aconteceu com um packshot durante a selagem."""

    model_config = ConfigDict(extra="forbid")

    id_sku: str
    arquivo: str
    acao: str
    detalhe: str | None = None


def selar_catalogo(
    catalogo: Catalogo,
    dir_packshots: Path,
    *,
    resselar: bool = False,
) -> list[ResultadoSelagem]:
    """Grava hash, tamanho e dimensoes dos packshots ainda nao selados.

    Packshot cujo hash ja esta gravado e divergiu do disco **nao** e resselado por
    padrao. Reselar em silencio destruiria justamente a informacao que o hash
    existe para dar: a de que a imagem mudou. Use ``resselar=True`` so depois de
    olhar o que mudou.
    """
    resultados: list[ResultadoSelagem] = []
    agora = datetime.now(UTC)

    for sku in sorted(catalogo.skus, key=lambda s: s.id):
        for packshot in sku.packshots:
            caminho = dir_packshots / packshot.arquivo
            if not caminho.is_file():
                resultados.append(
                    ResultadoSelagem(
                        id_sku=sku.id,
                        arquivo=packshot.arquivo,
                        acao="ausente",
                        detalhe=f"esperado em {caminho}",
                    )
                )
                continue

            atual = sha256_arquivo(caminho)
            if packshot.sha256 == atual:
                resultados.append(
                    ResultadoSelagem(id_sku=sku.id, arquivo=packshot.arquivo, acao="inalterado")
                )
                continue
            if packshot.sha256 is not None and not resselar:
                resultados.append(
                    ResultadoSelagem(
                        id_sku=sku.id,
                        arquivo=packshot.arquivo,
                        acao="divergente",
                        detalhe=(
                            f"selado {packshot.sha256[:12]}..., em disco {atual[:12]}... "
                            "(use --resselar para aceitar)"
                        ),
                    )
                )
                continue

            acao = "resselado" if packshot.sha256 is not None else "selado"
            packshot.sha256 = atual
            packshot.bytes = caminho.stat().st_size
            tamanho = dimensoes(caminho)
            if tamanho is not None:
                packshot.largura, packshot.altura = tamanho
            packshot.selado_em = agora
            resultados.append(
                ResultadoSelagem(id_sku=sku.id, arquivo=packshot.arquivo, acao=acao)
            )

    return resultados
