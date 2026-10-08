"""Cadastro, gravacao e selagem do catalogo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from gondola.catalogo.manifesto import (
    ErroCatalogo,
    adicionar_sku,
    carregar_catalogo,
    salvar_catalogo,
    selar_catalogo,
    sha256_arquivo,
)
from gondola.catalogo.modelos import Catalogo, Embalagem, Unidade


def _adicionar(
    catalogo: Catalogo,
    dir_packshots: Path,
    packshot: Path,
    *,
    id_sku: str = "coca-zero-350-lata",
    variante: str = "zero",
    tamanho: float = 350,
    **extra: object,
) -> object:
    return adicionar_sku(
        catalogo,
        id_sku=id_sku,
        nome="Coca-Cola Zero Lata 350ml",
        marca="Coca-Cola",
        linha="Original",
        variante=variante,
        tamanho=tamanho,
        unidade=Unidade.ML,
        embalagem=Embalagem.LATA,
        packshots=[packshot],
        dir_packshots=dir_packshots,
        **extra,  # type: ignore[arg-type]
    )


def test_adicionar_copia_o_packshot_e_nao_sela(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    origem = fazer_packshot("coca-zero")

    sku = _adicionar(catalogo, dir_packshots, origem)

    assert (dir_packshots / "coca-zero-350-lata.png").is_file()
    assert sku.packshots[0].sha256 is None, "adicionar nao deve selar"
    assert sku.packshots[0].selado is False


def test_adicionar_recusa_id_repetido(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    origem = fazer_packshot("coca-zero")
    _adicionar(catalogo, dir_packshots, origem)

    with pytest.raises(ErroCatalogo, match="ja existe SKU"):
        _adicionar(catalogo, dir_packshots, origem)

    _adicionar(catalogo, dir_packshots, origem, substituir=True)
    assert len(catalogo.skus) == 1


def test_adicionar_exige_packshot(tmp_path: Path) -> None:
    catalogo = Catalogo()
    with pytest.raises(ErroCatalogo, match="pelo menos um packshot"):
        adicionar_sku(
            catalogo,
            id_sku="sem-foto",
            nome="Sem foto",
            marca="M",
            linha="L",
            variante="v",
            tamanho=1,
            unidade=Unidade.UN,
            embalagem=Embalagem.OUTRO,
            packshots=[],
            dir_packshots=tmp_path / "packshots",
        )


def test_salvar_e_carregar_preserva_tudo(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo(categoria="bebidas-nao-alcoolicas")
    dir_packshots = tmp_path / "packshots"
    _adicionar(catalogo, dir_packshots, fazer_packshot("coca-zero"))
    selar_catalogo(catalogo, dir_packshots)

    caminho = tmp_path / "catalogo.yaml"
    salvar_catalogo(catalogo, caminho)
    lido = carregar_catalogo(caminho)

    assert lido.categoria == "bebidas-nao-alcoolicas"
    assert lido.skus[0].id == catalogo.skus[0].id
    assert lido.skus[0].packshots[0].sha256 == catalogo.skus[0].packshots[0].sha256
    assert lido.skus[0].packshots[0].largura == 512


def test_salvar_ordena_por_id(tmp_path: Path, fazer_packshot: Callable[..., Path]) -> None:
    """Diff legivel no git e o que torna revisavel uma mudanca de catalogo."""
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    for id_sku in ("zz-ultimo", "aa-primeiro", "mm-meio"):
        _adicionar(catalogo, dir_packshots, fazer_packshot(id_sku), id_sku=id_sku)

    caminho = tmp_path / "catalogo.yaml"
    salvar_catalogo(catalogo, caminho)
    texto = caminho.read_text(encoding="utf-8")

    assert texto.index("aa-primeiro") < texto.index("mm-meio") < texto.index("zz-ultimo")


def test_carregar_arquivo_inexistente_vira_catalogo_vazio(tmp_path: Path) -> None:
    assert carregar_catalogo(tmp_path / "nao-existe.yaml").skus == []


def test_selar_grava_hash_bytes_e_dimensoes(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    origem = fazer_packshot("coca-zero", largura=640, altura=480)
    _adicionar(catalogo, dir_packshots, origem)

    resultados = selar_catalogo(catalogo, dir_packshots)

    assert [r.acao for r in resultados] == ["selado"]
    packshot = catalogo.skus[0].packshots[0]
    assert packshot.sha256 == sha256_arquivo(dir_packshots / packshot.arquivo)
    assert packshot.largura == 640
    assert packshot.altura == 480
    assert packshot.bytes and packshot.bytes > 0
    assert packshot.selado_em is not None


def test_selar_duas_vezes_nao_mexe_no_que_ja_esta_selado(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    _adicionar(catalogo, dir_packshots, fazer_packshot("coca-zero"))
    selar_catalogo(catalogo, dir_packshots)

    resultados = selar_catalogo(catalogo, dir_packshots)

    assert [r.acao for r in resultados] == ["inalterado"]


def test_selar_nao_resela_em_silencio_quando_a_imagem_muda(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    """O caso da embalagem redesenhada: o arquivo trocou mantendo o nome.

    Reselar sozinho apagaria justamente a informacao que o hash existe para dar.
    """
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    _adicionar(catalogo, dir_packshots, fazer_packshot("coca-zero", cor=(200, 30, 30)))
    selar_catalogo(catalogo, dir_packshots)
    hash_original = catalogo.skus[0].packshots[0].sha256

    # a marca redesenhou: mesmo nome de arquivo, outro conteudo
    novo = fazer_packshot("redesenho", cor=(10, 10, 10))
    destino = dir_packshots / catalogo.skus[0].packshots[0].arquivo
    destino.write_bytes(novo.read_bytes())

    resultados = selar_catalogo(catalogo, dir_packshots)
    assert [r.acao for r in resultados] == ["divergente"]
    assert catalogo.skus[0].packshots[0].sha256 == hash_original

    resultados = selar_catalogo(catalogo, dir_packshots, resselar=True)
    assert [r.acao for r in resultados] == ["resselado"]
    assert catalogo.skus[0].packshots[0].sha256 != hash_original


def test_selar_reporta_packshot_ausente(
    tmp_path: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    dir_packshots = tmp_path / "packshots"
    _adicionar(catalogo, dir_packshots, fazer_packshot("coca-zero"))
    (dir_packshots / catalogo.skus[0].packshots[0].arquivo).unlink()

    resultados = selar_catalogo(catalogo, dir_packshots)

    assert [r.acao for r in resultados] == ["ausente"]
