# 00 — Visão geral

## O problema

Você fotografa uma gôndola e quer saber **quais produtos estão ali e quantos
de cada**. Parece classificação de imagem, e é aí que o projeto dá errado.

Classificação supõe um conjunto fechado de classes. Catálogo de varejo não é
fechado: lança sabor novo toda semana, redesenha embalagem, sobe edição de
Natal. Um classificador de N SKUs exigiria retreinar a cada lançamento — e pior
que o custo é o **blind spot**: o intervalo em que o produto já está na
prateleira e o modelo ainda não sabe que ele existe.

Então a pergunta muda. Não *"que classe é isso?"*, mas:

> **De qual produto do meu catálogo este recorte mais se parece?**

Isso é **identificação por similaridade**, não classificação. O modelo deixa de
ser um nomeador com lista fixa e vira uma **régua de semelhança**; o catálogo
vira um banco de vetores que você edita com `insert`. Produto novo custa uma
foto, não uma GPU.

A analogia exata é reconhecimento facial: o FaceNet não é um classificador de
10.000 funcionários. Ele mede rostos, e cadastrar alguém é enfileirar mais um
vetor. Embalagem se comporta igual — duas fotos da mesma Coca Zero variam só em
luz, ângulo e oclusão, nunca em identidade visual.

Disso decorre a pergunta que organiza o projeto todo:

> **Quão boa é a régua?** Se o encoder não separa Zero de tradicional, nada
> depois disso salva.

## O recorte

**Uma categoria, uma rede, um conjunto fechado de fotos de teste.**

A recomendação é começar por **bebidas não-alcoólicas**: é a categoria com a
maior densidade de pares confundíveis (Zero vs tradicional, 350 vs 600, sabores
da mesma linha), que é exatamente o que você precisa estressar. Se funcionar
ali, funciona em mercearia. O caminho inverso não vale.

Alvo inicial: **100 a 300 SKUs**, com packshot e cadastro de marca/linha/
variante/tamanho. Grande o bastante para a cauda longa aparecer, pequeno o
bastante para você rotular o conjunto de teste sozinho.

> **Decisão em aberto.** A categoria acima é proposta minha, pela lógica de
> confundibilidade. Se o caso de uso real for outro (higiene, mercearia seca,
> perfumaria), troque aqui antes da Parte 1 — o recorte define o catálogo e o
> conjunto de teste, e refazer depois custa caro.

## A arquitetura

```
                    ┌────────── catálogo (offline) ───────────┐
  packshots  ──►  [1] catálogo versionado
                       (marca / linha / variante / tamanho)
                        │
                        ▼
                  [7] augmentation ──► [4] encoder ──►  galeria de
                                            ▲            referência
                                            │           (FAISS/pgvector)
                                       [9] fine-tune
                                         (ArcFace)  ◄── [8] negativos difíceis
                    └─────────────────────────────────────────┘

                    ┌────────── consulta (online) ────────────┐
  foto da  ──► [2] YOLO ──► crops ──► [4] encoder ──► [5] k-NN ──► top-5
  gôndola     (SKU-110k)                                            │
                                                                    ▼
                                                            [10] limiar
                                                             │        │
                                                     "não sei"        ▼
                                                    (revisão)   [12] OCR
                                                                (desempate)
                                                                      │
                                                                      ▼
                                                            [11] contexto
                                                             de vizinho
                                                                      │
                                                                      ▼
                                                        [13] facings por SKU
                                                            ──► [14] API
                    └─────────────────────────────────────────┘

  [3] conjunto de teste rotulado mede tudo o que vem depois dele
  [6] compara encoders congelados antes de qualquer treino
```

## Por que cada peça existe

**[1] Catálogo versionado.** Os packshots *são* o seu conjunto de classes. Sem
hash e data por imagem você não consegue dizer contra qual versão do catálogo
uma leitura foi feita — e quando a marca redesenha a embalagem, a acurácia cai
sem explicação. Os campos de marca/linha/variante/tamanho não são burocracia:
são o que gera os negativos difíceis de graça na Parte 8.

**[2] Detecção (YOLO + SKU-110K).** Achar *onde* está cada produto e achar *o
que* ele é são dois problemas, e só o primeiro está resolvido. O SKU-110K existe
justamente para prateleira densa — dezenas de objetos colados, com oclusão.
Detecção devolve caixa, nunca identidade; quem quiser resolver os dois de uma
vez com um modelo só vai falhar nos dois.

Onde falha: oclusão pesada e produto deitado. Meça a taxa de caixa perdida antes
de culpar o encoder por erro que nasceu aqui.

**[3] Conjunto de teste rotulado.** É a peça que separa este projeto de um
tutorial, e a mais trabalhosa. Crops **reais** de prateleira, anotados à mão, com
os pares confundíveis representados de propósito — não adianta um conjunto onde
90% é fácil.

O truque que torna isso viável para uma pessoa: **rotule por cluster**. Embeda
todos os crops, clusteriza, e rotula o cluster inteiro de uma vez. Cinquenta
Cocas viram um clique em vez de cinquenta.

**[4] Encoder.** A função imagem → vetor. Duas escolas, e elas erram em lugares
diferentes:

*CLIP* foi treinado com pares (imagem, legenda) e aprendeu **semântica** — sabe
o que é uma marca, uma lata, um refrigerante. Seu ponto cego é estrutural:
legenda de internet diz *"uma lata de Coca"*, nunca *"350ml e não 600ml"*. Ele
foi literalmente treinado para ser indiferente à distinção que é o seu problema.

*DINOv2* é auto-supervisionado — sem texto, sem rótulo. Aprendeu forma, textura
e layout. Não faz ideia do que é uma marca, mas é sensível a cor e disposição,
que é justamente o que separa a embalagem preta da vermelha.

Repara que a segunda descrição encaixa melhor no seu problema. Existe argumento
forte de que DINOv2 congelado é o baseline mais alto aqui — e existe argumento
oposto, de que o prior semântico do CLIP ajuda quando você for fine-tunar. **Não
decida no papo. É o que a Parte 6 mede.**

Sobre o `/14` do `ViT-L/14`: é o tamanho do patch em pixels. A 224×224, `/14` dá
256 patches contra 49 de um `/32`. Como a diferença entre Zero e tradicional mora
numa faixa estreita do rótulo, patch pequeno aqui é requisito, não capricho.

**[5] k-NN.** Calcula a distância do vetor do crop até todos os do catálogo e
pega os k menores. Não tem treino — é consulta. **É essa ausência de treino que
é o ponto inteiro da arquitetura**: produto novo entra com um `insert`.

Use cosseno (ângulo), não distância bruta: o comprimento do vetor tende a
codificar intensidade, e você só quer direção. Normalize em L2 e os dois passam
a dar a mesma ordenação.

E **não ligue índice aproximado agora**. FAISS com IVF/PQ é rápido porque erra um
pouquinho de propósito, e se você ligar isso no dia 1 vai passar semanas sem
saber se a perda veio do índice ou do encoder. Força bruta (`IndexFlatIP`, ou o
`pgvector` que você já roda) aguenta esta escala com folga.

**[6] Comparação de encoders congelados.** *Congelado* é usar o backbone como
veio, sem tocar num parâmetro: zero GPU, zero risco. Esta parte é o mesmo código
com o encoder trocado — duas linhas de diferença, duas linhas na tabela.

Ela existe por dois motivos. Primeiro, você descobre em dois dias se o problema é
fácil ou difícil **no seu catálogo**, que é a única informação que importa.
Segundo, tudo que vier depois precisa de um número para bater; sem baseline você
não distingue melhoria de placebo.

**[7] Augmentation.** Aqui mora o inimigo do projeto: o **domain gap**. Seus
packshots são estúdio, fundo branco, 3000px. Seus crops são celular, de baixo,
com reflexo do LED do freezer, 80×140px, 30% tampados. São duas distribuições
diferentes, e um encoder genérico aprendeu que elas são *diferentes* — que é
exatamente o que você precisa desaprender.

A augmentation faz o packshot apanhar no treino (warp de perspectiva, blur,
downscale agressivo, brilho, JPEG, oclusão de borda) para fabricar
artificialmente a condição de prateleira. É barata e frequentemente sozinha já
move o número — meça ela isolada, antes de fine-tunar.

**[8] Mineração de negativos difíceis.** Um *negativo* é o que deve ficar longe.
Um *negativo difícil* é um SKU genuinamente diferente que o modelo **hoje** acha
parecido.

Se você sorteia negativos aleatórios, está pareando Coca Zero com sabão em pó. O
modelo já separa isso perfeitamente — loss perto de zero, gradiente perto de
zero, GPU queimada à toa. O sinal de aprendizado mora inteiro nos pares
confundíveis.

Duas fontes. A automática: roda o encoder da Parte 6, pega para cada produto os
vizinhos mais próximos que são SKU errado, e re-minera periodicamente conforme o
modelo melhora. A de graça: **o próprio catálogo** — mesma marca + mesma linha +
variante diferente é negativo difícil garantido, direto de um `GROUP BY`.

Cuidado com o extremo: minerar só o topo pesca ruído de rótulo e duplicata real
(dois SKUs que são a mesma imagem com código de barras diferente) e desestabiliza
o treino. Fique no *semi-hard*.

**[9] Fine-tune com ArcFace.** *Metric learning* é treinar a **geometria do
espaço** ("aproxime estes, afaste aquele") em vez de treinar rótulos. É como se
ensina uma régua — e régua funciona em produto que ela nunca viu.

Não use *triplet loss*: exige escolher as trincas, a esmagadora maioria já está
satisfeita (gradiente zero), e o treino instabiliza em muitas classes.

**ArcFace** veio de reconhecimento facial, que tem o mesmo formato de problema:
milhares de identidades, cauda longa, e precisa funcionar em rosto inédito. Ele
normaliza tudo numa hiperesfera — distância vira **ângulo** — e exige que a
classe certa vença por uma **margem angular** extra, tornando a tarefa
artificialmente mais difícil para que os grupos terminem mais compactos.

E então o movimento que confunde todo mundo: **existe uma cabeça de classificação
durante o treino, e você a joga fora no fim**. Ela era andaime para forçar boa
geometria. O que vai para produção é o encoder.

Um risco real: *catastrophic forgetting* — o fine-tune apagar o conhecimento
geral do backbone e piorar tudo. CLIP é notoriamente frágil nisso. O antídoto é
learning rate por bloco: alto em cima (específico da tarefa), decrescente
descendo (visão genérica). A receita do RetailKLIP é 2e-4 no último bloco e ×0.7
por bloco para trás — não é número mágico, é "quanto mais fundo, mais delicado".

**[10] Limiar e open-set.** O k-NN **sempre** devolve um vizinho, mesmo quando o
crop é uma etiqueta de preço, uma mão, ou um produto que não está no catálogo.
Sem um corte de distância você força top-1 e gera lixo silencioso, que é o pior
tipo de erro porque não aparece em métrica agregada.

A classe *"não sei"* não é desistência, é requisito. E o tamanho do balde de
revisão é seu alarme: quando ele cresce, o catálogo envelheceu.

**[11] Contexto de vizinho.** Os produtos numa gôndola **não são independentes**,
e tratar cada crop isoladamente joga fora a informação mais barata que existe.
Reposição agrupa o mesmo SKU em bloco contíguo — é como o repositor trabalha, não
é coincidência estatística. Se cinco vizinhos são Coca Zero com alta confiança e o
sexto está em dúvida, ele é Zero.

Suavização por maioria ao longo da fileira: ganho grande, custo computacional
perto de zero. É a melhor relação esforço/resultado do projeto inteiro.

**[12] Desempate por OCR.** O texto da embalagem é discriminativo exatamente onde
o vetor visual falha: "ZERO", "600ml", o sabor. Rodar OCR no crop e usar como
segundo sinal resolve a classe de erro mais cara.

A forma mais simples: os 5 candidatos do k-NN viram uma escolha entre 5 opções,
com o texto do OCR como evidência. Dá para fazer com regra, com um modelo de
decisão tipada, ou com um LLM pequeno — decida quando chegar aqui, medindo.

Só entre nesta parte se a Parte 6 mostrar top-5 muito acima do top-1. Se os dois
estiverem baixos, o problema é o encoder e OCR não salva.

**[13] Contagem de facings.** A métrica do negócio. Um *facing* é uma unidade
visível na frente da prateleira, e **share of shelf** — seus facings sobre o
total — é o número que a marca paga para saber.

Duas armadilhas. Primeira: facing **não é estoque**; atrás da lata da frente pode
ter mais dez ou nenhuma, e a foto não sabe. Não prometa inventário. Segunda: erro
de contagem diverge do top-1 de um jeito não óbvio — 85% de top-1 pode virar
share of shelf quase perfeito (erros se cancelam entre SKUs) ou desastroso (erros
se concentram todos num par confundível, e uma marca some do relatório). **Meça
as duas.**

**[14] API.** Um endpoint que recebe foto e devolve facings por SKU, com o balde
de revisão explícito na resposta. Swagger basta.

## Stack

Python 3.11 · PyTorch · ultralytics (YOLO) · open_clip_torch · timm (DINOv2) ·
pytorch-metric-learning (ArcFace) · FAISS ou pgvector · OpenCV · FastAPI · uv.

## O que fica de fora, sem dó

App mobile, UI de captura, multi-loja, gestão de planograma, detecção de etiqueta
de preço, inferência de estoque real, treinar detector do zero (use o SKU-110K
pré-treinado), e qualquer dashboard. Nada disso testa a régua, e todos consomem
semanas.

## Ordem de estudo

Não estude tudo antes de codar. Siga a ordem das partes: catálogo → detecção →
conjunto de teste → **baseline congelado medido** → só então treino. Cada
conceito faz muito mais sentido depois que você viu o problema que ele resolve
acontecer no seu terminal — e metade deles talvez você nem precise, porque o
baseline já resolveu.
