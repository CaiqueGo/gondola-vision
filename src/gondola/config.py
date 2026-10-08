"""Onde ficam os dados do projeto.

Um unico lugar decide caminho, e ele e sobrescritivel por variavel de ambiente.
E isso que permite ao teste (e ao catalogo de exemplo) rodar contra um diretorio
temporario sem nunca tocar nos seus dados de verdade.
"""

from __future__ import annotations

import os
from pathlib import Path

VAR_DIR_DADOS = "GONDOLA_DATA_DIR"
PADRAO_DIR_DADOS = "data"

NOME_MANIFESTO = "catalogo.yaml"
NOME_DIR_PACKSHOTS = "packshots"


def dir_dados() -> Path:
    """Raiz dos dados. Respeita GONDOLA_DATA_DIR quando definida."""
    return Path(os.environ.get(VAR_DIR_DADOS, PADRAO_DIR_DADOS))


def caminho_manifesto() -> Path:
    """O arquivo que vai para o git: a lista de SKUs com hash."""
    return dir_dados() / NOME_MANIFESTO


def dir_packshots() -> Path:
    """Onde ficam as imagens de referencia. Nao vai para o git."""
    return dir_dados() / NOME_DIR_PACKSHOTS

