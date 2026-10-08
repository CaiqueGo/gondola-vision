# Parte 2 — Detecção e crops

**Status:** 🟡 código pronto e testado; falta rodar numa foto real com pesos do SKU-110K
**Depende de:** nada (a Parte 1 não é usada aqui)
**Habilita:** Parte 3 (conjunto de teste rotulado), Parte 11 (contexto de vizinho), Parte 13 (contagem de facings)

---

## Objetivo

Dada uma foto de gôndola, achar **onde** está cada produto e salvar um recorte
(crop) por facing, com registro suficiente para saber de onde cada crop veio.

## Que problema isso resolve

**1. Achar e identificar são dois problemas.** O detector responde "tem um
produto aqui", nunca "é uma Coca Zero". Separar os dois é o que permite trocar o
encoder (Parte 6) sem tocar na detecção, e medir cada um isoladamente. Erro que
nasce aqui — caixa perdida, duas latas numa caixa só — o encoder não conserta, e
você vai culpá-lo se não souber que nasceu aqui.

**2. A Parte 3 precisa de crops reais.** O conjunto de teste é feito de recortes
de prateleira de verdade, não de packshots. Esta parte é a fábrica desses
recortes.

**3. Cada crop precisa carregar sua origem.** Qual foto (hash), qual detector
(hash dos pesos), qual caixa, em que fileira e posição. Sem isso, um rótulo da
Parte 3 aponta para um arquivo que pode ter mudado, e a contagem da Parte 13 não
sabe quem é vizinho de quem.

## O que foi construído

```
src/gondola/
├── config.py                  + dir_crops(), caminho_pesos_detector()
├── cli.py                     + gondola detectar
└── deteccao/
    ├── modelos.py             Caixa, Crop, ManifestoDeteccao (Pydantic)
    ├── detector.py            protocolo Detector + DetectorYolo (ultralytics)
    └── recorte.py             EXIF, filtros, fileiras, crops, anotada, manifesto
```

Para cada foto, `gondola detectar` cria `data/crops/<foto>/` com:

| Arquivo | O que é |
|---|---|
| `f01-p001.png`, … | Um crop por facing. `f` = fileira (1 = prateleira de cima), `p` = posição (1 = mais à esquerda) |
| `anotada.jpg` | A foto com as caixas desenhadas, **uma cor por fileira**. É para olhar com os olhos |
| `deteccao.json` | O manifesto: hash da foto, hash dos pesos, parâmetros, cada caixa e quantas foram descartadas e por quê |

### O caminho de uma foto

1. **Abre e gira pela etiqueta EXIF.** Foto de celular costuma ser gravada de
   lado com uma etiqueta "gire 90°". O Pillow não aplica isso sozinho; sem girar,
   o detector vê a gôndola deitada.
2. **O detector devolve caixas** — com confiança baixa de propósito (0,05).
3. **Filtra**, contando cada descarte:
   - confiança abaixo de `--confianca` (padrão 0,25);
   - caixa sem área dentro da foto;
   - caixa com algum lado abaixo de `--lado-minimo` (padrão 24 px) — ali não há
     rótulo legível, e o encoder só veria borrão.
4. **Agrupa em fileiras** e ordena cada uma da esquerda para a direita.
5. **Grava** crops, anotada e, por último, o manifesto.

### Decisões que valem explicar

**Por que o corte de confiança é aplicado fora do YOLO.** Se o YOLO cortasse em
0,25, as caixas de 0,2 sumiriam sem deixar rastro. Pedindo tudo acima de 0,05 e
cortando depois, o manifesto conta quantas ficaram de fora — é esse número que
diz se baixar o limiar recuperaria produto perdido.

**Por que `max_det=1000`.** O padrão do ultralytics é 300, e gôndola de bebidas
fotografada de longe passa disso. Teto baixo corta produto em silêncio: parece
que o detector não viu.

**Por que o nome do crop é a ordem de leitura, e não a ordem do detector.** A
ordem do YOLO é por confiança e muda de uma rodada para outra. `f02-p005` é
estável e diz onde o produto está; a Parte 11 precisa exatamente disso.

**Como a fileira é decidida.** As caixas são varridas de cima para baixo pelo
centro vertical. Uma caixa entra na fileira corrente se o centro dela estiver a
no máximo **meia altura típica** (a mediana das alturas) da média da fileira.
Meia altura separa duas prateleiras e tolera lata e garrafa lado a lado. Onde
falha: foto muito inclinada, em que a prateleira desce mais de meia altura de
uma ponta à outra — a fileira se parte em duas, e a `anotada.jpg` mostra isso
pelas cores.

**Por que PNG e não JPEG.** A foto já passou por uma compressão com perda no
celular. Salvar o crop em JPEG somaria uma segunda, que não existe na prateleira
e que o encoder aprenderia como se fosse sinal.

**Por que `detectar` recusa refazer uma foto.** Os rótulos da Parte 3 vão
apontar para `f02-p005.png` pelo nome. Refazer a detecção em silêncio pode pôr
outro produto atrás desse nome. Para refazer de propósito: `--substituir`. Ele
apaga só o que uma rodada anterior gerou e, se a nova rodada falhar antes de
gravar, a anterior fica intacta.

**Por que um protocolo `Detector`.** O recorte inteiro é testado com um detector
falso de dez linhas: sem GPU, sem pesos, sem ultralytics. E trocar de detector
mexe numa classe só.

## Os pesos

O detector é um YOLO treinado no **SKU-110K** — 11.762 fotos de prateleira com
cerca de 1,7 milhão de caixas, feito justamente para gôndola densa. Um YOLO
treinado no COCO, o padrão do ultralytics, conhece "garrafa" e "copo", não
"produto de prateleira": serve para ver o comando rodar, não para medir nada.

O ultralytics **não publica** pesos oficiais treinados no SKU-110K, só o dataset
pronto para treino (`SKU-110K.yaml`). Então há dois caminhos:

| Caminho | Custo | Risco |
|---|---|---|
| **Treinar você mesmo**: `yolo detect train data=SKU-110K.yaml model=yolo11n.pt` | Baixa ~13,6 GB de dataset; horas de GPU na RTX 4070 | Nenhum de procedência; você sabe exatamente o que tem |
| **Pesos de terceiros** já treinados (ex.: Hugging Face) | Minutos | O `.pt` é um pickle — **carregar executa código**. Só de origem em que você confia |

Isto **não** é "treinar detector do zero", que segue fora do escopo: o treino
parte de um YOLO pré-treinado no COCO e só ajusta para prateleira.

Coloque o arquivo em `data/modelos/detector.pt`, ou aponte com
`GONDOLA_PESOS_DETECTOR` ou `--pesos`. Pesos nunca vão para o git (`*.pt` está
no `.gitignore`); o hash deles vai para cada `deteccao.json`.

> **Licença.** O ultralytics é **AGPL-3.0**. Para estudo e portfólio aberto, não
> muda nada. Se a API da Parte 14 for servida para terceiros, a AGPL obriga a
> publicar o código do serviço — decida isso antes da Parte 14, não depois.

## Como rodar

Os testes não precisam do ultralytics:

```bash
.venv/Scripts/python.exe -m pytest
```

Para detectar de verdade, instale o grupo `deteccao`. Ele traz PyTorch; o pip,
no Windows, instala a versão só-CPU — para usar a RTX 4070, instale antes o torch
com CUDA pelo índice do PyTorch.

```bash
uv pip install -e ".[dev,deteccao]"
```

```bash
.venv/Scripts/python.exe -m gondola.cli detectar foto.jpg
```

Opções: `--confianca 0.25`, `--lado-minimo 24`, `--imgsz 640` (suba para 1280
se a foto for de longe e os produtos saírem pequenos), `--saida`, `--pesos`,
`--substituir`. Aceita várias fotos de uma vez; o modelo é carregado uma vez só.

## O que olhar quando rodar

Abra a `anotada.jpg` e anote no diário:

- **Produto sem caixa** — detecção perdida. Conte quantos numa foto; é a taxa de
  caixa perdida que a visão geral pede para medir antes de culpar o encoder.
- **Duas latas numa caixa só** — vira um facing a menos na Parte 13.
- **Etiqueta de preço com caixa** — falso positivo; a Parte 10 (limiar) vai
  precisar mandar isso para "não sei".
- **Duas cores na mesma prateleira** — fileira partida; foto inclinada demais.
- **A linha `descartadas`** — muitas "por confiança" sugere baixar `--confianca`.

## O que fica para depois, de propósito

Nenhuma medida formal de recall da detecção: isso exige caixas anotadas à mão, e
a Parte 3 já vai fazer você olhar cada crop. Nenhuma margem em volta da caixa:
decida quando o encoder (Parte 4) puder medir se ajuda. Nenhuma correção de
perspectiva para foto inclinada.

## Critério de ✅

- [x] `pytest` passa (46 testes; 19 desta parte)
- [x] `ruff check` e `mypy` limpos
- [ ] pesos do SKU-110K em `data/modelos/detector.pt`
- [ ] **você** rodou `gondola detectar` numa foto real de gôndola de bebidas e
      olhou a `anotada.jpg`
