# Parte 2 — Detecção e crops

**Status:** 🟡 detector treinado e comando validado; falta rodar numa foto sua
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
pronto para treino (`SKU-110K.yaml`). Havia dois caminhos, e o escolhido foi
**treinar aqui**:

| Caminho | Custo | Risco |
|---|---|---|
| **Treinar você mesmo** (escolhido) | Baixa ~11,4 GB de dataset; ~2 min por época na RTX 4070 | Nenhum de procedência; você sabe exatamente o que tem |
| **Pesos de terceiros** já treinados (ex.: Hugging Face) | Minutos | O `.pt` é um pickle — **carregar executa código**. Só de origem em que você confia |

Isto **não** é "treinar detector do zero", que segue fora do escopo: o treino
parte do YOLO11s pré-treinado no COCO e só ajusta para prateleira.

### Como o treino roda

```bash
GONDOLA_DIR_DATASETS=E:/datasets .venv/Scripts/python.exe scripts/treinar_detector.py --piloto
```

```bash
GONDOLA_DIR_DATASETS=E:/datasets .venv/Scripts/python.exe scripts/treinar_detector.py --instalar
```

- **Onde fica o dataset.** O SKU-110K passa de 20 GB no pico (o tar mais a
  extração). `GONDOLA_DIR_DATASETS` aponta para outro disco; sem ela, vai para
  `data/datasets/`. O script reescreve o YAML do ultralytics com caminho
  absoluto, para não mexer na configuração global dele.
- **O piloto vem antes.** São 10% do treino em 5 épocas. Ele baixa o dataset na
  primeira vez, mede quanto custa uma época e confirma que o mAP sai do zero.
- **Treino completo:** até 100 épocas, `imgsz` 640, batch 8, `patience` 15
  (para quando a validação passa 15 épocas sem melhorar). As rodadas ficam em
  `data/treino/`.
- **`max_det=1000` também na validação.** Com o padrão de 300, foto densa perde
  caixa e o mAP medido sai menor do que é.
- **`--instalar`** copia o `best.pt` para `data/modelos/detector.pt`, que é de
  onde `gondola detectar` lê (ou `GONDOLA_PESOS_DETECTOR`, ou `--pesos`). Pesos
  nunca vão para o git (`*.pt` está no `.gitignore`); o hash deles vai para cada
  `deteccao.json`.

### Resultados

| Rodada | Dados | Épocas | mAP50 | mAP50-95 | Tempo |
|---|---|---|---|---|---|
| Piloto | 10% do treino | 5 | 0,824 | 0,476 | 2,2 min |
| Completo | 100% | 75 (melhor: 60) | **0,926** | **0,576** | 2,4 h |

O treino completo parou sozinho na época 75: a validação não melhorou nas 15
épocas depois da 60. A curva subiu rápido (0,49 de mAP50-95 na época 1, 0,55
na 11, 0,57 na 31) e ficou no platô dali em diante. Precisão 0,911 e recall
0,870 na melhor época. Pesos: `sha256 9990d75a75d3…`, 19,2 MB.

O mAP é medido nas 588 fotos de validação do SKU-110K, que não são de bebidas
nem do Brasil. É a nota do detector em prateleira genérica; a nota que importa
para este projeto sai das suas fotos, na Parte 3.

> **Licença do SKU-110K.** As fotos são da Trax, liberadas **só para uso
> acadêmico e não comercial**, proibida a redistribuição e a criação de obras
> derivadas. Se pesos treinados nelas contam como "obra derivada" é juridicamente
> incerto. Na prática: estudo e portfólio, sim; **não publique os pesos** (Hugging
> Face, release do GitHub) e não use comercialmente sem resolver isso antes.

> **Licença.** O ultralytics é **AGPL-3.0**. Para estudo e portfólio aberto, não
> muda nada. Se a API da Parte 14 for servida para terceiros, a AGPL obriga a
> publicar o código do serviço — decida isso antes da Parte 14, não depois.

## Como rodar

Os testes não precisam do ultralytics:

```bash
.venv/Scripts/python.exe -m pytest
```

Para detectar de verdade, instale o grupo `deteccao`. Ele traz o PyTorch, e o
pip, no Windows, instala a versão só para CPU. Para usar a RTX 4070, instale
**antes** o torch com CUDA pelo índice do PyTorch; o `uv pip install` seguinte
mantém o que já está instalado.

```bash
uv pip install torch==2.14.1 torchvision --index-url https://download.pytorch.org/whl/cu130
```

```bash
uv pip install -e ".[dev,deteccao]"
```

O ultralytics vem com telemetria ligada (`sync: true` no `settings.json` dele).
Desligue uma vez por máquina:

```bash
.venv/Scripts/yolo.exe settings sync=False
```

```bash
.venv/Scripts/python.exe -m gondola.cli detectar foto.jpg
```

Opções: `--confianca 0.25`, `--lado-minimo 24`, `--imgsz 640` (suba para 1280
se a foto for de longe e os produtos saírem pequenos), `--saida`, `--pesos`,
`--substituir`. Aceita várias fotos de uma vez; o modelo é carregado uma vez só.

### Dependências auditadas (08/10/2026)

`pip-audit` sobre o ambiente resolvido, não sobre o `pyproject.toml`:

| Pacote | Achado | Decisão |
|---|---|---|
| torch 2.11.0 | CVE-2025-3000, corrupção de memória em `torch.jit.script` | Não usamos JIT, mas a correção era barata: atualizado para **2.14.1+cu130** |
| setuptools 78.1.0 (veio com o torch) | CVE-2025-47273, path traversal no `PackageIndex`; CVE-2026-59890, exclusão de sdist no macOS | Nenhum dos dois caminhos é usado; atualizado para **84.0.0** mesmo assim |

O dataset vem por **HTTP sem TLS** (`trax-geometry.s3.amazonaws.com`, a URL que o
próprio ultralytics usa) e sem checksum publicado. É imagem e CSV, não código,
mas não há como provar que chegou intacto. Algumas fotos da validação disparam
"Corrupt JPEG data" no decodificador a cada passada (são poucas, com 4 tipos de
aviso); a varredura do ultralytics as aceita (`0 corrupt`), e o defeito é
conhecido no dataset original.

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
- [x] pesos do SKU-110K em `data/modelos/detector.pt` (mAP50-95 0,576 na validação)
- [x] `gondola detectar` rodado com os pesos reais em duas fotos de bebidas da
      validação do SKU-110K (281 e 137 crops)
- [ ] **você** rodou `gondola detectar` numa foto real de gôndola de bebidas e
      olhou a `anotada.jpg`
