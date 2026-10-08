"""Fixtures compartilhadas.

A fixture ``dados_tmp`` aponta GONDOLA_DATA_DIR para um diretorio temporario.
Nenhum teste toca no catalogo real.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture()
def dados_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GONDOLA_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def fazer_packshot(tmp_path: Path) -> Callable[..., Path]:
    """Gera um PNG solido servindo de packshot.

    A Parte 1 nao interpreta o conteudo da imagem — so faz hash e le as
    dimensoes. Entao um retangulo de cor chapada serve, e o teste fica rapido e
    sem depender de arquivo externo.

    A cor entra no nome e no pixel: dois packshots de cores diferentes tem hashes
    diferentes, que e o que os testes de integridade precisam.
    """
    origem = tmp_path / "origem"
    origem.mkdir(exist_ok=True)

    def _fazer(
        nome: str,
        *,
        cor: tuple[int, int, int] = (200, 30, 30),
        largura: int = 512,
        altura: int = 512,
    ) -> Path:
        caminho = origem / f"{nome}.png"
        Image.new("RGB", (largura, altura), cor).save(caminho)
        return caminho

    return _fazer
