# ADR-021: Detector de Créditos Per-Arquivo por Sinais Visuais (Borda + Movimento)

**Status:** Aceito  
**Data:** 2026-06-19  
**Deciders:** Lucas Cristovam  
**Technical Story:** Detectar onde começam os créditos finais para habilitar "marcar como assistido" + auto-próximo (séries) e overlay estilo Netflix (filmes). Branch `feat/credits-detector`.

---

## Contexto

Logo após o detector de intro plugável (ADR-020), surgiu o pedido de detectar o **início dos créditos finais**. A intuição inicial foi reaproveitar a mesma maquinaria: correlação cross-episódio (a vinheta de abertura é idêntica entre episódios). Uma rodada de spikes contra mídia real derrubou essa premissa e revelou que **créditos são um problema diferente**:

1. **Cross-correlação (vídeo e áudio) não serve para créditos.** Reusando os correlators de produção na janela final:
   - **Vídeo:** 0/22 (MacGyver) e 0/8 (Light Shop) — os créditos rolam sobre imagem específica de cada episódio / em fase de scroll diferente, então não há frame compartilhado.
   - **Áudio (Chromaprint):** deu "8/8" no Light Shop, mas o **ground-truth do usuário expôs que era miragem** — o bloco casado era um trecho de áudio recorrente *fora* dos créditos (errou 40–187s). A música de encerramento varia por episódio (OST rotativa de K-drama). Áudio cross-corr foi descartado.

2. **Não existe um único sinal visual que sirva para todo conteúdo.** Validado em mídia real:
   - **Filme** (créditos de texto branco rolando sobre preto): **densidade de borda** funciona; movimento falha (scroll = movimento alto).
   - **Episódio moderno** (créditos de texto estático sobre fundo escuro): **baixo movimento** funciona; borda falha (show escuro, texto fino some no downscale).
   - **TV antiga** (créditos sobre cena em movimento): nenhum sinal funciona.

3. **A natureza do problema é best-effort.** Como o próprio ecossistema confirma (Plex/Netflix dependem de **marcação humana/crowd** em nuvem, não só de algoritmo), nenhuma heurística leve acerta 100%. Em duas séries muito diferentes, cada uma quebrou de um jeito.

Diferente da intro (cross-correlação por temporada), créditos têm um marcador de **apenas início** (rodam até o fim do arquivo) e são detectáveis **por arquivo isolado** — sem precisar dos episódios irmãos.

## Decisão

**Vamos detectar créditos com um detector per-arquivo único que combina dois sinais visuais complementares e escolhe o candidato pelo onset mais tardio, tratando a detecção como best-effort apoiada por edição manual.**

1. **Per-arquivo, um detector para filme E episódio.** `CreditsDetectorPort.detect(file_path, tuning) -> DetectedCredits | None`. Sem cross-correlação, sem áudio, sem batch por temporada — cada filme e cada episódio é analisado isoladamente. O marcador de domínio `CreditsMarker` carrega só `start_seconds` (+ `source`, `confidence`), pois os créditos vão até o fim.

2. **Dois sinais combinados, seleção por recência.** `CreditsDetector` amostra a janela final (cinza, baixa-res, via ffmpeg `-sseof`) e pontua com:
   - **Borda/texto** — degrau sustentado de alta densidade de borda (créditos claros/rolando = filme);
   - **Baixo movimento** — vale sustentado de baixa diferença entre frames (créditos estáticos/escuros = episódio moderno).
   
   Como a confiança dos dois sinais **não é comparável** (a borda satura em 1.0 em qualquer cena clara de um show escuro), a seleção é pelo **onset mais tardio** entre os candidatos viáveis — créditos são a última região especial antes do fim. Onde nenhum sinal produz região sustentada (TV antiga), retorna `None` → estado `NO_CREDITS_FOUND` (perda honesta, não um chute).

3. **Detecção é per-file no domínio** (`Episode.credits` / `Movie.credits` + `credits_detection_state` por título, não por temporada). O `CreditsDetectionJob` varre filmes + episódios `NOT_STARTED`, aplica o `min_confidence` do operador, e persiste marcador `AUTO_DETECTED` ou `NO_CREDITS_FOUND`. Knobs persistidos em `CreditsDetectionConfig` (ADR-013/014).

4. **Best-effort + manual + heurística de runtime.** A detecção cobre o que dá; o que ela erra (casos-limite) é corrigido por um **editor manual** de marcador (endpoints `PUT/DELETE /admin/media/{id}/credits`, marcador `MANUAL` que o job respeita). A UX de **série** (auto-próximo + marcar assistido) é dirigida primariamente por **%-runtime / tempo restante** — 100% confiável — usando o marcador detectado quando houver, para precisão.

## Consequências

### Positivas

- Um único detector leve (só `numpy` + ffmpeg, já presentes) cobre filme e episódio, sem áudio nem cross-correlação.
- Degrada graciosamente: onde não há sinal (TV antiga), nenhum marcador é gravado — sem falso-positivo.
- A seleção por onset-mais-tardio resolve a incomparabilidade de confiança entre os dois sinais com uma regra simples e robusta.
- O algoritmo de pontuação fica isolado da I/O e testável com frames sintéticos.
- Marcador só-início reflete a realidade (créditos vão até o fim) e simplifica schema e player.

### Negativas

- Detecção é imperfeita por natureza (content-dependent): casos como uma cena quieta antes dos créditos, ou créditos ultracurtos (~9s), erram ou não detectam. Mitigado pelo editor manual.
- A `confidence` ainda não é calibrada entre sinais (um filme correto pode vir com confiança baixa); `min_confidence` default conservador (0.4), a refinar via observabilidade.
- Decodifica a janela final de cada arquivo: custo de CPU em catálogos grandes (~2 min por 5 filmes + 5 episódios na máquina-alvo). Mitigado por ser job em background com `batch_size`.

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Onset errado persistido como AUTO (cena quieta antes dos créditos) | Média | Baixo | `min_confidence` + editor manual + reset por título; player de série usa %-runtime como base. |
| Confiança não-comparável levar a marcador ruim | Média | Baixo | Seleção por recência (não por confiança); calibrar `min_confidence` com a observabilidade (Fase B). |
| Custo de decode em biblioteca grande | Média | Médio | Job em background, `batch_size` baixo, janela configurável. |

## Alternativas Consideradas

### 1. Cross-correlação (reusar o detector de intro)

Correlacionar a janela final entre episódios. **Rejeitada:** provada 0/22 e 0/8 em vídeo; o conteúdo dos créditos varia por episódio, então não há bloco compartilhado para casar.

### 2. Áudio (Chromaprint) na janela final

Casar a trilha de encerramento entre episódios. **Rejeitada:** miragem — casou áudio recorrente fora dos créditos (a OST de encerramento varia por episódio); o ground-truth do usuário mostrou erros de 40–187s.

### 3. Sinal visual único (só borda, ou só movimento, ou texto-no-escuro estilo Plex)

**Rejeitada:** content-dependent — borda acerta filme mas falha em episódio escuro; movimento acerta episódio estático mas falha em filme que rola; brilho/texto-no-escuro morre no downscale. Nenhum cobre os três casos sozinho.

### 4. ML (ResNet/classificador de frame) ou OCR (Tesseract)

Os únicos que poderiam quebrar os casos indistintos. **Rejeitada (por ora):** dependências pesadas (TensorFlow/Tesseract) contra o espírito enxuto do projeto; OCR ainda morreria no downscale do texto fino. Reabrível se a cobertura best-effort + manual se mostrar insuficiente.
