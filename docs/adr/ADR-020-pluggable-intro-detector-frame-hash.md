# ADR-020: Detector de Intro Plugável + Algoritmo por Frame-Hash de Vídeo

**Status:** Aceito  
**Data:** 2026-06-15  
**Deciders:** Lucas Cristovam  
**Technical Story:** Detecção automática de abertura ("Skip Intro") errava/perdia episódios em várias séries. Um teste manual com a lib `similar_vid` (perceptual-hash de frames de vídeo) deu resultado nitidamente superior ao detector de áudio existente. Branch `feat/frame-hash-intro-detector`.

---

## Contexto

A detecção automática de abertura era **exclusivamente por áudio**: `ChromaprintIntroDetector` extrai uma janela inicial de áudio via ffmpeg, gera fingerprints com `fpcalc` (Chromaprint) e cruza-os entre episódios da temporada. Funciona bem quando o tema de abertura é o mesmo arquivo de áudio em todos os episódios, mas falha quando o áudio da vinheta varia (mixagem por episódio, narração sobreposta, dublagens).

Dois problemas concretos:

1. **Qualidade.** Um teste manual reimplementando a técnica da lib `similar_vid` — *perceptual-hash de frames de vídeo* (dHash) — detectou aberturas que o caminho de áudio não pegava, com bordas precisas. Em MacGyver S01 (22 eps) o frame-hash fechou 22/22 com a janela correta.

2. **Fronteira vazada.** O `IntroDetectorPort` estava abstraído no nível errado: recebia `Sequence[EpisodeFingerprint]` — hashes Chromaprint de áudio crus — e a extração de áudio + `fpcalc` vivia no **job**, não atrás do port. Um detector baseado em vídeo não consome áudio-hashes nem recebia o caminho do arquivo. Ou seja, a troca de algoritmo prometida pelo padrão port/adapter **não era possível** sem refatorar a fronteira.

A lib `similar_vid` em si é inviável como dependência: está **sem licença** no GitHub (all-rights-reserved por padrão) e depende da `decord`, abandonada desde 2022. O HomeFlix já tem infraestrutura de tunables persistidos (ADR-013) com um aggregate por bucket (ADR-014).

## Decisão

**Vamos tornar o detector de intro plugável atrás de um port elevado e adicionar um algoritmo por frame-hash de vídeo, reimplementado com libs permissivas, selecionável por configuração em runtime.**

1. **Elevar o `IntroDetectorPort`** para o nível "arquivos de episódio → markers": `detect(episodes: Sequence[EpisodeMediaRef], tuning) -> IntroDetectionResult`. `EpisodeMediaRef` carrega `(episode_id, file_path)`; `IntroDetectionResult` carrega `markers` + `analyzed_count` (preserva a distinção `INSUFFICIENT_EPISODES` vs `COMPLETED` quando a mídia é ilegível). Cada adapter passa a ser dono do seu pipeline completo (extração + hashing + correlação); o job não conhece mais áudio/fpcalc. `IntroDetectorTuning` vira base neutra (`min_intro_seconds`, `max_intro_seconds`, `analysis_window_seconds`), com subtipos por algoritmo.

2. **Reimplementar a técnica de frame-hash**, sem `similar_vid`/`decord`: `FrameHasher` amostra frames pela janela inicial via ffmpeg (pipe raw rgb24, sem PNGs em disco) e calcula um **dHash nativo** (Pillow resize LANCZOS + diff horizontal — as operações exatas do `imagehash.dhash`, validado **bit-idêntico** em teste de paridade), empacotado em `uint64`. `FrameHashCorrelator` casa por **votação de diagonal (offset histogram)** sobre todos os offsets da janela, com popcount vetorizado (SWAR) em numpy. Única dependência nova: **`numpy`** (Pillow já existia).

3. **Selecionar o algoritmo por configuração** (ADR-013/ADR-014): `IntroDetectionConfig.algorithm: IntroDetectionAlgorithm` (`chromaprint` | `frame_hash`, default **`frame_hash`**), com knobs por algoritmo nos sub-buckets `chromaprint` e `frame_hash`. O `IntroDetectionJob` recebe um registry `Mapping[IntroDetectionAlgorithm, IntroDetectorPort]` e escolhe o detector por tick, montando a tuning do bucket correspondente — admin troca de detector sem restart.

## Consequências

### Positivas

- Troca de algoritmo de detecção sem deploy; A/B e rollback por uma flag de config.
- O port finalmente cumpre o contrato do padrão: novos detectores entram como adapters sem tocar o job.
- Frame-hash recupera aberturas que o áudio não pega; áudio segue disponível para os casos inversos (complementares).
- Sem dependências problemáticas (`similar_vid` sem licença, `decord` abandonada); só `numpy`, permissiva e ubíqua.
- O algoritmo puro (`*Correlator`) fica isolado da I/O e testável com fixtures sintéticas.

### Negativas

- O frame-hash decodifica vídeo: mais pesado que fingerprint de áudio (~7 min/temporada de 22 eps a 600s/2fps na máquina-alvo). Mitigado por ser job em background e por bit-packing/numpy no matching.
- `IntroDetectionConfig` ganhou complexidade (sub-buckets + enum).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Config persistido antigo perde valores de campos renomeados/aninhados (`audio_window_seconds`, `max_hash_hamming`, `tolerance_hashes`) | Alta | Baixo | `CompoundValueObject` usa `extra=ignore` → desserializa sem crash, campos movidos revertem ao default. Detecção é opt-in (`enabled=False`); reconferir Settings após deploy. |
| dHash nativo divergir da calibração validada | Baixa | Médio | Teste de paridade confirmou 0/60 mismatches vs `imagehash.dhash`. |
| Custo de CPU do decode em catálogos grandes | Média | Médio | `batch_size` baixo, janela configurável, job em background; alternar para `chromaprint` se necessário. |

## Alternativas Consideradas

### 1. Depender da lib `similar_vid`

Usar a lib diretamente (ou vendorizá-la).

**Rejeitado porque:** sem licença no repositório (uso/redistribuição legalmente proibidos por padrão) e depende da `decord`, sem manutenção desde 2022. A técnica é simples o bastante para reimplementar com libs permissivas.

### 2. Substituir o detector de áudio de vez

Remover o Chromaprint e ficar só com frame-hash.

**Rejeitado porque:** os dados mostraram que os dois são **complementares** — há episódios em que o vídeo da vinheta difere (e o áudio acerta) e vice-versa. Manter ambos selecionáveis maximiza cobertura e dá rollback.

### 3. Manter o port como estava (fingerprints de áudio)

**Rejeitado porque:** vaza a implementação Chromaprint no contrato e impede plugar qualquer detector não-áudio — exatamente o objetivo.

## Referências

- ADR-013 (Runtime Settings em banco), ADR-014 (Settings — Aggregate por Bucket)
- `src/modules/media/application/ports/intro_detector_port.py`
- `src/modules/media/infrastructure/video/` (FrameHasher, FrameHashCorrelator, FrameHashIntroDetector)
- `src/modules/media/infrastructure/audio/chromaprint_correlator.py`
- lib de referência (não adotada): github.com/jahwi/similar-vid

---

## Notas de Implementação

- **Votação de diagonal:** para o par (A,B), monta a matriz de Hamming entre todo frame de A e todo frame de B; cada diagonal `d = idxB - idxA` é um alinhamento candidato; a diagonal com o maior run tolerante de casamentos (≤ `hash_distance_threshold`) é a abertura, projetada para os segundos de A e de B. Cobrir todos os offsets (em vez de um shift limitado como no áudio) é o que permite casar aberturas empurradas por cold-opens de duração variável.
- **dHash nativo:** `Image.fromarray(frame).convert("L").resize((9,8), LANCZOS)`, diff `px[:,1:] > px[:,:-1]`, flatten row-major, `np.packbits(...).view(np.uint64)`.
- **Defaults calibrados:** dHash 8×8 (64 bits), frame 64px, fps=2, `hash_distance_threshold=8` (estrito — afrouxar gera falso-positivo), `match_tolerance_frames=2`, `analysis_window_seconds=600`, `min_intro_seconds=5`, `max_intro_seconds=120`, `min_confidence=0.7`.
