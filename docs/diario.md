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

## Modelo de entrada

```
## AAAA-MM-DD — Parte N

- **O que esperava:**
- **O que aconteceu:**
- **Por que:**
- **O que fiz:**
- **Número antes / depois:**
```
