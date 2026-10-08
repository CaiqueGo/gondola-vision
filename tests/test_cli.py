"""A CLI de ponta a ponta, contra um diretorio de dados temporario."""

from __future__ import annotations

import sys
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


def test_detectar_sem_pesos_sai_com_erro_explicando_onde_procurar(
    dados_tmp: Path, tmp_path: Path
) -> None:
    foto = tmp_path / "gondola.jpg"
    foto.write_bytes(b"irrelevante: falha antes de abrir a foto")

    resultado = runner.invoke(app, ["detectar", str(foto)])

    assert resultado.exit_code == 1
    assert "pesos do detector nao encontrados" in resultado.stderr
    assert not (dados_tmp / "crops").exists()


def test_detectar_sem_ultralytics_instalado_diz_como_instalar(
    dados_tmp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pesos = tmp_path / "detector.pt"
    pesos.write_bytes(b"pesos de mentira")
    # None em sys.modules faz o proximo 'import ultralytics' falhar com ImportError,
    # esteja ele instalado ou nao.
    monkeypatch.setitem(sys.modules, "ultralytics", None)

    resultado = runner.invoke(app, ["detectar", str(tmp_path / "x.jpg"), "--pesos", str(pesos)])

    assert resultado.exit_code == 1
    assert "deteccao" in resultado.stderr


@pytest.mark.usefixtures("dados_tmp")
def test_detectar_recusa_duas_fotos_com_o_mesmo_nome(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    resultado = runner.invoke(
        app, ["detectar", str(tmp_path / "a" / "IMG_1.jpg"), str(tmp_path / "b" / "IMG_1.jpg")]
    )

    assert resultado.exit_code == 1
    assert "mesmo nome" in resultado.stderr
    assert "IMG_1" in resultado.stderr
