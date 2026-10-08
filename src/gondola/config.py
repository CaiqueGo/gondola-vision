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
VAR_PESOS_DETECTOR = "GONDOLA_PESOS_DETECTOR"

NOME_MANIFESTO = "catalogo.yaml"
NOME_DIR_PACKSHOTS = "packshots"
NOME_DIR_CROPS = "crops"
NOME_PESOS_DETECTOR = "modelos/detector.pt"


def dir_dados() -> Path:
    """Raiz dos dados. Respeita GONDOLA_DATA_DIR quando definida."""
    return Path(os.environ.get(VAR_DIR_DADOS, PADRAO_DIR_DADOS))


def caminho_manifesto() -> Path:
    """O arquivo que vai para o git: a lista de SKUs com hash."""
    return dir_dados() / NOME_MANIFESTO


def dir_packshots() -> Path:
    """Onde ficam as imagens de referencia. Nao vai para o git."""
    return dir_dados() / NOME_DIR_PACKSHOTS


def dir_crops() -> Path:
    """Onde a Parte 2 grava os crops, um subdiretorio por foto. Nao vai para o git."""
    return dir_dados() / NOME_DIR_CROPS


def caminho_pesos_detector() -> Path:
    """Pesos do YOLO. Respeita GONDOLA_PESOS_DETECTOR quando definida. Nao vai para o git."""
    definido = os.environ.get(VAR_PESOS_DETECTOR)
    return Path(definido) if definido else dir_dados() / NOME_PESOS_DETECTOR
