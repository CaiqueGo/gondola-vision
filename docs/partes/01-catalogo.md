# Parte 1 — Catálogo versionado

**Status:** ✅ pronto para você testar
**Depende de:** nada
**Habilita:** Parte 2 (detecção), Parte 4 (galeria de referência), Parte 8 (negativos difíceis)

---

## Objetivo

Ter uma lista explícita e verificável de quais SKUs o sistema conhece, com prova
de que cada packshot em disco é exatamente aquele que foi registrado — e com o
cadastro estruturado do jeito que o treino vai precisar depois.

## Que problema isso resolve

Quatro, e todos aparecem só lá na frente se você não resolver agora.

**1. "Contra qual versão do catálogo esse número foi medido?"** Marca redesenha
embalagem. Se alguém substituir um packshot mantendo o nome do arquivo, a
acurácia cai semanas depois e você não tem como saber por quê. O hash transforma
isso de mistério em erro na hora.

**2. O cadastro é insumo de treino, não burocracia.** `marca`, `linha`,
`variante` e `tamanho` não estão ali para relatório. É deles que sai, de graça, a
lista de negativos difíceis da Parte 8: dois SKUs da mesma linha que só diferem
na variante formam exatamente o par que o encoder precisa aprender a separar. Se
o cadastro estiver sujo aqui, o treino lá é ruim e você não vai saber por quê.

**3. As imagens não cabem no git.** O que vai para o repositório é o
*manifesto*: um YAML pequeno, legível no diff, que descreve o catálogo. Quem
clonar traz as imagens à parte, e o `verificar` prova que tem os mesmos bytes.

**4. Duas armadilhas conhecidas passam batido por meses.** Packshot compartilhado
entre dois SKUs (acontece: produto com dois EANs e uma foto só) e grafia
inconsistente no cadastro. A primeira dá ao treino um par rotulado como negativo
que é visualmente idêntico. A segunda quebra o agrupamento da Parte 8 em
silêncio. São baratas de pegar aqui e caras de descobrir na Parte 9.

## O que foi construído

```
src/gondola/
├── config.py                  onde os dados moram (GONDOLA_DATA_DIR)
├── cli.py                     adicionar, selar, listar, verificar
└── catalogo/
    ├── modelos.py             SKU, Packshot, Catalogo (Pydantic) + normalizar()
    ├── manifesto.py           carregar, salvar, adicionar, selar, sha256
    └── verificacao.py         as checagens e o relatório
scripts/
└── gerar_exemplo.py           um catálogo de brinquedo para ver funcionando hoje
```

### O modelo `SKU`

| Campo | Para quê |
|---|---|
| `id` | Chave curta e estável. Vira o rótulo em todo o pipeline — por isso é validado por regex e não muda |
| `nome` | Legibilidade |
| `marca`, `linha`, `variante` | Os eixos de agrupamento; geram os negativos difíceis da Parte 8 |
| `tamanho`, `unidade` | O outro eixo confundível. Numérico, não texto, para poder comparar |
| `embalagem` | Lata e PET do mesmo produto são visualmente distintos |
| `ean` | Código de barras, quando houver |
| `packshots` | As imagens de referência. Uma já funciona; mais de uma ajuda |
| `registrado_em`, `observacoes` | Quando entrou, e suas notas |

`extra="forbid"` no schema: um campo com nome errado no YAML vira erro no
carregamento, não um valor silenciosamente ignorado.

### Cadastrar e selar são dois passos

`adicionar` copia a imagem e registra o SKU, **sem gravar hash**. `selar` grava
hash, bytes e dimensões. A separação é de propósito: cadastrar em lote e fechar a
versão são coisas que você quer revisar uma de cada vez.

E `selar` **não resela em silêncio** um packshot cujo conteúdo mudou. Ele reporta
`divergente` e sai com código 1; para aceitar a troca você passa `--resselar`,
depois de olhar o que mudou. Reselar sozinho destruiria justamente a informação
que o hash existe para dar.

### O que `verificar` checa

| Código | Nível | O que pega |
|---|---|---|
| `id_duplicado` | erro | Mesmo id duas vezes no manifesto |
| `sku_sem_packshot` | erro | SKU que nunca poderá ser reconhecido |
| `packshot_ausente` | erro | Declarado no manifesto, não está em disco |
| `packshot_nao_selado` | erro | Sem hash; cadastro não fechado |
| `hash_divergente` | erro | **A embalagem redesenhada** |
| `imagem_ilegivel` | erro | Arquivo que o Pillow não abre |
| `imagem_pequena` | aviso | Menor lado < 256px; não sobrevive à augmentation da Parte 7 |
| `packshot_orfao` | aviso | Imagem em disco que nenhum SKU referencia |
| `packshot_compartilhado` | erro | Dois SKUs, a mesma imagem — inseparáveis por imagem |
| `grafia_inconsistente` | aviso | `Coca-Cola` e `coca cola` viram dois grupos |

Sai com código 1 se houver erro, o que permite usar no CI.

### Decisões que valem explicar

**Por que SHA-256 e não data de modificação.** Data muda ao copiar arquivo entre
máquinas; hash não. O hash é a única afirmação que se sustenta em CI.

**Por que `normalizar()` não remove acento.** `limao` e `limão` são grafias
diferentes do mesmo produto, e a verificação deve **reclamar** disso em vez de
esconder. Normalização silenciosa demais vira cadastro sujo que ninguém vê.

**Por que o par confundível conta um eixo de cada vez.** Um par só entra na conta
quando compartilha (marca, linha) e difere *ou* na variante *ou* no tamanho —
nunca nos dois. Par que difere nos dois eixos é visualmente mais fácil, e inflar
a conta com ele daria falsa sensação de catálogo bem preparado.

**Por que o relatório mostra os pares confundíveis já na Parte 1.** É o sinal de
que o catálogo tem o que o treino vai precisar. Catálogo com zero par confundível
não é catálogo fácil: é catálogo que não exercita nada, e a Parte 8 não terá o
que minerar.

**Por que as funções recebem caminho por parâmetro.** `adicionar_sku` não chama
`config.dir_packshots()` por dentro — recebe `dir_packshots`. É o que permite
testar em `tmp_path` sem nenhum mock, e é o padrão do projeto inteiro.

**Por que a saída da CLI é ASCII puro.** Console do Windows mastiga caractere
fora do codepage e você perde a leitura do relatório.

## Como rodar

```bash
uv venv --python 3.11
```

```bash
uv pip install -e ".[dev]"
```

```bash
.venv/Scripts/python.exe -m pytest
```

Para ver funcionando sem ter packshot nenhum ainda:

```bash
.venv/Scripts/python.exe scripts/gerar_exemplo.py
```

```bash
GONDOLA_DATA_DIR=exemplo .venv/Scripts/python.exe -m gondola.cli catalogo verificar
```

O exemplo tem seis SKUs (quatro Coca-Cola em 2 variantes × 2 tamanhos, dois
Guaraná em 2 variantes) e deve reportar **5 pares confundíveis**. As imagens são
retângulos de cor chapada — placeholders. A Parte 1 não interpreta o conteúdo da
imagem, então servem para exercitar a ferramenta inteira; você troca por packshot
real na Parte 4.

Para cadastrar de verdade:

```bash
.venv/Scripts/python.exe -m gondola.cli catalogo adicionar foto.png --id coca-zero-350-lata --nome "Coca-Cola Zero Lata 350ml" --marca Coca-Cola --linha Original --variante zero --tamanho 350 --unidade ml --embalagem lata
```

```bash
.venv/Scripts/python.exe -m gondola.cli catalogo selar
```

## O que fica para depois, de propósito

Nada de imagem é *interpretado* aqui — só hash e dimensões. Embedding é Parte 4.
Não há importação em lote de planilha: quando o catálogo real chegar e tiver 300
SKUs, isso vira um comando, mas inventar o formato antes de ver a planilha de
verdade é desperdício.

## Critério de ✅

- [x] `pytest` passa (27 testes)
- [x] `ruff check` e `mypy` limpos
- [x] `catalogo verificar` sai 0 num catálogo íntegro e 1 num corrompido
- [ ] **você** rodou com os olhos e cadastrou ao menos um SKU real
