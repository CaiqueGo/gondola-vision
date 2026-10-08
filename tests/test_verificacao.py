"""As checagens do catalogo.

Um teste por armadilha. Cada uma delas custou alguem semanas de treino ruim em
algum projeto de reconhecimento de produto; pegar aqui e barato.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from gondola.catalogo.manifesto import adicionar_sku, selar_catalogo
from gondola.catalogo.modelos import Catalogo, Embalagem, Unidade, normalizar
from gondola.catalogo.verificacao import Codigo, Nivel, verificar


@pytest.fixture()
def dir_packshots(tmp_path: Path) -> Path:
    return tmp_path / "packshots"


def _add(
    catalogo: Catalogo,
    dir_packshots: Path,
    packshot: Path,
    *,
    id_sku: str,
    marca: str = "Coca-Cola",
    linha: str = "Original",
    variante: str = "zero",
    tamanho: float = 350,
    embalagem: Embalagem = Embalagem.LATA,
) -> None:
    adicionar_sku(
        catalogo,
        id_sku=id_sku,
        nome=id_sku,
        marca=marca,
        linha=linha,
        variante=variante,
        tamanho=tamanho,
        unidade=Unidade.ML,
        embalagem=embalagem,
        packshots=[packshot],
        dir_packshots=dir_packshots,
    )


def _codigos(catalogo: Catalogo, dir_packshots: Path) -> set[Codigo]:
    return {a.codigo for a in verificar(catalogo, dir_packshots).achados}


def test_catalogo_selado_e_integro_nao_tem_achado(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", cor=(1, 1, 1)), id_sku="a")
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)

    assert rel.achados == []
    assert rel.ok
    assert rel.selados == 1


def test_packshot_nao_selado_e_erro(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a"), id_sku="a")

    rel = verificar(catalogo, dir_packshots)

    assert Codigo.PACKSHOT_NAO_SELADO in {a.codigo for a in rel.achados}
    assert not rel.ok


def test_packshot_ausente_e_erro(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a"), id_sku="a")
    selar_catalogo(catalogo, dir_packshots)
    (dir_packshots / catalogo.skus[0].packshots[0].arquivo).unlink()

    assert Codigo.PACKSHOT_AUSENTE in _codigos(catalogo, dir_packshots)


def test_hash_divergente_e_erro(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", cor=(1, 1, 1)), id_sku="a")
    selar_catalogo(catalogo, dir_packshots)

    outro = fazer_packshot("outro", cor=(9, 9, 9))
    (dir_packshots / catalogo.skus[0].packshots[0].arquivo).write_bytes(outro.read_bytes())

    assert Codigo.HASH_DIVERGENTE in _codigos(catalogo, dir_packshots)


def test_imagem_ilegivel_e_erro(dir_packshots: Path) -> None:
    catalogo = Catalogo()
    dir_packshots.mkdir(parents=True)
    falso = dir_packshots / "a.png"
    falso.write_bytes(b"isto nao e uma imagem")
    _add(catalogo, dir_packshots, falso, id_sku="a")

    assert Codigo.IMAGEM_ILEGIVEL in _codigos(catalogo, dir_packshots)


def test_imagem_pequena_e_aviso(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", largura=64, altura=64), id_sku="a")
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)
    pequenas = [a for a in rel.achados if a.codigo is Codigo.IMAGEM_PEQUENA]

    assert len(pequenas) == 1
    assert pequenas[0].nivel is Nivel.AVISO
    assert rel.ok, "imagem pequena avisa, mas nao reprova o catalogo"


def test_packshot_compartilhado_entre_skus_e_erro(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    """Dois SKUs com a mesma imagem sao inseparaveis por imagem.

    Acontece de verdade: produto com dois EANs e um packshot so. Se passar, o
    treino da Parte 9 recebe um par rotulado como negativo que e visualmente
    identico, e desestabiliza.
    """
    catalogo = Catalogo()
    mesma = fazer_packshot("identica", cor=(7, 7, 7))
    _add(catalogo, dir_packshots, mesma, id_sku="a", variante="zero")
    _add(catalogo, dir_packshots, mesma, id_sku="b", variante="tradicional")
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)
    compartilhados = [a for a in rel.achados if a.codigo is Codigo.PACKSHOT_COMPARTILHADO]

    assert len(compartilhados) == 1
    assert compartilhados[0].sku == "b"
    assert not rel.ok


def test_packshot_orfao_e_aviso(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", cor=(1, 1, 1)), id_sku="a")
    selar_catalogo(catalogo, dir_packshots)
    (dir_packshots / "sobrou.png").write_bytes(fazer_packshot("s", cor=(2, 2, 2)).read_bytes())

    rel = verificar(catalogo, dir_packshots)
    orfaos = [a for a in rel.achados if a.codigo is Codigo.PACKSHOT_ORFAO]

    assert len(orfaos) == 1
    assert orfaos[0].nivel is Nivel.AVISO


def test_grafia_inconsistente_e_aviso(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    """'Coca-Cola' e 'coca-cola' viram dois grupos e quebram a Parte 8 em silencio."""
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", cor=(1, 1, 1)), id_sku="a", marca="Coca-Cola")
    _add(catalogo, dir_packshots, fazer_packshot("b", cor=(2, 2, 2)), id_sku="b", marca="coca-cola")
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)
    grafias = [a for a in rel.achados if a.codigo is Codigo.GRAFIA_INCONSISTENTE]

    assert len(grafias) == 1
    assert grafias[0].nivel is Nivel.AVISO


def test_normalizar_junta_espaco_e_maiuscula_mas_nao_acento() -> None:
    assert normalizar("  Coca-Cola   Zero ") == "coca-cola zero"
    assert normalizar("limao") != normalizar("limão"), "acento diferente deve ser reclamado"


def test_pares_confundiveis_contam_um_eixo_de_cada_vez(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    """Quatro SKUs da mesma linha: 2 variantes x 2 tamanhos.

    Pares esperados: 2 por variante (mesmo tamanho, variante diferente) e 2 por
    tamanho (mesma variante, tamanho diferente). Os 2 pares que diferem nos dois
    eixos sao mais faceis e nao entram na conta.
    """
    catalogo = Catalogo()
    combinacoes = [
        ("zero-350", "zero", 350.0),
        ("trad-350", "tradicional", 350.0),
        ("zero-600", "zero", 600.0),
        ("trad-600", "tradicional", 600.0),
    ]
    for indice, (id_sku, variante, tamanho) in enumerate(combinacoes, start=1):
        _add(
            catalogo,
            dir_packshots,
            fazer_packshot(id_sku, cor=(indice * 10, 0, 0)),
            id_sku=id_sku,
            variante=variante,
            tamanho=tamanho,
        )
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)

    assert len(rel.grupos) == 1
    grupo = rel.grupos[0]
    assert grupo.skus == 4
    assert grupo.pares_variante == 2
    assert grupo.pares_tamanho == 2
    assert rel.total_pares == 4


def test_catalogo_sem_par_confundivel_nao_gera_grupo(
    dir_packshots: Path, fazer_packshot: Callable[..., Path]
) -> None:
    catalogo = Catalogo()
    _add(catalogo, dir_packshots, fazer_packshot("a", cor=(1, 1, 1)), id_sku="a", marca="Marca A")
    _add(catalogo, dir_packshots, fazer_packshot("b", cor=(2, 2, 2)), id_sku="b", marca="Marca B")
    selar_catalogo(catalogo, dir_packshots)

    rel = verificar(catalogo, dir_packshots)

    assert rel.grupos == []
    assert rel.total_pares == 0
