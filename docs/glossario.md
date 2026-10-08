# Glossário

Todo termo técnico do projeto, em uma linha. Se algo aparecer num documento e
não estiver aqui, é bug da documentação.

## Domínio: varejo

**SKU** — Stock Keeping Unit: a unidade de catálogo. Coca Zero lata 350ml e Coca
Zero garrafa 600ml são **SKUs diferentes**, e distingui-las é o problema inteiro.

**Gôndola** — a estante de exposição. Uma foto de gôndola tem dezenas de produtos
densamente empacotados, com oclusão e ângulo.

**Facing** — uma unidade do produto visível na frente da prateleira. Cinco Cocas
lado a lado são cinco facings. É a unidade de medida do negócio.

**Facing ≠ estoque** — atrás da lata da frente pode ter mais dez ou nenhuma. A
foto mede fachada, não inventário; não prometa contagem de estoque.

**Share of shelf** — seus facings dividido pelo total de facings. É a métrica que
a marca paga para saber.

**Planograma** — o mapa de como a gôndola *deveria* estar montada. Quando existe,
é um prior forte para desambiguar leitura.

**Ruptura** — o produto que deveria estar e não está (out of stock). Cai fora da
detecção: é comparação do detectado contra o planograma, aritmética pura.

**Packshot** — a foto oficial do produto: fundo branco, frontal, estúdio, alta
resolução. É a imagem de referência que popula o catálogo.

**In vitro / in situ** — como a literatura chama packshot e foto de prateleira. A
distância entre os dois é o domain gap.

## Detecção

**Detecção de objetos** — achar *onde* está cada objeto na imagem, devolvendo
caixas. Não diz o que é cada um.

**Bounding box** — o retângulo que delimita um objeto detectado.

**YOLO** — família de detectores de objeto em uma passada, rápida. É a primeira
etapa do pipeline, e é problema resolvido aqui.

**Crop** — o recorte da imagem dentro de uma bounding box. É o que entra no
encoder.

**Retificação de perspectiva** — endireitar o crop quando a foto foi tirada de
ângulo, antes de embedar.

**Oclusão** — produto parcialmente tampado por outro, por etiqueta de preço ou
pela mão de alguém. Principal fonte de erro em prateleira cheia.

## Embedding e busca

**Encoder** — a função que recebe uma imagem e devolve uma lista de números. É a
peça que você treina; todo o resto é consulta.

**Embedding** — o vetor devolvido pelo encoder. Imagens parecidas produzem
vetores próximos; é essa propriedade, e só ela, que faz o sistema funcionar.

**Dimensão** — quantos números tem o vetor. CLIP ViT-L/14 devolve 768, DINOv2
ViT-L/14 devolve 1024.

**Similaridade de cosseno** — mede o ângulo entre dois vetores, ignorando o
tamanho; é como se compara embeddings.

**Normalização L2** — encolher todo vetor para comprimento 1. Depois disso,
cosseno e distância euclidiana dão a mesma ordenação.

**k-NN** — k vizinhos mais próximos: calcula a distância do vetor novo até todos
os do catálogo e pega os k menores. **Não tem treino, é consulta.**

**Galeria de referência** — o índice de vetores do catálogo, um ou mais packshots
por SKU. Produto novo é um `insert`, não um retreino.

**FAISS** — biblioteca de busca por similaridade em escala, com índices
aproximados.

**Busca aproximada (ANN)** — troca um pouco de exatidão por muita velocidade.
**Não ligue no dia 1**: vira uma fonte de erro que você não consegue separar do
erro do encoder.

**Limiar de distância** — o corte abaixo do qual você recusa responder. Sem ele o
k-NN sempre devolve alguma coisa, inclusive para etiqueta de preço e mão.

**Open-set** — o cenário real: aparecem produtos fora do seu catálogo. Exige a
classe "não sei"; classificação fechada não tem isso.

**pgvector** — extensão do Postgres que guarda vetores e busca por similaridade
dentro do banco. Dá conta da escala inicial sem peça nova.

## Modelos

**Backbone** — o modelo pré-treinado usado como ponto de partida.

**ViT** — Vision Transformer: pica a imagem em quadradinhos, trata cada um como
"palavra" e roda um Transformer. Substituiu a CNN como padrão de embedding.

**Patch** — o quadradinho. `/14` significa 14×14 pixels: mais patches, mais
detalhe fino percebido, mais conta para fazer.

**ViT-L/14** — variante Large (~300M parâmetros), patch de 14px. O `/14` importa
aqui porque a diferença entre Zero e tradicional mora em região pequena.

**CLIP** — encoder treinado com pares (imagem, legenda), aproximando cada imagem
da legenda dela e afastando das outras. Aprende semântica.

**O ponto cego do CLIP** — legenda de internet diz "uma lata de Coca", nunca
"350ml e não 600ml". Ele foi treinado para ser indiferente à distinção que é o
seu problema. Por isso o fine-tune não é opcional.

**OpenCLIP** — reimplementação aberta do CLIP, licença permissiva.

**LAION-2B** — os 2 bilhões de pares imagem-texto (raspagem da web) em que esses
pesos foram treinados. Mesma arquitetura + dados diferentes = outro modelo.

**DINOv2** — encoder auto-supervisionado da Meta: sem texto, sem rótulo. Aprende
forma, textura e layout em vez de semântica.

**Auto-supervisionado** — treina forçando dois recortes da *mesma* imagem a
produzir o mesmo vetor. Ninguém diz ao modelo o que é o objeto.

**CLIP vs DINOv2** — CLIP sabe o que é uma marca; DINOv2 é mais sensível a cor e
layout, que é o que separa Zero de tradicional. **Meça os dois, não escolha no
papo.**

## Treino

**Congelado (frozen)** — usar o backbone como veio, sem atualizar um parâmetro.
Zero GPU, zero risco. É a etapa 1.

**Fine-tune** — continuar treinando os pesos pré-treinados nos seus dados. Não é
treinar do zero, é empurrar de leve.

**Catastrophic forgetting** — o fine-tune apagar o conhecimento geral do
backbone. CLIP é frágil nisso; é o risco real de piorar em vez de melhorar.

**Learning rate por bloco** — LR alto nos blocos de cima (específicos da tarefa)
e decrescente descendo (visão genérica). No RetailKLIP: 2e-4 no último, ×0.7 por
bloco para trás. É o antídoto contra o esquecimento.

**Metric learning** — treinar a *geometria do espaço* ("aproxime estes, afaste
aquele") em vez de treinar rótulos. É como se ensina uma régua.

**Triplet loss** — âncora, positivo e negativo, com margem. **Evite**: exige
escolher as trincas, a maioria é fácil demais, e o treino instabiliza.

**ArcFace** — normaliza tudo numa hiperesfera (distância vira ângulo) e exige que
a classe certa vença por uma **margem angular** extra. Estável, escala para
milhares de classes, aguenta cauda longa.

**Cabeça de classificação** — a camada final usada durante o treino do ArcFace e
**jogada fora depois**. Era andaime para forçar boa geometria; o que vai para
produção é o encoder.

**Cauda longa** — a distribuição real do catálogo: uns poucos SKUs com milhares
de fotos e a maioria com menos de dez. É por isso que a loss veio de
reconhecimento facial.

**Negativo difícil** — um SKU genuinamente diferente que o modelo *hoje* acha
parecido: Zero vs tradicional, 350 vs 600, morango vs framboesa.

**Hard negative mining** — ir atrás desses pares em vez de sortear. Negativo
aleatório (Coca vs sabão em pó) tem gradiente ~zero: queima GPU sem aprender
nada.

**Mineração pelo catálogo** — atalho de graça: mesma marca + mesma linha +
variante diferente é negativo difícil garantido, direto de um `GROUP BY`.

**Semi-hard** — difícil, mas não o extremo. Minerar só o topo pesca ruído de
rótulo e duplicata real, e desestabiliza o treino.

**Augmentation** — maltratar o packshot no treino (warp, blur, downscale, brilho,
JPEG, oclusão) para fabricar artificialmente a condição de prateleira.

**Domain gap (catalog-to-real)** — a distância entre packshot de estúdio e crop
de celular. É onde a acurácia morre, e fechá-lo é o trabalho da etapa 2.

## Avaliação

**Top-1** — fração dos crops de teste em que o vizinho mais próximo era o SKU
certo.

**Top-5** — fração em que o SKU certo estava entre os 5 mais próximos.

**A distância entre top-1 e top-5** — o diagnóstico que importa. Top-1 60% com
top-5 95% = o encoder vê certo e erra a ordem fina (conserta com OCR e contexto,
é barato). Top-1 60% com top-5 63% = o encoder não enxerga (exige fine-tune).

**Erro de contagem de facings** — a métrica de negócio. Diverge do top-1: os
erros podem se cancelar entre SKUs ou se concentrar todos num par confundível.
Meça as duas.

**Rotulagem por cluster** — em vez de rotular crop a crop, embeda tudo,
clusteriza e rotula o cluster inteiro de uma vez. Reduz o custo em uma ordem de
grandeza; é o que torna o projeto viável para uma pessoa.

**Contexto de vizinho** — usar o fato de que facings do mesmo SKU ficam
contíguos: suavizar por maioria ao longo da fileira. Ganho grande, custo ~zero.

## Datasets

**SKU-110K** — detecção em prateleira densa. Só caixas, sem identidade de
produto. É o que resolve a etapa de detecção.

**Grozi-120** — 120 produtos, um packshot no treino e fotos reais no teste. O
dataset que mede exatamente o domain gap.

**RP2K** — 2.388 produtos de varejo, com bastante foto por classe.

**CAPG-GP** — one-shot com produtos fine-grained, mas treino e teste no mesmo
domínio (não mede domain gap).

**RP6K** — a base interna (não pública) usada para treinar o RetailKLIP: 6.500
produtos, mais de 1 milhão de imagens.
