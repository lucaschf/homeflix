# ADR-026: Seleção de Faixa Default Autoritativa no Servidor a partir de Preferência por Usuário

**Status:** Aceito
**Data:** 2026-06-30
**Deciders:** Lucas
**Technical Story:** Follow-up F-2 (`docs/audits/07-phase6-backlog.md`). A investigação cross-repo (homeflix + homeflix-web) revelou drift entre back e front na escolha de faixa default de áudio/legenda. Emenda o ADR-005.

---

## Contexto

O ADR-005 modelou a `Library` como entidade de configuração e previu **preferências de reprodução por-library** (`LibrarySettings.preferred_audio_language` / `preferred_subtitle_language` / `subtitle_mode`) dirigindo um `TrackSelector` de domínio que escolhe a faixa default.

Ao tentar "ligar" essa preferência no boundary `/tracks` (F-2), a investigação ponta-a-ponta mostrou que a realidade divergiu do ADR-005 em três pontos, criando **duas fontes de verdade** e **dois motores de seleção**:

1. **Preferência real é por-usuário, não por-library.** O frontend lê/grava `audio_lang` / `subtitle_lang` / `subtitle_mode` em `/preferences` (o **Preferences BC**, por-perfil, default `pt-BR`), com cache em localStorage. É o mecanismo que de fato funciona.
2. **A seleção acontece no cliente.** `Player.tsx` resolve a faixa via `findTrackByLang(hls.audioTracks, playbackPrefs.audioLang)`. O `TrackSelector` de domínio (ADR-005 / Card B) existe mas só `select_audio`, e o boundary `/tracks` sempre passava `preferred_language=None` — inerte. O campo `is_default` de `/tracks` **não é consumido** pelo front (só aparece em `api/types.ts`).
3. **A preferência por-library está órfã.** `LibrarySettings.preferred_audio_language` (default `en`) não influencia playback algum — só alimentaria o `is_default` que o front ignora — e o default `en` ainda conflita com o `pt-BR` do Preferences BC.

Além disso, o manifesto HLS marca `DEFAULT=YES,AUTOSELECT=YES` **sempre na primeira faixa de áudio** (`_primary_audio_index`, index 0), independente de container default e de qualquer preferência. O cliente compensa isso em runtime. Ou seja, mesmo o `/tracks.is_default` e o manifesto **não concordam** entre si.

Resultado: a regra de seleção está duplicada (`findTrackByLang` no cliente **vs** `TrackSelector` no domínio), alimentada por fontes diferentes (Preferences BC por-usuário **vs** LibrarySettings por-library), com defaults divergentes (`pt-BR` vs `en`), e o manifesto HLS ignora ambos. Isso é o oposto do padrão da indústria (Plex/Jellyfin/Netflix): **uma** preferência por-perfil, persistida no servidor, com **uma** autoridade resolvendo o stream default.

## Decisão

Nós tornaremos o **servidor a autoridade única** da escolha de faixa default, a partir de uma **fonte única de preferência por-usuário** (o Preferences BC).

1. **Fonte única.** A preferência de reprodução (`audio_lang`, `subtitle_lang`, `subtitle_mode`) vive **apenas** no Preferences BC, por-perfil. As contrapartes por-library em `LibrarySettings` (`preferred_audio_language`, `preferred_subtitle_language`, `subtitle_mode`) são **removidas** — eram config órfã com default conflitante. (Os demais campos de `LibrarySettings` — `generate_thumbnails`, `detect_intros`, `auto_refresh_metadata` — são config de scan/processamento legítima por-library e permanecem.)

2. **Autoridade no servidor.** O `TrackSelector` de domínio (ADR-005) continua dono da regra, agora alimentado pela preferência **por-usuário** lida via Read Port + ACL cross-BC `media → preferences` (ADR-009). A seleção é aplicada nos **dois** pontos de leitura que o cliente consome, que passam a **concordar**:
   - `/tracks` → `is_default` reflete a faixa resolvida;
   - o **manifesto HLS** → `DEFAULT=YES,AUTOSELECT=YES` na mesma faixa resolvida (não mais sempre index 0).

3. **Precedência canônica.** A faixa que toca é resolvida nesta ordem:
   `escolha salva no título (watch_progress) → preferência do perfil (Preferences BC) → default declarado no container → primeira faixa`.
   O servidor é dono das três camadas inferiores (preferência → container → primeira). A escolha salva por-título é estado de retomada aplicado pelo cliente por cima do default do servidor (não é regra; fica no cliente para não acoplar `media → watch_progress` na borda de streaming).

4. **`select_subtitle` por modo (o F-3) é implementado no domínio**, dentro desta autoridade, consumindo o `subtitle_mode` por-usuário — não mais a lógica client-side de `pickPreferredSubtitleId`.

5. **Cliente fica mínimo (mas não-zero).** O front deixa de **decidir** (`findTrackByLang` / `pickPreferredSubtitleId` saem) e passa a **aplicar** o default que o servidor entregou + permitir override ao vivo + lembrar a escolha por-título. É o split thin-client correto (servidor decide o quê; cliente aplica e permite trocar).

Esta decisão **emenda o ADR-005**: a localização da preferência de reprodução muda de por-library para por-usuário (Preferences BC), e a autoridade de seleção passa a ser explicitamente o servidor (manifesto + `/tracks`), não o cliente.

## Consequências

### Positivas

- Fonte única e autoridade única eliminam o drift back↔front (fim das duas implementações e dois defaults).
- `/tracks.is_default` e o manifesto HLS passam a concordar — o áudio que o player auto-seleciona é o mesmo que a UI marca como default.
- A regra (matching de idioma, mais canais, `subtitle_mode`) vira domínio testável sem browser; alinha ADR-005/ADR-017.
- Consistência cross-device (a preferência resolve igual em qualquer cliente).
- Dá um lar correto ao F-3 (`select_subtitle` por modo) no domínio.
- Alinhamento com o padrão da indústria (Plex/Jellyfin/Netflix: preferência por-perfil server-side; cliente aplica).

### Negativas

- Trabalho **cross-repo** e de **risco alto** (toca o player; exige smoke test manual antes de push, por CLAUDE.md).
- Novo edge cross-BC `media → preferences` (mais um Read Port + ACL; ver risco de proliferação no ADR-009).
- O frontend precisa abrir mão da sua resolução própria e passar a confiar no servidor (mudança no `homeflix-web`).
- Remover campos de `LibrarySettings` exige ajustar mapper/schemas/DTOs da Library (sem migration de banco — settings são JSON; chaves obsoletas são ignoradas na re-hidratação).

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Regressão de playback (áudio/legenda errados) | Média | Alto | Faseado, 1 PR por etapa; smoke manual obrigatório nos PRs que tocam player/HLS; limpar cache HLS no teste |
| Manifesto e `/tracks` saírem de sincronia de novo | Baixa | Médio | Ambos resolvem pelo MESMO `TrackSelector`+preferência; teste fixando a concordância |
| Front e back fora de fase durante o rollout | Média | Médio | `/tracks.is_default` já existe no contrato; manter compatível enquanto o front migra; remover `findTrackByLang` só quê o servidor já resolve |
| Proliferação de ports `media → *` | Baixa | Baixo | Vigiar em review; consolidar leituras cross-BC se surgir um padrão (ver ADR-009) |
| Gargalo: leitura cross-BC da preferência no caminho de manifesto HLS (alta volumetria) | Média | Médio | Resolver a preferência **uma vez por requisição** e reusá-la em `/tracks` e no manifesto (memoization no escopo da request); cache de curta duração por-perfil se o profiling indicar |
| Cache localStorage do front servir preferência obsoleta após o servidor virar autoritativo | Média | Médio | O front revalida via TanStack Query (`["preferences"]`) e trata o localStorage só como cache write-through; invalidar a query ao salvar preferência para refletir mudança cross-device no próximo playback |

## Alternativas Consideradas

### 1. Cliente como autoridade (manter resolução no front, limpar o backend)

O player segue resolvendo via `findTrackByLang` a partir da preferência por-usuário; o backend para de fingir seleção (`TrackSelector` de áudio e `is_default` viram inertes/removidos).

**Rejeitado porque:** contradiz o ADR-005 (regra de seleção é de domínio) e a filosofia Clean Arch do projeto; deixa a divergência manifesto↔/tracks de pé (o front continua brigando com o `DEFAULT=YES` index 0); e mantém `subtitle_mode` como lógica não-testável no cliente. Menor esforço, mas não é o desenho correto.

### 2. Manter `LibrarySettings.preferred_audio_language` como fallback de admin

Integrar o setting por-library na precedência, abaixo da preferência por-usuário (estilo "default de library" do Plex).

**Rejeitado porque:** para um media server pessoal a preferência por-perfil já basta; o setting está órfão e com default conflitante (`en` vs `pt-BR`), e mantê-lo perpetua duas fontes. Pode ser reintroduzido via novo ADR se um caso real de default por-library surgir.

### 3. Não fazer nada

Deixar back e front como estão.

**Rejeitado porque:** o drift (duas fontes, dois motores, manifesto incoerente) já é a causa de a tela de preferência "não influenciar" de forma previsível; só tende a piorar conforme F-3 e afins forem adicionados.

## Referências

- ADR-005 (Library como Entidade de Configuração) — **emendado por este ADR** quanto à localização da preferência de reprodução e à autoridade de seleção
- ADR-009 (Cross-BC Read Ports + ACL) — o edge `media → preferences`
- ADR-017 (Invariantes/regras na camada de domínio) — o `TrackSelector`
- `src/modules/media/domain/services/track_selector.py`, `src/modules/preferences/`
- homeflix-web: `src/hooks/usePlaybackPreferences.ts`, `src/pages/Player.tsx` (`findTrackByLang`, `pickPreferredSubtitleId`)
- [Plex — default audio/subtitle by account preference](https://support.plex.tv/articles/200471133-audio-subtitle-language-preferences/) · [Jellyfin — user language preferences](https://jellyfin.org/docs/)

---

## Notas de Implementação

```python
# media/application/ports/profile_playback_preference_port.py (cross-BC read, ADR-009)
class ProfilePlaybackPreferencePort(ABC):
    @abstractmethod
    async def for_profile(self, profile_id: str) -> PlaybackPreference | None: ...
    # PlaybackPreference: audio_language, subtitle_language, subtitle_mode (consumer-owned DTO)

# Resolução única, consumida por /tracks E pelo manifesto HLS:
#   TrackSelector.select_audio(tracks, pref.audio_language)
#   TrackSelector.select_subtitle(subs, audio_lang, pref.subtitle_language, pref.subtitle_mode)
```

**Rollout faseado sugerido (1 PR por etapa, smoke nos que tocam player):**
1. ADR (este) + remover os campos de preferência de reprodução de `LibrarySettings` (mapper/schemas/DTO; sem migration).
2. Port+ACL `media → preferences` + resolução server-side no `/tracks` (`is_default` passa a valer).
3. Manifesto HLS resolve o `DEFAULT=YES` pela mesma preferência (coerência com `/tracks`). **[risco alto — smoke]**
4. `select_subtitle` por modo no domínio (F-3).
5. homeflix-web: remover `findTrackByLang`/`pickPreferredSubtitleId`, passar a confiar no servidor (aplicar + override + resume). **[risco alto — smoke]**

**Cuidados de implementação (avaliação externa do ADR):**

- **Perf do read cross-BC (etapas 2–3).** Geração de manifesto pode ter alta volumetria; resolver a preferência do perfil **uma vez por requisição** e reusá-la tanto no `/tracks` quanto no manifesto (memoization no escopo da request), evitando ida-e-volta repetida entre BCs. Medir antes de adicionar cache mais agressivo.
- **Fallback gracioso no `subtitle_mode` (etapa 4).** No modo `FORCED_ONLY`, se o container não tiver as flags de legenda forçada mapeadas, o domínio deve **degradar para sem-legenda** (não cair na legenda completa). O `select_subtitle` precisa ser robusto à ausência/imprecisão dos sinais de "forced" (ver também F-4/`SubtitleFormat` para classificação).
- **Revalidação do cache do front (etapa 5).** Com o servidor autoritativo, o localStorage vira só cache write-through: invalidar a query `["preferences"]` ao salvar e confiar no servidor no próximo playback, para a consistência cross-device valer (mudou na TV → Web reflete).

## Histórico de Revisões

| Data | Autor | Mudança |
|------|-------|---------|
| 2026-06-30 | Lucas | Criação inicial |
