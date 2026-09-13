<!-- Hallmark · pre-emit critique: P5 H5 E4 S5 R5 V4 -->

# DeepTutor Learner App — System Design

Locked design system + product architecture for the **learner-facing** mobile and desktop app.

This is not the full DeepTutor workspace. It is the **study scene**: a voice-first character tutor with visual scaffolding. Future UI work reads this file first and defers to it. Amend the file; do not override locally.

Provenance: Hallmark disciplines (Nutlope/hallmark v1.1) applied to a multi-surface product. Brand axes stay locked across screens. Screen *voice* may shift; tokens, type, chrome, and motion stance may not.

---

## 1. Brief and cuts

### Product sentence

A learner opens a lesson, talks to a tutor character, and only taps when the tutor needs a confirmation, an answer, or a pivot. The screen holds one presence and one artifact. Chat history is an audit drawer, not the product.

### In scope

- Session start / resume
- Character + voice dock
- Auto-route: teach, check, solve, quiz
- Thin context: existing material, existing video, course topic
- Immersive reading (page + tutor)
- Immersive watching (timestamp + tutor)
- Generated figure on stage
- Session wrap (what we did / practice more)

### Out of scope (learner app)

Books compiler, Co-Writer, Notebook, Memory workbench, Partners / subagents / MCP / CLI, KB engine admin, workspace file ops, research reports, guardian/admin consoles.

Those stay on a separate operator surface if needed.

---

## 2. Hallmark lock

Hallmark's multi-page rule: lock brand axes; do not invent a new fingerprint per screen. This product is one room with five doors, not five landing pages.

### System

- Genre · atmospheric, with editorial restraint (not playful-SaaS, not dashboard-minimal)
- Macrostructure · **Presence Stage**
- Theme · custom (vibe: "quiet paper desk, one warm companion")
- Axes · warm-paper / roman display grotesk / ember accent

### Why this fingerprint

A voice tutor that looks like ChatGPT-on-purple, or like a card farm with 3 feature tiles, is slop. The object on screen is a person-shaped tutor and a piece of work (page, clip, problem, figure). Geometry and paper do the structure. The accent is spent on *live state* (listening ring, chosen card, current timestamp) — not on decoration.

### Anti-patterns refused

- Hero → 3 feature cards → CTA → footer
- Gradient mesh backgrounds, glassmorphism, glow orbs
- Inter / Roboto / Arial stacks as the brand face
- Italic display headings
- Fake phone chrome, fake browser bars
- Invented metrics on the home scene ("10× faster learning")
- Rainbow quiz options
- Persistent composer + infinite bubbles as the primary surface
- Mid-render colour improvisation (every fill references a token)

### Six disciplines (always on)

1. Pre-emit critique before shipping a screen.
2. Honest copy. No fake mastery percentages.
3. Locked tokens only.
4. No redrawn device chrome.
5. Verify 320 / 375 / 414 / 768, plus desktop 1280 / 1440.
6. Headings stay roman.

---

## 3. Tokens

Canonical source of truth: `tokens.css`. Values below are the lock. Do not inline OKLCH in components.

```css
:root {
  --color-paper:      oklch(0.97 0.012 85);
  --color-paper-2:    oklch(0.94 0.018 80);
  --color-paper-3:    oklch(0.90 0.024 75);
  --color-ink:        oklch(0.22 0.025 55);
  --color-ink-2:      oklch(0.42 0.020 60);
  --color-rule:       oklch(0.82 0.018 75);
  --color-accent:     oklch(0.62 0.14 45);      /* ember — live state only */
  --color-accent-ink: oklch(0.28 0.08 45);
  --color-focus:      oklch(0.55 0.12 230);     /* cool focus, never the accent */
  --color-listen:     oklch(0.58 0.11 155);     /* listening only */
  --color-speak:      oklch(0.62 0.14 45);      /* speaking = accent */
  --color-wait:       oklch(0.70 0.04 80);
  --color-danger:     oklch(0.55 0.14 25);

  --font-display: "Fraunces", "Iowan Old Style", "Palatino Linotype", serif;
  --font-body:    "Sora", "Source Sans 3", "Segoe UI", sans-serif;
  --font-mono:    "IBM Plex Mono", ui-monospace, monospace;

  --space-3xs: 4px;
  --space-2xs: 8px;
  --space-xs:  12px;
  --space-sm:  16px;
  --space-md:  24px;
  --space-lg:  32px;
  --space-xl:  48px;
  --space-2xl: 64px;
  --space-3xl: 96px;

  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-md: 1rem;
  --text-lg: 1.25rem;
  --text-xl: 1.6rem;
  --text-display: 2.25rem;

  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-fast: 180ms;
  --dur-base: 240ms;
  --dur-slow: 320ms;

  --radius-card: 18px;   /* choice cards only — stage itself is unboxed */
  --radius-pill: 999px;
  --radius-input: 12px;

  --tap-min: 56px;       /* mobile floor; desktop may use 44px on rails */
  --mic-min: 80px;
}
```

### Token spend rules

- `--color-accent` is not a brand wash. It marks *the live turn*: mic while speaking, selected choice, playhead.
- `--color-listen` never appears except in the listening ring / waveform.
- Paper stays paper. Do not tint the whole stage ember.
- One display face for character lines and screen titles. Body face for chips, captions, quiz stems. Mono only for timestamps and page numbers.

### CTA voice

- Primary · ember fill · pill · 16 / 22 padding · label ≤ 22 characters, one line
- Secondary · hairline rule, paper fill · same pill
- Choice card · paper-2 plate, 18 radius, 2px rule; selected = 2px accent rule + accent-ink label
- No shadowed floating FAB except the mic, which is a disc on the dock, not a marketing button

### Motion stance

- Silent room. Two primitives only: **state crossfade** (opacity ≤ 240ms) and **listen pulse** (scale 1 → 1.04, 900ms, respects reduced motion).
- Reduced motion: drop pulse; ≤ 150ms opacity.
- No page-load hero choreography. No confetti on correct quiz. Correct = card rule turns ember, tutor speaks.
- Silent success. No "Saved!" toast if the next card is already on stage.

---

## 4. Macrostructure — Presence Stage

Every learner screen is the same room:

```
┌──────────────────────────────────────────┐
│ rail: topic · page/time · overflow       │  hairline, not a product nav
├──────────────────────────────────────────┤
│                                          │
│            PRESENCE                      │  character + one spoken line
│            or ARTIFACT                   │  page / clip / figure / stem
│                                          │
├──────────────────────────────────────────┤
│ decision band                            │  0–4 chips or choice cards
├──────────────────────────────────────────┤
│ voice dock                               │  mic · state word · interrupt
└──────────────────────────────────────────┘
```

### Rules of the room

1. **One focus.** Presence *or* artifact owns the middle. Never presence + transcript + artifact + composer.
2. **Decision band is empty until the tutor asks.** Empty is correct. Do not invent shortcuts to fill it.
3. **Voice dock is permanent.** It does not hide behind the keyboard. Keyboard is an overflow, not a default.
4. **Caption is ephemeral.** One or two lines under the character. It fades. Full transcript lives behind a labelled overflow, not on stage.
5. **No two-line tap labels.** Chip text wraps by being shorter, not by shrinking type.

### Screen voices (same system, different emphasis)

| Screen | Middle owner | Decision band |
| --- | --- | --- |
| Enter | resume card + 2–3 topic plates | none, or "talk to pick" |
| Scene | character | chips when the tutor asks |
| Read | document page | explain / quiz-this-page / next |
| Watch | player | this-moment / recap / quiz-clip |
| Quiz & solve | stem + options or step card | those options *are* the band |
| Wrap | 3 fact plates | practice / done |

Do not give Enter a marketing hero. Do not give Wrap a dashboard chart.

---

## 5. Product architecture

```
                    ┌─────────────┐
   mic / tap   →    │  Client UI  │  Presence Stage
                    └──────┬──────┘
                           │ session events
                    ┌──────▼──────┐
                    │  Session    │  context + turn machine
                    │  Orchestrator
                    └──────┬──────┘
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     Voice stack     Tutor runtime     Artifact
     STT / TTS       DeepTutor         store
     barge-in        capabilities      page / time /
                     (subset)          figure / quiz
```

The learner client never talks to RAG engines, MCP, or Partners. It talks to **one session API**.

### Runtime subset (mapped from DeepTutor)

| Learner intent | Runtime capability | UI object |
| --- | --- | --- |
| Teach this | `chat` + grounded RAG | spoken turn + caption |
| Check me | `deep_question` / quiz cards | choice cards |
| Solve this | `deep_solve` | step cards, not a monologue |
| Show a figure | `visualize` (server-picked renderer) | stage figure |
| This page | immersive reading | page + citation chip |
| This minute | immersive watching | player + timestamp chip |
| What next | `auto` router | 2–3 mode cards only when ambiguous |

`ask_user` from the runtime **must** terminate on the decision band. If the model asks a question and the client has no cards, the turn is incomplete — do not fall back to a text area.

---

## 6. Turn machine

A turn is the unit of UI. Screens do not own loops; the session does.

```
Idle
  → Listening          (dock = listen colour)
  → Understanding      (short wait mark, no spinner farm)
  → Routing            (silent unless Auto is unsure)
  → Speaking           (dock = accent, caption live)
  → AwaitingChoice     (decision band populated)
  → ActingOnArtifact   (page jump, seek, figure swap)
  → FailedHear         (two chips: say-again / type-this-once)
```

### Contracts

**Client → session**

```json
{
  "session_id": "…",
  "input": {
    "kind": "voice | choice | artifact_gesture",
    "transcript": "optional",
    "choice_id": "optional",
    "artifact": { "type": "page | timestamp | region", "ref": "…" }
  }
}
```

**Session → client**

```json
{
  "turn_id": "…",
  "speak": { "text": "≤ 2 sentences preferred", "ssml": null },
  "caption": "same text or shorter",
  "character": { "mood": "listen | think | speak | wait | encourage" },
  "choices": [
    { "id": "a", "label": "Phân số", "hint_icon": "optional" }
  ],
  "artifact": {
    "type": "none | page | video | figure | stem",
    "ref": "…",
    "highlight": "optional"
  },
  "progress": { "label": "Câu 2 / 5", "optional": true }
}
```

Hard limits for the learner surface:

- `speak.text` target ≤ 280 characters. Longer teaching is split across turns with a "còn tiếp" chip.
- `choices.length` ∈ {0, 2, 3, 4}. More than four becomes a full-width picker sheet, still tappable / speakable by label.
- No markdown essay in `caption`.

---

## 7. Information architecture

Five routes. No settings tree.

```
/               Enter
/scene          default study scene
/read           material on stage
/watch          video on stage
/check          quiz or solve cards
/wrap           end of session
```

Overflow (sheet, not a page): transcript, speed of voice, tutor voice, leave session.

Deep links restore `{session_id, artifact_ref, turn_id}`. Resume is a first-class Enter plate, not a toast.

---

## 8. Interaction design

### Voice dock — 8 states (Hallmark component discipline)

| State | What the learner sees | Colour token |
| --- | --- | --- |
| default | mic disc, label "Giữ để nói" | ink on paper-2 |
| hover / focus-visible | hairline focus ring | `--color-focus` |
| active | pressed 1px | ink |
| listening | pulse + "Đang nghe" | `--color-listen` |
| thinking | still disc, "Đang nghĩ" | `--color-wait` |
| speaking | waveform tick, "Đang nói · chạm để ngắt" | `--color-accent` |
| disabled | muted, session blocked | ink-2 40% |
| error | "Nói lại" as the primary chip | `--color-danger` |

Desktop: Space holds-to-talk. Esc interrupts speech. Focus never trapped in an invisible composer.

### Visual scaffolding catalogue

Use these and no others on the learner surface:

- **Chip** — pivot or confirm (Có / Nói lại / Trang này)
- **Choice card** — quiz option or ambiguous route
- **Picker sheet** — long list (topic, chapter) with speak-to-filter
- **Step card** — one solve step
- **Citation chip** — page or timestamp; tap seeks
- **Progress tick** — "2 / 5", not a dashboard

Combo-box in the original brief = picker sheet. It is full-width, large type, icon + short label. It is not a desktop `<select>`.

### Gesture floor (learners who do not type)

- Tap and speak first.
- Swipe only to change page or dismiss a sheet.
- No drag-and-drop.
- Camera on mobile is a valid way to put a problem on stage.
- Keyboard appears only for: rename is out of scope; FailedHear "type once"; search inside a long picker if voice failed.

---

## 9. Mobile vs desktop

Same tokens, same turn machine, different allocation of the room.

### Mobile

- Single column Presence Stage.
- Artifact replaces the character (character shrinks to a 48px corner still, still speaking).
- Mic ≥ `--mic-min`, thumb-reachable.
- Read / Watch are sequential, not 50/50 split.
- Landscape allowed only for Watch and figure.
- Enter shows at most three plates. The rest is "nói tên bài".

### Desktop

- Three bands, not three products: slim context rail / stage / dock.
- Character may stay visible while a page is open (rail width, not a second hero).
- Keyboard is a parallel, not a substitute: Space = talk.
- Artifact can be large. Transcript drawer docks left, closed by default.
- No operator settings. Voice speed lives in overflow.

Breakpoint behaviour follows Hallmark mobile gates: no horizontal scroll, `overflow-x: clip` on root, no two-line tappable labels, image tracks `minmax(0, 1fr)`.

---

## 10. Character and copy

The character is furniture of the room, not a 3D mascot product shot.

- Still, readable silhouette. Mood is a small set of poses, not lip-sync theatre if it fights latency.
- One spoken line on stage. If the tutor must list options, the options are cards — do not read four long choices aloud.
- Copy voice: short, concrete, second person. "Bạn chọn đáp án nào?" not "Hãy tận dụng tiềm năng học tập của bạn".
- No italic headings. Emphasis by weight or ember underline.
- No invented streaks, XP, or leaderboards in v1. If progress exists, it is "Câu 2 / 5" or "Còn một mục".

---

## 11. Client module map

Keep the codebase aligned to the room, not to DeepTutor's full web IA.

```
app/
  enter/
  scene/
  read/
  watch/
  check/
  wrap/
ui/
  VoiceDock/
  Character/
  DecisionBand/
  ChoiceCard/
  Chip/
  PickerSheet/
  ArtifactStage/
  Caption/
  TranscriptDrawer/
session/
  turnMachine.ts
  sessionApi.ts
voice/
  stt.ts
  tts.ts
  bargeIn.ts
tokens.css
```

`ArtifactStage` mounts page, player, figure, or stem. It does not mount a chat list.

---

## 12. Data the learner app is allowed to know

Per session:

- `session_id`, learner display name
- attached `material_id` or `video_id` or `topic_id` (one primary)
- turn log (for resume + guardian export elsewhere)
- quiz item ids and scores for *this* session
- voice preference (rate, persona id)

The app does not fetch engine type, embedding model, cost ledger, memory graph, or partner channel status.

---

## 13. Quality gates before a screen ships

Score 1–5. Anything under 3 is rewritten.

| Axis | Question for this product |
| --- | --- |
| Philosophy | Is the tutor present, or did we ship a chat wrapper? |
| Hierarchy | Can a child find the mic and the one question in one glance? |
| Execution | Tokens only? 8 dock states? 320px no clip? |
| Specificity | Does this screen look like a desk with a person, not a SaaS shell? |
| Restraint | Did we add a control that the turn machine did not ask for? |
| Variety | Across the five routes, did we keep one room — not five templates? |

Additional product gates:

- [ ] Decision band empty unless `choices.length > 0`
- [ ] `ask_user` never opens a textarea by default
- [ ] Correct quiz answer does not fire confetti
- [ ] Transcript is behind overflow
- [ ] Accent colour appears ≤ 2 places on screen at once
- [ ] Reduced-motion path exists for the listen pulse

---

## 14. Build order

1. Tokens + Presence Stage shell + VoiceDock 8 states  
2. Turn machine against a stub session (`speak` + `choices`)  
3. Enter + Scene  
4. Check (quiz / solve cards)  
5. Read + citation seek  
6. Watch + timestamp chips  
7. Figure mount on ArtifactStage  
8. Wrap + resume  

Do not start with settings, themes beyond this lock, or a message list.

---

## Exports

`tokens.css` is the source of truth for colour, type, space, radius, and duration.

If the implementation uses Tailwind v4, map these 1:1 into `@theme`. Do not add extra brand colours in utility classes.

Amend this file when the room itself changes. Do not restyle a single route away from Presence Stage.
