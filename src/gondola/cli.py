"""Interface de linha de comando.

Cada parte do projeto ganha um subcomando aqui. A CLI e fina de proposito: ela le
argumentos, chama a funcao de dominio e imprime. Toda a logica testavel vive nos
modulos, nao neste arquivo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from gondola import __version__, config
from gondola.catalogo.manifesto import (
    ErroCatalogo,
    adicionar_sku,
    carregar_catalogo,
    salvar_catalogo,
    selar_catalogo,
)
from gondola.catalogo.modelos import Embalagem, Unidade
from gondola.catalogo.verificacao import Nivel, verificar
from gondola.deteccao.detector import DetectorYolo, ErroDeteccao
from gondola.deteccao.recorte import (
    CONFIANCA_MINIMA_PADRAO,
    LADO_MINIMO_PADRAO,
    detectar_e_recortar,
)

app = typer.Typer(
    help="gondola — reconhecimento de produtos em gondola.",
    no_args_is_help=True,
)
catalogo_app = typer.Typer(help="Parte 1 — gerir o catalogo de SKUs.", no_args_is_help=True)
app.add_typer(catalogo_app, name="catalogo")

console = Console()
erro_console = Console(stderr=True)


@app.command()
def versao() -> None:
    """Mostra a versao do projeto."""
    console.print(f"gondola-vision {__version__}")


@catalogo_app.command("adicionar")
def catalogo_adicionar(
    packshots: Annotated[
        list[Path], typer.Argument(help="Uma ou mais imagens de referencia do produto.")
    ],
    id_sku: Annotated[
        str, typer.Option("--id", help="Identificador curto, ex.: coca-zero-350-lata.")
    ],
    nome: Annotated[str, typer.Option("--nome", help="Nome legivel do produto.")],
    marca: Annotated[str, typer.Option("--marca", help="Marca, ex.: Coca-Cola.")],
    linha: Annotated[str, typer.Option("--linha", help="Linha dentro da marca, ex.: Original.")],
    variante: Annotated[str, typer.Option("--variante", help="Ex.: zero, tradicional, limao.")],
    tamanho: Annotated[float, typer.Option("--tamanho", help="Valor numerico, ex.: 350.")],
    unidade: Annotated[Unidade, typer.Option("--unidade", help="Unidade do tamanho.")] = Unidade.ML,
    embalagem: Annotated[
        Embalagem, typer.Option("--embalagem", help="Tipo de embalagem.")
    ] = Embalagem.LATA,
    ean: Annotated[str | None, typer.Option("--ean", help="Codigo de barras.")] = None,
    observacoes: Annotated[str | None, typer.Option("--obs", help="Nota livre.")] = None,
    substituir: Annotated[
        bool, typer.Option("--substituir", help="Sobrescrever um id ja existente.")
    ] = False,
) -> None:
    """Cadastra um SKU e copia seus packshots para o catalogo.

    Nao grava hash: isso e 'catalogo selar'. Os dois passos sao separados para que
    cadastrar em lote e fechar a versao sejam revisaveis um de cada vez.
    """
    caminho = config.caminho_manifesto()
    catalogo = carregar_catalogo(caminho)
    try:
        sku = adicionar_sku(
            catalogo,
            id_sku=id_sku,
            nome=nome,
            marca=marca,
            linha=linha,
            variante=variante,
            tamanho=tamanho,
            unidade=unidade,
            embalagem=embalagem,
            packshots=packshots,
            dir_packshots=config.dir_packshots(),
            ean=ean,
            observacoes=observacoes,
            substituir=substituir,
        )
    except ErroCatalogo as erro:
        erro_console.print(f"[red]erro:[/red] {erro}")
        raise typer.Exit(code=1) from erro

    salvar_catalogo(catalogo, caminho)
    console.print(
        f"[green]cadastrado[/green] {sku.id}  "
        f"{sku.marca} / {sku.linha} / {sku.variante} / {sku.rotulo_tamanho}  "
        f"({len(sku.packshots)} packshot(s), nao selado)"
    )


@catalogo_app.command("selar")
def catalogo_selar(
    resselar: Annotated[
        bool,
        typer.Option("--resselar", help="Aceitar packshot cujo conteudo mudou desde a selagem."),
    ] = False,
) -> None:
    """Grava hash, bytes e dimensoes dos packshots ainda nao selados.

    Sai com codigo 1 se algum packshot divergiu e --resselar nao foi passado:
    imagem trocada em silencio e exatamente o que este comando existe para expor.
    """
    caminho = config.caminho_manifesto()
    catalogo = carregar_catalogo(caminho)
    resultados = selar_catalogo(catalogo, config.dir_packshots(), resselar=resselar)
    if not resultados:
        console.print("[yellow]catalogo vazio[/yellow] — use 'gondola catalogo adicionar'.")
        return

    cores = {
        "selado": "green",
        "resselado": "yellow",
        "inalterado": "dim",
        "divergente": "red",
        "ausente": "red",
    }
    mudou = False
    for r in resultados:
        cor = cores.get(r.acao, "white")
        detalhe = f"  ({r.detalhe})" if r.detalhe else ""
        console.print(f"[{cor}]{r.acao:>11}[/{cor}]  {r.id_sku}  {r.arquivo}{detalhe}")
        mudou = mudou or r.acao in {"selado", "resselado"}

    if mudou:
        salvar_catalogo(catalogo, caminho)

    problemas = [r for r in resultados if r.acao in {"divergente", "ausente"}]
    if problemas:
        erro_console.print(f"\n[red]{len(problemas)} packshot(s) precisam da sua atencao[/red]")
        sys.exit(1)


@catalogo_app.command("listar")
def catalogo_listar() -> None:
    """Lista os SKUs do catalogo."""
    catalogo = carregar_catalogo(config.caminho_manifesto())
    if not catalogo.skus:
        console.print("[yellow]catalogo vazio[/yellow] — use 'gondola catalogo adicionar'.")
        return

    tabela = Table(title=f"Catalogo ({len(catalogo.skus)} SKUs)")
    tabela.add_column("id", style="cyan")
    tabela.add_column("marca")
    tabela.add_column("linha")
    tabela.add_column("variante")
    tabela.add_column("tam.", justify="right")
    tabela.add_column("emb.")
    tabela.add_column("pack.", justify="center")
    for sku in sorted(catalogo.skus, key=lambda s: s.id):
        selados = sum(1 for p in sku.packshots if p.selado)
        tabela.add_row(
            sku.id,
            sku.marca,
            sku.linha,
            sku.variante,
            sku.rotulo_tamanho,
            sku.embalagem.value,
            f"{selados}/{len(sku.packshots)}",
        )
    console.print(tabela)


@catalogo_app.command("verificar")
def catalogo_verificar() -> None:
    """Confere integridade, armadilhas de cadastro e prontidao para a Parte 8.

    Sai com codigo 1 se houver erro — e o que permite usar isso no CI.
    """
    catalogo = carregar_catalogo(config.caminho_manifesto())
    if not catalogo.skus:
        console.print("[yellow]catalogo vazio[/yellow] — nada a verificar.")
        return

    rel = verificar(catalogo, config.dir_packshots())

    console.print(
        f"catalogo: [cyan]{config.caminho_manifesto()}[/cyan]"
        + (f"  ({catalogo.categoria})" if catalogo.categoria else "")
    )
    # Saida em ASCII puro de proposito: o console do Windows mastiga caractere
    # fora do codepage e voce perde a leitura do relatorio.
    console.print(
        f"  {rel.total_skus} SKUs | {rel.total_packshots} packshots | {rel.selados} selados\n"
    )

    for achado in rel.achados:
        cor = "red" if achado.nivel is Nivel.ERRO else "yellow"
        alvo = f"{achado.sku}  " if achado.sku else ""
        console.print(f"  [{cor}]{achado.nivel.value:>5}[/{cor}]  {alvo}{achado.mensagem}")
    if rel.achados:
        console.print()

    if rel.grupos:
        tabela = Table(title="Pares confundiveis disponiveis para a Parte 8")
        tabela.add_column("marca")
        tabela.add_column("linha")
        tabela.add_column("SKUs", justify="right")
        tabela.add_column("por variante", justify="right")
        tabela.add_column("por tamanho", justify="right")
        for g in rel.grupos:
            tabela.add_row(
                g.marca, g.linha, str(g.skus), str(g.pares_variante), str(g.pares_tamanho)
            )
        console.print(tabela)
        console.print(f"  [green]{rel.total_pares}[/green] pares confundiveis no total\n")
    else:
        console.print(
            "  [yellow]nenhum par confundivel[/yellow] — o catalogo nao tem dois SKUs da mesma\n"
            "  linha diferindo so na variante ou so no tamanho. A Parte 8 nao tera o que minerar.\n"
        )

    if rel.erros:
        erro_console.print(
            f"[red]{len(rel.erros)} erro(s)[/red]"
            + (f", [yellow]{len(rel.avisos)} aviso(s)[/yellow]" if rel.avisos else "")
        )
        sys.exit(1)
    if rel.avisos:
        console.print(f"[green]sem erros[/green], [yellow]{len(rel.avisos)} aviso(s)[/yellow]")
    else:
        console.print("[green]catalogo integro[/green]")


@app.command()
def detectar(
    fotos: Annotated[list[Path], typer.Argument(help="Uma ou mais fotos de gondola.")],
    pesos: Annotated[
        Path | None,
        typer.Option("--pesos", help="Pesos do YOLO. Padrao: GONDOLA_PESOS_DETECTOR."),
    ] = None,
    confianca: Annotated[
        float,
        typer.Option("--confianca", min=0.0, max=1.0, help="Caixas abaixo disso sao descartadas."),
    ] = CONFIANCA_MINIMA_PADRAO,
    lado_minimo: Annotated[
        int, typer.Option("--lado-minimo", min=1, help="Menor lado aceito de um crop, em px.")
    ] = LADO_MINIMO_PADRAO,
    tamanho_entrada: Annotated[
        int, typer.Option("--imgsz", min=32, help="Lado da imagem que entra no YOLO.")
    ] = 640,
    saida: Annotated[
        Path | None, typer.Option("--saida", help="Diretorio dos crops. Padrao: data/crops.")
    ] = None,
    substituir: Annotated[
        bool, typer.Option("--substituir", help="Refazer foto ja detectada.")
    ] = False,
) -> None:
    """Parte 2 — detecta os produtos e salva um crop por facing.

    Cada foto vira um diretorio com os crops, a anotada.jpg (para conferir com os
    olhos) e o deteccao.json. Sai com codigo 1 se alguma foto falhar.
    """
    # O diretorio de saida e o nome da foto sem extensao: duas fotos homonimas de
    # pastas diferentes cairiam no mesmo lugar, e com --substituir a segunda
    # apagaria a primeira em silencio.
    repetidos = sorted({f.stem for f in fotos if [g.stem for g in fotos].count(f.stem) > 1})
    if repetidos:
        erro_console.print(
            f"[red]erro:[/red] fotos com o mesmo nome: {escape(', '.join(repetidos))} "
            "(cada foto vira data/crops/<nome>; renomeie antes)"
        )
        raise typer.Exit(code=1)

    try:
        detector = DetectorYolo(
            pesos or config.caminho_pesos_detector(), tamanho_entrada=tamanho_entrada
        )
    except ErroDeteccao as erro:
        erro_console.print(f"[red]erro:[/red] {escape(str(erro))}")
        raise typer.Exit(code=1) from erro

    dir_saida = saida or config.dir_crops()
    falhas = 0
    for foto in fotos:
        try:
            m = detectar_e_recortar(
                foto,
                detector,
                dir_saida,
                confianca_minima=confianca,
                lado_minimo=lado_minimo,
                substituir=substituir,
            )
        except ErroDeteccao as erro:
            erro_console.print(f"[red]erro:[/red] {escape(str(erro))}")
            falhas += 1
            continue
        console.print(
            f"[green]{len(m.crops):>4} crops[/green]  {m.fileiras} fileira(s)  "
            + escape(f"{foto.name}  -> {dir_saida / foto.stem}")
        )
        console.print(
            f"        descartadas: {m.descartadas_confianca} por confianca, "
            f"{m.descartadas_pequenas} pequenas, {m.descartadas_fora} fora da foto"
            + ("  [yellow](girada pelo EXIF)[/yellow]" if m.girada_pelo_exif else "")
        )

    if falhas:
        erro_console.print(f"\n[red]{falhas} foto(s) falharam[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
