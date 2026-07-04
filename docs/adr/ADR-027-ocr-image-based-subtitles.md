# ADR-027: OCR de Legendas Baseadas em Imagem (PGS/VOBSUB) para Faixas de Texto Selecionáveis

**Status:** Aceito  
**Data:** 2026-07-04  
**Deciders:** Lucas Cristovam  
**Technical Story:** Legendas baseadas em imagem (PGS/SUP/VOBSUB) não aparecem como opção no player — só faixas de texto. Ex. real: filme com 1 SRT + 27 PGS mostra só a SRT; Nausicaä (Ghibli) tem **só** PGS e fica sem legenda alguma. Branch `feat/subtitle-ocr`.

---

## Contexto

O HomeFlix serve legendas ao player como **WebVTT (texto)**. Tanto o endpoint `/tracks`
(`serialize_tracks`) quanto o pipeline HLS (`_build_master_playlist`,
`_start_generation`) filtram por `is_text_based`, descartando faixas
`is_image_based` de propósito — um bitmap não vira WebVTT sem OCR. Não é regressão: é
limitação de longa data (ver backlog `project_image_subtitle_support_backlog`).

O impacto real é desigual entre acervos. Muitos remuxes de Blu-ray carregam legendas
**exclusivamente** em PGS (o formato nativo de BD). Nesses títulos o usuário fica sem
nenhuma legenda selecionável — inclusive em conteúdo onde a legenda é essencial
(animação japonesa, filme estrangeiro). É o mesmo problema que Plex e Jellyfin
resolvem com OCR em background.

Um protótipo (2026-07-04) validou a viabilidade contra mídia real (Nausicaä, faixa PGS
inglesa, 8.8 GB): um parser PGS próprio (decodifica RLE + paleta YCbCr→RGB, pareia
display-sets show/clear em cues com timing) + **tesseract 5.3.4** produziu **1079 cues,
0% vazias**, com um único erro sistemático — tesseract lê o "I" isolado como "|",
corrigível por uma regra de uma linha (`|`→`I`), que zera o resíduo. Custo: ~96 s
single-thread por faixa (~11 cues/s), decode pixel-perfeito. Sinal claro de **GO**.

Restrições que moldam a decisão:

1. **Faixas de legenda não são persistidas no banco.** São descobertas por probe
   (ffprobe) na hora. Não há coluna SQL barata para "mídia com PGS sem OCR" — diferente
   do backfill de thumbnails, que consulta `scrub_preview_path IS NULL`.
2. **OCR é lento** (dezenas de segundos a minutos por faixa) — muito além dos 120 s que
   a thread de extração HLS síncrona espera. Precisa ser trabalho de background.
3. **O runtime de produção é Windows** (o backend chama `ffmpeg.exe`, paths `G:\`). Uma
   dependência de OCR precisa existir no host Windows, não só no ambiente de dev (WSL).
4. **ADR-026** já tornou o servidor autoritativo sobre qual faixa é default e o front
   confia no `/tracks`. Qualquer faixa nova precisa apenas aparecer no `/tracks` como
   texto para ser selecionável — sem mudança no front.

## Decisão

**Vamos habilitar legendas de imagem via OCR para WebVTT, materializando cada resultado
como um sidecar de texto em disco que o probe expõe como uma faixa externa de texto —
gerado por um job de background best-effort, sem migration.**

1. **Representação = faixa externa de texto (VTT).** Para cada faixa `is_image_based`
   cujo sidecar OCR já existe em disco, o probe passa a expor uma faixa **irmã**
   `SubtitleTrack(is_external=True, format="vtt", file_path=<ocr.vtt>)` com um `index`
   novo e único (após o máximo atual). A faixa PGS original permanece (segue filtrada).
   Sem mutação da faixa de imagem, sem colisão de `sub_N`. Essa representação satisfaz
   o validador do VO e **todos** os filtros `is_text_based` existentes — flui pelo ramo
   externo do HLS (`ffmpeg -i ocr.vtt -c:s webvtt`) e pela seleção de default do
   ADR-026 **sem alterar** o código de extração/serving.

2. **Sidecar determinístico em disco, sem migration.** A saída OCR vive em
   `<pasta-do-arquivo>/<subdir>/<stem>/ocr_s<streamIdx>_<lang>.vtt` (espelha
   `scrub_preview_output_dir` do thumbnail). "Feito" = o arquivo existe. Um marcador
   por-arquivo (`.ocr_done`) permite o job pular arquivos já processados **sem coluna
   no banco** — contornando a restrição de que faixas não são persistidas.

3. **Exposição = função pura aplicada em toda leitura de probe.**
   `attach_ocr_subtitles(probe, source)` roda tanto em `HlsService.probe_tracks` (alimenta
   `/tracks`) quanto em `_start_generation` (alimenta o HLS), recomputando `file_path` a
   partir do caminho determinístico a cada vez. Isso contorna o gap conhecido em que
   `_save/_deserialize_probe` não persiste `file_path` de faixas externas.

4. **Geração = job de background agendado** (modelo Plex/Jellyfin — legenda pronta antes
   de reproduzir), espelhando `ThumbnailBackfillJob`: varre a mídia em lotes, pula via
   marcador `.ocr_done`, faz probe das faixas de imagem, OCR das faltantes, grava sidecar
   + marcador. Registrado no scheduler com `job_id="homeflix:subtitle-ocr"` — a gravação
   de `JobRun` e o dashboard `/admin/jobs` vêm de graça. `enabled`/lote/intervalo/langs
   ficam em `SubtitleOcrConfig` persistido (ADR-013/014). Trigger eager on-play e endpoint
   manual ficam adiados (best-effort primeiro).

5. **Tesseract como dependência de OCR do host.** O serviço de OCR faz shell-out para
   `tesseract` (como já faz para `ffmpeg`). O binário e os idiomas habilitados ficam em
   config. **Produção exige tesseract no host Windows** (`choco install tesseract` + os
   `tessdata` dos idiomas). Documentado como pré-requisito de deploy.

6. **Mapa de idioma + best-effort.** ISO 639-1 (`en`/`pt`/`fr`) → tesseract 639-2/T
   (`eng`/`por`/`fra`). Idioma desconhecido/sem `tessdata` → faixa pulada (logado).
   Qualidade de OCR varia por fonte; assim como o detector de créditos (ADR-021), é
   **best-effort** — sem ground-truth garantido, apoiado por refazível (deletar o sidecar
   re-elege a faixa).

## Consequências

### Positivas

- Legendas PGS/VOBSUB tornam-se **selecionáveis como texto**, incluindo títulos onde é
  a única legenda existente (Blu-ray remux, animação).
- Integra-se **sem alterar** o serving HLS, o `/tracks` ou a seleção de default do
  ADR-026 — a faixa OCR é apenas mais uma faixa de texto.
- **Zero migration** e zero mudança no front (backend-only). Idempotente e refazível
  (o sidecar é derivado; apagar re-processa).
- Observável de graça (`JobRun` + `/admin/jobs`) por reusar a maquinaria do scheduler.

### Negativas

- Nova dependência externa de runtime (**tesseract**) no host Windows — mais uma peça
  de deploy além do ffmpeg.
- OCR é caro (dezenas de segundos por faixa); o primeiro sweep de um acervo grande com
  muito PGS consome CPU por bastante tempo (mitigado por lote + best-effort).
- Qualidade não é garantida (fontes difíceis, estilos, idiomas sem `tessdata` bom).
- Poluição leve do diretório de mídia com sidecars `.homeflix/subtitles/...` (mesmo
  padrão já aceito para thumbnails).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Faixa OCR quebra o player (índice/rendition inconsistente) | Baixa | Alto | Índice novo único; smoke test manual obrigatório antes de push (regra player-risk) |
| tesseract ausente no host de produção | Média | Médio | Config `enabled=false` por default até o operador instalar; job degrada e loga |
| OCR ruim vira legenda pior que nada | Média | Baixo | Best-effort + refazível (apagar sidecar); pós-fix `|`→`I`; faixa original PGS permanece |
| Sweep satura CPU num acervo grande | Média | Médio | Lote (`batch_size`) + intervalo configuráveis; sequencial |

## Alternativas Consideradas

### 1. Burn-in (hardsub)

Re-encodar o vídeo com a legenda de imagem sobreposta.

**Rejeitado porque:** caro (re-encode por seleção), perde o "desligar legenda" e a
troca de idioma, e é irreversível por faixa. OCR entrega texto real, selecionável e
estilizável.

### 2. Persistir faixas de legenda no banco + coluna de estado OCR

Gravar as faixas no scan e ter uma coluna `ocr_state` para o job consultar (como
`intro_detection_state`).

**Rejeitado porque:** exige migration e mudança ampla no scanner (que hoje não persiste
faixas), para eliminar um re-probe que o marcador `.ocr_done` em disco já resolve a
custo baixo. Reavaliar se surgir necessidade de query/relatório sobre faixas.

### 3. OCR eager on-play apenas (sem sweep)

OCR disparado só quando alguém abre um título com PGS.

**Rejeitado como MVP porque:** o primeiro play espera ~15–90 s sem legenda (UX ruim). O
sweep agendado deixa a legenda pronta antes. O trigger eager fica como fase opcional
posterior, complementar ao sweep.

### 4. Won't-fix

**Rejeitado porque:** o protótipo mostrou qualidade e custo aceitáveis, e o impacto em
acervos só-PGS é alto (legenda essencial ausente).

## Referências

- **Guia operacional:** [`docs/standards/subtitle-ocr-guide.md`](../standards/subtitle-ocr-guide.md) (instalação do tesseract + modelos, configuração, trigger manual, observabilidade)
- Backlog: memória `project_image_subtitle_support_backlog` (descoberta + protótipo validado)
- ADR-013/014 — Runtime Settings persistidos por bucket (`SubtitleOcrConfig`)
- ADR-021 — Detector de Créditos (precedente best-effort per-arquivo + job + config)
- ADR-026 — Seleção de Faixa Default Autoritativa no Servidor (a faixa OCR entra na seleção)
- `ThumbnailBackfillJob` — blueprint do job de background (path determinístico, lote, JobRun)

---

## Notas de Implementação

Representação da faixa OCR (satisfaz o validador e todos os filtros de texto):

```python
SubtitleTrack(
    index=next_index,          # único, após o máx atual (evita colisão de sub_N)
    language=pgs_track.language,
    format="vtt",
    is_external=True,
    file_path=FilePath(str(ocr_vtt_path)),
)
```

Caminho determinístico do sidecar (espelha `scrub_preview_output_dir`):

```python
def ocr_subtitle_output_dir(source: Path, subdir: str) -> Path:
    # <source-dir>/<subdir>/<source-stem>/
    return source.parent / subdir / source.stem
```

Rollout faseado (1 PR por fase; commits locais):

1. **ADR-027** (este documento).
2. **Pipeline OCR** — `SubtitleOcrPort` + `TesseractPgsOcrService` + `SubtitleOcrConfig`
   (sem wiring, sem impacto no player).
3. **Exposição** — `attach_ocr_subtitles` em `probe_tracks` + `_start_generation`
   (⚠️ risco player → smoke test antes de push).
4. **Job de background** — `SubtitleOcrBackfillJob` + DI + registro no scheduler.
5. **Opcional/adiado** — trigger eager on-play, endpoint admin "OCR agora", rótulo
   "(OCR)" no front.

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-07-04 | Lucas Cristovam | Criação inicial (decisão + rollout faseado) |
