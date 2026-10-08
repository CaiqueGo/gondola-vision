"""Treina o detector da Parte 2 no SKU-110K e, opcionalmente, instala os pesos.

Nao e "treinar detector do zero": parte de um YOLO pre-treinado no COCO e ajusta
para prateleira densa. O SKU-110K tem 8.219 fotos de treino e 588 de validacao,
com ~150 produtos por foto e uma classe so ('object') — detecta produto, nunca
qual produto.

Rode primeiro o piloto: 10% do treino, cinco epocas. Ele baixa o dataset
(13,6 GB) na primeira vez, mede quanto custa uma epoca e confirma que o mAP sai
do zero. Cinco e nao uma: o ultralytics passa as primeiras ~300 iteracoes em
warmup, com taxa alta no bias, e uma epoca de 10% (~100 iteracoes) termina no
meio dele — com mAP zero que nao diz nada sobre o pipeline.

    GONDOLA_DIR_DATASETS=E:/datasets python scripts/treinar_detector.py --piloto
    GONDOLA_DIR_DATASETS=E:/datasets python scripts/treinar_detector.py --instalar

Os pesos instalados vao para data/modelos/detector.pt (ou GONDOLA_PESOS_DETECTOR),
que e de onde 'gondola detectar' le.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

from gondola import config
from gondola.catalogo.manifesto import sha256_arquivo
from gondola.deteccao.detector import MAX_DETECCOES

MODELO_BASE = "yolo11s.pt"
"""Ponto de partida. 's' em vez de 'n': cabe folgado nos 12 GB da RTX 4070 e a
diferenca de precisao em objeto pequeno e denso compensa o tempo a mais."""

EPOCAS_PILOTO = 5


def preparar_yaml(dir_datasets: Path) -> Path:
    """Copia a definicao do SKU-110K do ultralytics apontando para ``dir_datasets``.

    O YAML original usa caminho relativo ao ``datasets_dir`` global do ultralytics;
    reescrever com caminho absoluto deixa o dataset onde este projeto mandou, sem
    mexer na configuracao global.
    """
    import ultralytics

    original = Path(ultralytics.__file__).parent / "cfg" / "datasets" / "SKU-110K.yaml"
    definicao = yaml.safe_load(original.read_text(encoding="utf-8"))
    definicao["path"] = str((dir_datasets / "SKU-110K").resolve())
    destino = dir_datasets / "SKU-110K.yaml"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(yaml.safe_dump(definicao, sort_keys=False), encoding="utf-8")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description="Treina o YOLO da Parte 2 no SKU-110K.")
    parser.add_argument("--piloto", action="store_true", help="10%% do treino, 5 epocas.")
    parser.add_argument("--epocas", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--nome", default=None, help="Nome da rodada em data/treino/.")
    parser.add_argument(
        "--instalar", action="store_true", help="Copiar o best.pt para os pesos do detector."
    )
    args = parser.parse_args()

    from ultralytics import YOLO

    dir_modelos = config.dir_dados() / "modelos"
    dir_modelos.mkdir(parents=True, exist_ok=True)
    data = preparar_yaml(config.dir_datasets())
    modelo = YOLO(str(dir_modelos / MODELO_BASE))

    epocas = EPOCAS_PILOTO if args.piloto else args.epocas
    nome = args.nome or ("piloto" if args.piloto else f"sku110k-{Path(MODELO_BASE).stem}")
    modelo.train(
        data=str(data),
        epochs=epocas,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        fraction=0.1 if args.piloto else 1.0,
        # A validacao usa o mesmo teto da deteccao: com o padrao de 300, foto
        # densa perde caixa na validacao e o mAP sai menor do que e.
        max_det=MAX_DETECCOES,
        project=str((config.dir_dados() / "treino").resolve()),
        name=nome,
        seed=0,
        # Para se a validacao passar 15 epocas sem melhorar. Com 10, um plato
        # ruidoso no meio do treino encerrava cedo demais.
        patience=15,
    )

    melhor = Path(modelo.trainer.best)
    print(f"\nmelhores pesos: {melhor}")
    print(f"sha256: {sha256_arquivo(melhor)}")
    if args.instalar and not args.piloto:
        destino = config.caminho_pesos_detector()
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(melhor, destino)
        print(f"instalado em {destino}")


if __name__ == "__main__":
    main()
