"""Gera um catalogo de exemplo para voce ver a Parte 1 funcionando hoje.

As imagens sao retangulos de cor chapada com o nome escrito — placeholders, nao
packshots de verdade. A Parte 1 nao interpreta o conteudo da imagem: ela faz
hash, le as dimensoes e confere o cadastro. Entao placeholder serve para exercitar
a ferramenta inteira, e voce troca por packshot real quando chegar na Parte 4.

Os seis SKUs foram escolhidos para produzir pares confundiveis de verdade:
quatro Coca-Cola (2 variantes x 2 tamanhos) e dois Guarana (2 variantes). E
exatamente o formato de par que o encoder vai ter de aprender a separar.

    python scripts/gerar_exemplo.py
    GONDOLA_DATA_DIR=exemplo python -m gondola.cli catalogo verificar
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gondola.catalogo.manifesto import adicionar_sku, salvar_catalogo, selar_catalogo
from gondola.catalogo.modelos import Catalogo, Embalagem, Unidade

RAIZ = Path(__file__).resolve().parent.parent
DIR_EXEMPLO = RAIZ / "exemplo"

# (id, nome, marca, linha, variante, tamanho, unidade, embalagem, cor)
PRODUTOS = [
    ("coca-trad-350-lata", "Coca-Cola Lata 350ml", "Coca-Cola", "Original",
     "tradicional", 350.0, Unidade.ML, Embalagem.LATA, (196, 30, 40)),
    ("coca-zero-350-lata", "Coca-Cola Zero Lata 350ml", "Coca-Cola", "Original",
     "zero", 350.0, Unidade.ML, Embalagem.LATA, (24, 24, 28)),
    ("coca-trad-600-pet", "Coca-Cola PET 600ml", "Coca-Cola", "Original",
     "tradicional", 600.0, Unidade.ML, Embalagem.PET, (176, 26, 36)),
    ("coca-zero-600-pet", "Coca-Cola Zero PET 600ml", "Coca-Cola", "Original",
     "zero", 600.0, Unidade.ML, Embalagem.PET, (32, 32, 38)),
    ("guarana-trad-350-lata", "Guarana Antarctica Lata 350ml", "Antarctica", "Guarana",
     "tradicional", 350.0, Unidade.ML, Embalagem.LATA, (22, 96, 62)),
    ("guarana-zero-350-lata", "Guarana Antarctica Zero Lata 350ml", "Antarctica", "Guarana",
     "zero", 350.0, Unidade.ML, Embalagem.LATA, (18, 70, 48)),
]


def desenhar(caminho: Path, texto: str, cor: tuple[int, int, int]) -> None:
    """Um placeholder 512x512 com o nome escrito, so para ser legivel na pasta."""
    imagem = Image.new("RGB", (512, 512), cor)
    desenho = ImageDraw.Draw(imagem)
    fonte = ImageFont.load_default()
    for indice, linha in enumerate(texto.split("\n")):
        desenho.text((24, 24 + indice * 18), linha, fill=(255, 255, 255), font=fonte)
    imagem.save(caminho)


def main() -> None:
    if DIR_EXEMPLO.exists():
        shutil.rmtree(DIR_EXEMPLO)
    origem = DIR_EXEMPLO / "_origem"
    origem.mkdir(parents=True)

    catalogo = Catalogo(categoria="bebidas-nao-alcoolicas")
    for id_sku, nome, marca, linha, variante, tamanho, unidade, embalagem, cor in PRODUTOS:
        arquivo = origem / f"{id_sku}.png"
        desenhar(arquivo, f"{marca}\n{linha}\n{variante}\n{tamanho:.0f}{unidade.value}", cor)
        adicionar_sku(
            catalogo,
            id_sku=id_sku,
            nome=nome,
            marca=marca,
            linha=linha,
            variante=variante,
            tamanho=tamanho,
            unidade=unidade,
            embalagem=embalagem,
            packshots=[arquivo],
            dir_packshots=DIR_EXEMPLO / "packshots",
        )

    selar_catalogo(catalogo, DIR_EXEMPLO / "packshots")
    salvar_catalogo(catalogo, DIR_EXEMPLO / "catalogo.yaml")
    shutil.rmtree(origem)

    print(f"catalogo de exemplo em {DIR_EXEMPLO}")
    print(f"  {len(catalogo.skus)} SKUs, {catalogo.total_packshots} packshots selados")
    print()
    print("agora rode:")
    print("  GONDOLA_DATA_DIR=exemplo python -m gondola.cli catalogo verificar")


if __name__ == "__main__":
    main()
