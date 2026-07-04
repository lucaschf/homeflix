# Guia — OCR de Legendas Baseadas em Imagem (PGS/SUP)

Este guia cobre a instalação, configuração e operação do **OCR de
legendas** (ADR-027): a conversão de legendas baseadas em imagem
(PGS/SUP, comuns em remuxes de Blu-ray) em texto WebVTT selecionável no
player.

> **Fonte da verdade da decisão:** [`docs/adr/ADR-027-ocr-image-based-subtitles.md`](../adr/ADR-027-ocr-image-based-subtitles.md).

---

## 1. Visão Geral

Legendas de imagem não são selecionáveis no player porque o HLS serve
legenda como texto (WebVTT). Este recurso faz **OCR** dessas faixas para
sidecars de texto em disco, que o probe passa a expor como faixas de
texto normais.

Fluxo: **job de background** (ou **trigger manual**) → OCR → sidecar
`.vtt` no disco → o probe expõe como faixa externa de texto → aparece no
`/tracks` e vira uma rendition `sub_N` no HLS → selecionável no player.

É **best-effort**: a qualidade varia por fonte, e depende de o idioma ter
modelo de OCR instalado no host.

---

## 2. Pré-requisitos

O backend roda **Windows-native** (chama `ffmpeg`/`ffprobe`/`tesseract`
via `PATH`). O host precisa de:

| Dependência | Uso |
|-------------|-----|
| **ffmpeg + ffprobe** | Demux da faixa PGS + probe de faixas |
| **tesseract** | Motor de OCR |
| **modelos de idioma (`*.traineddata`)** | Um por idioma que se queira extrair |

> Sem tesseract, o job **pula todo tick** e o trigger manual grava um run
> `FAILED` ("No tesseract language models installed") — nada é marcado
> como processado silenciosamente.

---

## 3. Instalação (host Windows)

### 3.1. tesseract

```powershell
choco install tesseract
```

Confirme que está no `PATH`:

```powershell
tesseract --version
```

Se não estiver no `PATH`, informe o caminho completo em
`tesseract_binary` (ver §4).

### 3.2. Modelos de idioma

O pacote choco instala normalmente **só o inglês** (`eng`). Cada idioma
adicional exige o `*.traineddata` correspondente na pasta `tessdata` do
tesseract (ex.: `C:\Program Files\Tesseract-OCR\tessdata\`).

Baixe o modelo do idioma desejado do repositório oficial e copie para
`tessdata`. Exemplo para **português**:

- <https://github.com/tesseract-ocr/tessdata_fast/blob/main/por.traineddata>
  → salvar como `...\tessdata\por.traineddata`

Confirme os modelos instalados:

```powershell
tesseract --list-langs
```

> **`SEM MODELO` na tela de execuções = o `*.traineddata` daquele idioma
> não está no host.** Instale o modelo e reprocesse (ver §7).

Mapeamento ISO 639-1 → modelo tesseract usado internamente:
`en→eng`, `pt→por`, `fr→fra`, `es→spa`, `de→deu`, `it→ita`, `nl→nld`,
`pl→pol`, `ru→rus`, `sv→swe`, `no→nor`, `da→dan`, `fi→fin`, `tr→tur`,
`cs→ces`, `ja→jpn`, `ko→kor`, `zh→chi_sim`, `ar→ara`, `hi→hin`.
Idioma fora dessa lista → `SEM MODELO`.

### 3.3. Migration do banco

O recurso persiste um log de execuções na tabela `subtitle_ocr_runs`.
Rode a migration **antes** de subir o servidor:

```bash
make migrate      # revision 5d0b7e1c9a3f
```

> Se subir o dev server antes do migrate, `Base.metadata.create_all` cria
> a tabela e o migrate depois falha com "table already exists". Nesse caso:
> `poetry run alembic stamp 5d0b7e1c9a3f` (a tabela já está correta).

---

## 4. Configuração (bucket `subtitle_ocr`)

Os knobs ficam no bucket de runtime settings `subtitle_ocr` (ADR-013/014),
editável em **Admin → OCR de legendas** (card de settings) ou via API.

| Campo | Default | Descrição |
|-------|---------|-----------|
| `enabled` | `false` | Liga o **job periódico**. O trigger manual funciona mesmo com isto desligado. |
| `batch_size` | `2` | Arquivos processados por tick do job. OCR é caro — mantenha baixo. |
| `interval_minutes` | `60` | Cadência do job. |
| `subdir` | `.homeflix/subtitles` | Subpasta (relativa à pasta do arquivo) dos sidecars + marcador. |
| `languages` | `[]` (todos) | Códigos ISO 639-1 a processar (ex.: `["pt","en"]`). **Vazio = todos os mapeáveis.** |
| `tesseract_binary` | `tesseract` | Nome ou caminho completo do executável. |
| `per_cue_timeout_seconds` | `30` | Timeout de uma chamada tesseract (uma legenda). |

> ⚠️ **Defina `languages`.** Alguns remuxes carregam 20+ faixas PGS (ex.:
> Rush Hour tem 27). Com `languages` vazio, o job **e** o trigger manual
> fazem OCR de todas — horas de trabalho. Restrinja ao(s) seu(s) idioma(s).

### 4.1. Via API

```http
PATCH /api/v1/admin/settings/subtitle-ocr
Content-Type: application/json

{
  "enabled": true,
  "batch_size": 2,
  "interval_minutes": 60,
  "subdir": ".homeflix/subtitles",
  "languages": ["pt", "en"],
  "tesseract_binary": "tesseract",
  "per_cue_timeout_seconds": 30
}
```

> Update é **full-replace**: envie o objeto inteiro. Alterar `languages`
> vale no próximo tick/trigger sem restart (o snapshot invalida ao salvar).
> Ligar/desligar o **job** exige restart (registro no boot).

---

## 5. Como Funciona

### 5.1. Job de background (`homeflix:subtitle-ocr`)

Registrado no scheduler quando `enabled=true` (no boot). Varre
filmes/episódios, pula arquivos com marcador `.ocr_done` em disco, faz
probe das faixas de imagem, OCR das faltantes (respeitando `languages`),
grava sidecar + marcador, e registra um `SubtitleOcrRun`. Aparece no
dashboard **Admin → Jobs** e permite "Run now".

### 5.2. Trigger manual ("OCR neste título agora")

Botão **admin** no detalhe do **filme** (ícone de legendas) dispara OCR
sob demanda para aquele título:

```http
POST /api/v1/admin/subtitle-ocr/movies/{movie_id}/run      # 202 Accepted
POST /api/v1/admin/subtitle-ocr/episodes/{episode_id}/run  # 202 Accepted
```

- É **fire-and-forget** (202): o OCR roda em background; o resultado
  aparece na página de execuções quando termina (minutos).
- Ignora o marcador `.ocr_done` (sempre reprocessa) mas **respeita
  `languages`**.
- Não exige o job periódico ligado.
- `tesseract` ausente → grava um run `FAILED`.

> O botão por-episódio (SeriesDetail) ainda não existe na UI; o endpoint
> `/episodes/{id}/run` já funciona.

### 5.3. Exposição no player

Uma vez que o sidecar existe em disco, o probe o expõe como faixa externa
de texto (sem alterar o serving HLS/`/tracks`). **Só faz efeito com o
bucket `subtitle_ocr` `enabled=true`.** Se o título já foi transmitido, o
`master.m3u8` está cacheado sem a rendition — limpe o cache HLS do título
(**Admin → HLS Cache**, ou `DELETE /api/v1/stream/movie/{id}/hls/cache`)
para regenerar.

### 5.4. Observabilidade (**Admin → OCR de legendas**)

`GET /api/v1/admin/subtitle-ocr/runs` — histórico por arquivo: título,
desfecho, nº de faixas de imagem e, por faixa, idioma + desfecho +
nº de legendas (cues) extraídas. Desfechos por-faixa: `extracted`,
`no_text`, `unsupported_format`, `no_language_model` (SEM MODELO),
`skipped_language`, `failed`.

---

## 6. Formatos Suportados

- ✅ **PGS / SUP** (`hdmv_pgs_subtitle`) — decodificados e OCR'd.
- ❌ **VOBSUB / IDX** — layout de bitmap diferente; retornam
  `unsupported_format` (não implementado).
- Legendas de **texto** (SRT/ASS/VTT) não passam por OCR — já são
  selecionáveis diretamente.

---

## 7. Reprocessar um Título

O marcador `.ocr_done` faz o job pular arquivos já processados. Para
reprocessar (ex.: depois de instalar um novo modelo de idioma):

- **Trigger manual:** já ignora o marcador — basta disparar de novo.
- **Job periódico:** apague o marcador
  `<pasta-do-arquivo>/.homeflix/subtitles/<stem>/.ocr_done`.
- Para descartar o texto OCR'd, apague também os `ocr_s*.vtt` da mesma
  pasta.

---

## 8. Diagnóstico Rápido

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Faixa diz `SEM MODELO` | `*.traineddata` do idioma ausente | Instalar o modelo em `tessdata` (§3.2) + reprocessar |
| Nenhum run aparece / demora demais | `languages` vazio + título com muitas faixas PGS | Definir `languages` (§4) + reiniciar (mata a task) |
| Run `FAILED` "No tesseract..." | tesseract fora do `PATH`/ausente | Instalar tesseract ou ajustar `tesseract_binary` |
| Legenda OCR não aparece no player | cache HLS antigo do título | Limpar cache HLS do título (§5.3) |
| Migrate falha "table already exists" | dev server rodou antes do migrate | `alembic stamp 5d0b7e1c9a3f` (§3.3) |
