"""A CLI de ponta a ponta, contra um diretorio de dados temporario."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gondola.cli import app

runner = CliRunner()


def _adicionar(packshot: Path, *, id_sku: str, variante: str, tamanho: str) -> object:
    return runner.invoke(
        app,
        [
            "catalogo", "adicionar", str(packshot),
            "--id", id_sku,
            "--nome", id_sku,
            "--marca", "Coca-Cola",
            "--linha", "Original",
            "--variante", variante,
            "--tamanho", tamanho,
            "--unidade", "ml",
            "--embalagem", "lata",
        ],
    )


@pytest.mark.usefixtures("dados_tmp")
def test_versao() -> None:
    resultado = runner.invoke(app, ["versao"])
    assert resultado.exit_code == 0
    assert "gondola-vision" in resultado.stdout


@pytest.mark.usefixtures("dados_tmp")
def test_verificar_catalogo_vazio_nao_falha() -> None:
    resultado = runner.invoke(app, ["catalogo", "verificar"])
    assert resultado.exit_code == 0
    assert "vazio" in resultado.stdout


@pytest.mark.usefixtures("dados_tmp")
def test_ciclo_completo_adicionar_selar_verificar(fazer_packshot: Callable[..., Path]) -> None:
    assert _adicionar(fazer_packshot("z3", cor=(1, 1, 1)), id_sku="z3", variante="zero", tamanho="350").exit_code == 0  # noqa: E501
    assert _adicionar(fazer_packshot("t3", cor=(2, 2, 2)), id_sku="t3", variante="tradicional", tamanho="350").exit_code == 0  # noqa: E501

    verificacao = runner.invoke(app, ["catalogo", "verificar"])
    assert verificacao.exit_code == 1, "sem selar, verificar deve reprovar"
    assert "nao_selado" in verificacao.stdout or "selar" in verificacao.stdout

    selagem = runner.invoke(app, ["catalogo", "selar"])
    assert selagem.exit_code == 0
    assert "selado" in selagem.stdout

    verificacao = runner.invoke(app, ["catalogo", "verificar"])
    assert verificacao.exit_code == 0
    assert "integro" in verificacao.stdout
    assert "1" in verificacao.stdout, "deve reportar o par confundivel z3/t3"


@pytest.mark.usefixtures("dados_tmp")
def test_listar_mostra_os_skus(fazer_packshot: Callable[..., Path]) -> None:
    _adicionar(fazer_packshot("z3"), id_sku="z3", variante="zero", tamanho="350")
    resultado = runner.invoke(app, ["catalogo", "listar"])
    assert resultado.exit_code == 0
    assert "z3" in resultado.stdout


@pytest.mark.usefixtures("dados_tmp")
def test_adicionar_id_repetido_sai_com_erro(fazer_packshot: Callable[..., Path]) -> None:
    packshot = fazer_packshot("z3")
    _adicionar(packshot, id_sku="z3", variante="zero", tamanho="350")
    resultado = _adicionar(packshot, id_sku="z3", variante="zero", tamanho="350")
    assert resultado.exit_code == 1

