# ADR-019: Transcodificação por Hardware (NVENC/NVDEC) com Seleção de Encoder Configurável

**Status:** Aceito  
**Data:** 2026-06-14  
**Deciders:** Lucas Cristovam  
**Technical Story:** Banding em gradientes suaves no player (WALL·E, fonte HEVC 10-bit 4K) + CPU saturada durante reprodução e geração de thumbnails. PRs homeflix#274 (backend) e homeflix-web#165 (admin).

---

## Contexto

O pipeline de HLS re-encoda para H.264 toda fonte cujo codec de vídeo não é diretamente reproduzível no browser (qualquer coisa fora de `{"h264"}`), e remuxa (`-c:v copy`) quando já é H.264. Fontes modernas de filme — HEVC/H.265, frequentemente 10-bit e 4K — caem no caminho de re-encode.

Esse re-encode rodava em **software** com `libx264 -preset ultrafast -crf 23`. Dois problemas concretos surgiram:

1. **Qualidade.** `ultrafast` desliga CABAC e adaptive quantization, o que colapsa gradientes suaves (céu, névoa) em macroblocos visíveis. O mesmo conteúdo no VLC (que decodifica o HEVC original, sem re-encode) ficava liso.
2. **Custo de CPU.** Encodar 4K HEVC→H.264 por software em tempo real satura a CPU (medido ~92% nos 24 threads de um Ryzen 9 7900X). A geração de **sprites de scrub-preview** agrava o quadro: decodifica o filme 4K HEVC *inteiro* por software, em passes concorrentes.

A máquina-alvo tem uma GPU NVIDIA (RTX 4070 Ti SUPER) com NVENC/NVDEC dedicados, ociosa enquanto a CPU gargalava. Benchmark do pipeline full-GPU (`-hwaccel cuda` → `scale_cuda=format=nv12` → `h264_nvenc`) deu ~1,6× tempo real em 4K com CPU ≈ 0%.

O HomeFlix já tem infraestrutura para tunables operacionais persistidos (ADR-013) com um aggregate por bucket (ADR-014); `StreamingConfig` já existia para `ffmpeg_threads` e `hls_cache_max_size_mb`.

## Decisão

**Vamos delegar à GPU todo trabalho de ffmpeg que seja decode/encode de vídeo, controlado por um único knob persistido `StreamingConfig.hw_accel`.**

- **Novo Value Object** `HardwareAccel` (StrEnum: `auto` | `nvenc` | `off`), campo `hw_accel` em `StreamingConfig`, default `auto`. Persistido como JSON em `app_settings`; retrocompatível (chave ausente → `auto`, sem migration).
  - `auto` — sonda funcionalmente o NVENC uma vez (encode sintético descartável via `lavfi`) e usa se funcionar; senão cai para software. Default seguro: host sem GPU NVIDIA fica em software sozinho.
  - `nvenc` — força NVENC, pulando o probe. Encoder quebrado vira falha de transcode (sem fallback silencioso).
  - `off` — força software, ignorando qualquer GPU (CI, containers sem `--gpus`, A/B).
- **HLS transcode** (`hls_service.py`): caminho full-GPU para fontes que precisam de re-encode — `-hwaccel cuda -hwaccel_output_format cuda` (decode NVDEC) → `scale_cuda=format=nv12` (conversão 10→8 bit em VRAM) → `h264_nvenc -preset p5 -tune hq -rc vbr -cq 19 -spatial_aq 1`. O fallback de software sai do `ultrafast` para `superfast -crf 20 -pix_fmt yuv420p`.
- **Sprites de scrub-preview** (`thumbnail_service.py`): o decode do filme inteiro vai para a NVDEC (`-hwaccel cuda`, decode-only — os filtros `scale`/`pad`/`tile` seguem na CPU sobre frames já baixados, pois `tile` não tem equivalente CUDA e o custo pós-downscale é pequeno). Com retry automático em software numa falha rápida de hwaccel e **sem** retry em timeout.
- **Desacoplamento de módulo** (ADR-008): `media` é infraestrutura consumidora; compara `hw_accel` pelo valor do StrEnum (`"off"`/`"nvenc"`) sem importar o VO de `settings` em runtime — `media` só importa `settings` sob `TYPE_CHECKING`, seguindo o precedente existente.

**Auditoria de delegação à GPU (escopo desta decisão).** Nem todo ffmpeg é candidato — só decode/encode de vídeo. O levantamento de todas as invocações:

| Serviço | Trabalho ffmpeg | Candidato a GPU? | Estado |
|---|---|---|---|
| HLS — transcode de vídeo | decode + encode H.264 | **Sim** | ✅ NVDEC + NVENC |
| Sprite de scrub-preview | decode do filme inteiro | **Sim** | ✅ NVDEC (decode) |
| HLS — áudio primário/alternativo | decode de áudio + encode AAC | Não (áudio) | — |
| Extração de legenda | remux de legenda de texto p/ WebVTT | Não (texto) | — |
| Extração de áudio (intro detection) | janela de áudio → WAV | Não (áudio) | — |
| Fingerprint de intro (fpcalc) | chromaprint | Não (áudio) | — |
| Probe (`ffprobe`) | só metadados | Não | — |

NVENC/NVDEC aceleram apenas vídeo; áudio, legenda de texto e fingerprinting são CPU-bound mas baratos. **Os dois únicos caminhos pesados de vídeo já estão na GPU; nenhum outro serviço se beneficia.**

## Consequências

### Positivas

- CPU praticamente livre no transcode 4K do player e na geração de sprites (medido ~0% vs ~92%).
- Banding resolvido na GPU (`spatial_aq`) e também no fallback de software (saída do `ultrafast`).
- Comportamento controlável por host sem recompilar, via `/admin` → Settings → Streaming (admin control no homeflix-web#165).
- Default `auto` é seguro e portável: degrada para software onde não há GPU.

### Negativas

- Acopla a qualidade/custo do streaming à presença de uma GPU NVIDIA + driver + build de ffmpeg com NVENC. Em outros vendors (Intel QSV, AMD AMF, VAAPI) o `auto` não detecta nada e fica em software.
- O caminho HLS full-GPU **não tem fallback de software por-arquivo**: uma fonte que a NVDEC não decodifica falha aquele transcode (escape hatch: `hw_accel=off`).
- Matriz de teste cresce: caminhos GPU não rodam em CI sem GPU (cobertos por testes que mockam o probe/detecção).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Fonte não-decodável pela NVDEC quebra o transcode HLS | Baixa (biblioteca é codec mainstream) | Médio | `hw_accel=off`; fallback per-arquivo é follow-up |
| Probe NVENC passa mas encode real falha sob contenção de sessões | Baixa | Médio | `nvenc` força sem probe; `off` como escape; falha vira erro de geração, não corrupção |
| Limites de sessões NVENC concorrentes (cards consumer) | Baixa (uso pessoal, poucas sessões) | Baixo | Eviction de ffmpeg idle já existente (ADR de runtime settings) |

## Alternativas Consideradas

### 1. Continuar em software, só ajustando o preset

Trocar `ultrafast` por `superfast`/`veryfast` e baixar o CRF.

**Rejeitado porque:** resolve o banding mas não o custo de CPU — encode 4K por software em tempo real continua saturando a máquina, com risco de rebuffer. (Mantido apenas como *fallback* quando não há GPU.)

### 2. Downscale para 1080p no caminho de software

Escalar 4K→1080p para caber um preset melhor no mesmo orçamento de CPU.

**Rejeitado porque:** degrada a resolução entregue e ainda gasta CPU; a GPU resolve sem abrir mão do 4K. Pode voltar como opção futura (`max_transcode_height`) ortogonal a esta decisão.

### 3. Hardcode do NVENC, sem knob nem fallback

Trocar o bloco de software direto por NVENC fixo.

**Rejeitado porque:** quebra em qualquer ambiente sem GPU NVIDIA (CI, Docker, outra máquina) e foge da convenção de tunables persistidos (ADR-013/014).

### 4. Pré-converter a biblioteca para H.264 offline

Transcodar tudo uma vez para H.264 8-bit, deixando o playback como puro remux.

**Rejeitado (por ora) porque:** custa disco (cópia duplicada) e descarta a fonte de maior qualidade; é um trade-off de produto diferente. Não conflita com esta decisão e pode coexistir no futuro.

## Referências

- PR backend: lucaschf/homeflix#274
- PR admin (knob no frontend): lucaschf/homeflix-web#165
- ADR-013 (Runtime Settings persistidos), ADR-014 (Aggregate por bucket), ADR-008 (direção de dependência entre módulos)
- `docs/roadmap.md` — Phase 3.2 (Hardware transcoding VAAPI/NVENC)

---

## Notas de Implementação

Seleção de encoder (decode-only para sprite, full-GPU para HLS):

```python
# HLS — full-GPU quando hw_accel resolve para NVENC
hwaccel_input_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
vf_args = ["-vf", "scale_cuda=format=nv12"]               # 10->8 bit em VRAM
video_args = ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
              "-rc", "vbr", "-cq", "19", "-b:v", "0", "-spatial_aq", "1"]

# Sprite — decode na NVDEC, filtros scale/pad/tile na CPU
hwaccel_args = ["-hwaccel", "cuda"] if use_hwaccel else []
```

Extensão futura natural: trocar `HardwareAccel` por uma seleção mais rica (`qsv`, `amf`, `vaapi`) e/ou adicionar `max_transcode_height`, sem mudar a fronteira da decisão (encoder configurável + fallback de software).
