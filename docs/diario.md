# Diário de bordo

Anote aqui, **enquanto acontece**, tudo que quebrou, surpreendeu ou foi
abandonado. No fim do projeto é impossível lembrar, e é exatamente daqui que sai
a seção "o que não funcionou" do README — a que sinaliza experiência real.

Formato: data, parte, o que aconteceu, o que você fez.

---

## 2026-09-21 — Parte 0

- Documentação escrita: visão geral, glossário, este diário.
- Arquitetura decidida: identificação por similaridade (encoder + k-NN), não
  classificação de N classes. Motivo: catálogo de varejo não é conjunto fechado.
- Em aberto: a categoria do recorte.

---

## 2026-09-21 — Parte 1

- Catálogo versionado pronto: 27 testes, ruff e mypy limpos.
- Decisão: `adicionar` e `selar` são comandos separados, e `selar` recusa
  reselar em silêncio um packshot que mudou. Reselar sozinho apagaria a única
  informação que o hash existe para dar.
- Duas checagens entraram por antecipação de dor futura, não por requisito:
  packshot compartilhado entre dois SKUs e grafia inconsistente. Ambas são
  invisíveis até desestabilizarem o treino da Parte 9.
- O relatório já conta os pares confundíveis disponíveis para a Parte 8. No
  catálogo de exemplo (6 SKUs) dá 5 pares — bate com a conta à mão.
- Saída da CLI em ASCII puro: o `·` saiu mastigado no console do Windows.
- (anote aqui o que você observar ao cadastrar os SKUs de verdade)

---

## 2026-10-08 — Parte 2

- Recorte decidido: bebidas não-alcoólicas.
- Código da detecção pronto com 19 testes novos (46 no total), ruff e mypy
  limpos. Tudo testado com um detector falso; o ultralytics ainda não foi
  instalado nem rodado.
- O teste da mensagem "ultralytics não instalado" pegou um bug de verdade: o
  Rich leu `[dev,deteccao]` como tag de markup e engoliu o texto, e a mensagem
  dizia para instalar `"."`. Texto que vem de fora (erro, caminho) agora passa
  por `rich.markup.escape` no comando `detectar`. Os comandos da Parte 1 têm o
  mesmo risco com caminho que contenha colchete.
- Decisão: o corte de confiança fica fora do YOLO (que roda com piso de 0,05),
  para o manifesto contar quantas caixas o limiar descartou.
- Pendente: pesos do SKU-110K. O ultralytics não publica pesos oficiais; ou
  treina, ou usa de terceiro (é pickle, só de origem confiável).
- Decidido treinar no SKU-110K em vez de usar pesos de terceiros. O C: tinha
  35 GB livres e o dataset passa de 20 GB no pico; foi para `E:\datasets`
  (`GONDOLA_DIR_DATASETS`).
- O download caiu uma vez por timeout e recomeçou; 11,4 GB levaram ~2h30.
- **O que esperava:** piloto de 1 época (10%) com mAP baixo, mas não zero.
  **O que aconteceu:** mAP 0, perda de validação `NaN`, e o modelo devolvendo
  caixas sem sentido com confiança 1,0. **Por que:** 1 época de 10% são ~103
  iterações, e o ultralytics passa as primeiras ~309 em warmup, com taxa de
  0,1 no bias; o piloto terminou no meio dele. Antes de achar isso, descartei
  rótulo errado (o `train_batch0.jpg` mostra as caixas certas), NaN nos pesos
  (nenhum) e fp16 (fp32 também deu zero). **O que fiz:** piloto passou a 5
  épocas. **Número antes / depois:** mAP50 0 → 0,824 (mAP50-95 0,476).
- Validação de teste rodada com o script via stdin travou: no Windows, os
  workers do DataLoader não conseguem reimportar um script que veio do stdin.
  Script de verdade em arquivo, com `if __name__ == "__main__"`.
- `pip-audit` achou CVEs no torch 2.11 e no setuptools 78.1; nenhuma no nosso
  caminho de uso, mas a correção era barata: torch 2.14.1+cu130, setuptools 84.
- Telemetria do ultralytics desligada (`sync=False`).
- Treino completo: 75 épocas em 2,4 h (early stopping; melhor na 60),
  mAP50 0,926 / mAP50-95 0,576. Tinha estimado 4–6 h; uma época custou
  2 min 20 s, não os 5–7 min que eu chutava antes do piloto.
- `gondola detectar` com os pesos reais em duas fotos de bebidas da validação
  do SKU-110K (corredor de refrigerantes e geladeira de latas):
  - **Detecção boa.** Quase todo produto tem caixa, inclusive as garrafas
    pequenas no fundo do corredor; etiqueta de preço quase nunca.
  - **Falso positivo:** tampinhas de garrafas da fileira de trás, no alto da
    prateleira, viraram caixas pequenas. Vão precisar do limiar da Parte 10.
  - **Fileiras erradas, como previsto:** corredor em perspectiva deu 17
    "fileiras" para cerca de 7 prateleiras, e a geladeira de duas portas com
    prateleiras desalinhadas mistura as portas. O crop não é afetado, mas a
    Parte 11 vai precisar de algo melhor que "meia altura do centro".
- (anote aqui o que a `anotada.jpg` da primeira foto **sua** mostrar)

---

## Modelo de entrada

```
## AAAA-MM-DD — Parte N

- **O que esperava:**
- **O que aconteceu:**
- **Por que:**
- **O que fiz:**
- **Número antes / depois:**
```
