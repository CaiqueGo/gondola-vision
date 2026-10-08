# gondola-vision

Reconhecimento de produtos em foto de gôndola: quais SKUs estão na prateleira e
quantos facings de cada. Construído **parte a parte**, em que cada melhoria é
medida contra um conjunto de crops rotulados à mão.

> Projeto de estudo: a meta é entender cada peça e por que ela existe, não
> montar um pipeline pronto. Por isso o baseline sem treino nenhum vem primeiro,
> e a avaliação vem antes das otimizações.

A aposta do projeto em uma linha: **isto não é classificação, é identificação
por similaridade** — o modelo é uma régua de semelhança, e o catálogo é um banco
de vetores que aceita produto novo com um `insert`.

## Por onde começar

1. [`docs/00-visao-geral.md`](docs/00-visao-geral.md) — o problema, a
   arquitetura e a razão de cada peça
2. [`docs/glossario.md`](docs/glossario.md) — cada termo técnico em uma linha
3. [`docs/partes/`](docs/partes/) — uma página por parte construída
4. [`docs/diario.md`](docs/diario.md) — o que deu errado, anotado na hora

## Estado atual

| Parte | Status |
|---|---|
| 0 — Documentação | ✅ pronto |
| 1 — Catálogo versionado | ✅ pronto |
| 2 — Detecção e crops | 🟡 código e testes prontos; falta rodar com pesos SKU-110K numa foto real |
| 3 a 14 | ⬜ a construir |

**Recorte decidido (08/10/2026):** bebidas não-alcoólicas, pela densidade de
pares confundíveis — ver [`00-visao-geral.md`](docs/00-visao-geral.md#o-recorte).

## As etapas

Cada parte é uma entrega testável: você roda um comando, vê um resultado e só
então seguimos. Nenhuma parte depende de código que ainda não existe.

### Etapa 1 — baseline congelado (sem treinar nada)

| # | Parte | Status | Entrega testável |
|---|---|---|---|
| 1 | [Catálogo versionado](docs/partes/01-catalogo.md) | ✅ | `gondola catalogo verificar` confere hash e cadastro de cada SKU |
| 2 | [Detecção e crops](docs/partes/02-deteccao.md) | 🟡 | `gondola detectar foto.jpg` salva um crop por facing |
| 3 | Conjunto de teste rotulado | ⬜ | `gondola dataset validar` sobre 300–500 crops reais seus |
| 4 | Galeria de referência | ⬜ | `gondola indexar --encoder dinov2` popula o índice |
| 5 | Busca e avaliação | ⬜ | `gondola avaliar` imprime top-1 e top-5 |
| 6 | **Comparação de encoders** | ⬜ | mesma tabela, uma linha por encoder congelado |

> **A Parte 6 é o marco de decisão do projeto.** A distância entre top-1 e top-5
> diz o que fazer a seguir: top-5 muito acima do top-1 significa que o encoder
> enxerga certo e só erra a ordem fina — vá para a Etapa 3, que é barata. Os dois
> baixos significam que o encoder não enxerga — aí sim Etapa 2.

### Etapa 2 — fine-tune (só se a Parte 6 mandar)

| # | Parte | Status | Entrega testável |
|---|---|---|---|
| 7 | Augmentation | ⬜ | top-1 sobe na mesma tabela, sem treino nenhum |
| 8 | Mineração de negativos difíceis | ⬜ | `gondola negativos minerar` lista os pares confundíveis |
| 9 | Fine-tune com ArcFace | ⬜ | top-1 sobe de novo; tempo de treino medido |

### Etapa 3 — produção

| # | Parte | Status | Entrega testável |
|---|---|---|---|
| 10 | Limiar e open-set | ⬜ | `gondola avaliar --limiar` reporta o tamanho do balde de revisão |
| 11 | Contexto de vizinho | ⬜ | top-1 sobe com custo de latência ~zero |
| 12 | Desempate por OCR | ⬜ | top-1 sobe nos pares confundíveis especificamente |
| 13 | Contagem de facings | ⬜ | `gondola contar foto.jpg` devolve facings e share of shelf |
| 14 | API | ⬜ | `POST /analisar` no Swagger |

**Regra do projeto:** uma parte só vira ✅ quando os testes dela passam e você
rodou o comando com os olhos. Anote o que deu errado em cada parte no
[`docs/diario.md`](docs/diario.md) — a seção "o que não funcionou" sai daí.

## Rodar agora

```bash
uv venv --python 3.11
```

```bash
uv pip install -e ".[dev]"
```

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m gondola.cli --help
```

## Resultados

_A tabela comparando encoders entra aqui a partir da Parte 5. As duas primeiras
linhas são congeladas, sem treino._

| Configuração | top-1 | top-5 | erro de facing | latência/crop |
|---|---|---|---|---|
| DINOv2 ViT-L/14 congelado | — | — | — | — |
| OpenCLIP ViT-L/14 LAION-2B congelado | — | — | — | — |

_Meça sempre as duas: top-1 é a métrica do modelo, erro de facing é a do
negócio, e elas divergem._

## O que não funcionou

_Ver [`docs/diario.md`](docs/diario.md); esta seção é destilada dele no fim._
