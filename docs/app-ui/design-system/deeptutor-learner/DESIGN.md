# Design System: DeepTutor Learner

**Product:** learner-only voice tutor (mobile + desktop). Not a workspace, dashboard, LMS, or chat app.
**Macrostructure:** Presence Stage — one room, five doors.
**Vibe:** quiet paper desk, one warm companion.
**Genre:** atmospheric with editorial restraint. Paper-light study desk. No dark theme in v1.

A learner opens a lesson, talks to a tutor character, and only taps when the tutor needs a confirmation, an answer, or a pivot. The screen holds one presence and one artifact. Chat history is an audit drawer, not the product.

---

## Overview

Warm paper surfaces, roman serif display, grotesk body, ember used only for *live state*. Geometry and paper do the structure. The object on screen is a person-shaped tutor and a piece of work (page, clip, problem, figure).

Variance 3 — centered room, not brutalist or bento.
Motion 2 — listen pulse + crossfade only.
Density 3 — spacious study desk (24–96px air on desktop; mobile still thumb-first).

Keep: AI-native presence, content-first, soft paper, minimal chrome.
Veto: glassmorphism, claymorphism, neumorphism, aurora mesh, 3-column bento home, dark-first SaaS, ChatGPT-on-purple, card farms.

---

## Colors

Canonical tokens are OKLCH in `tokens.css`. Hex below is the sRGB lock for Stitch.

- **Paper / surface** (#F9F5EC): page background. Never tint the whole stage ember.
- **Paper raised** (#F2EADE): dock, chips, choice cards at rest.
- **Paper sunken** (#E8DCCD): pressed plates, slightly deeper paper.
- **Paper rule edge** (#DDCEBE): hairline structure.
- **Ink** (#24180F): primary text, character silhouette, wordmark.
- **Ink muted** (#564B42): helpers only if contrast ≥ 4.5:1 on paper; otherwise use Ink.
- **Rule** (#CBC3B8): 1px borders on chips/cards at rest.
- **Ember / accent** (#C96736): live turn only — speaking ring, selected card rule, playhead. Appear in at most two places on a screen.
- **Ember ink** (#471800): selected choice label, accent-on-paper text.
- **On accent** (#F9F5EC): text on ember fill (primary CTA).
- **Listen** (#3B8D5D): listening ring / waveform only. Never a brand wash.
- **Wait** (#AC9C83): thinking state on the dock.
- **Focus** (#007DAA): keyboard focus ring only. Never the accent.
- **Danger** (#B54A46): wrong quiz pick, hear-error. Pair with a dash mark, not color alone.
- **Danger wash** (#FEDBD7): error dock fill.

Stitch seed mapping (FIDELITY, do not generate a rainbow palette):

- Primary = Ember `#C96736`
- Secondary = Wait / warm stone `#AC9C83`
- Tertiary = Ember ink `#471800`
- Neutral = Ink muted `#564B42`
- Surface = Paper `#F9F5EC`

---

## Typography

Headings stay roman. No italic display headings. No Inter / Roboto / Arial as the brand face.

- **Headline / display:** Literata (stand-in for Fraunces). Weight 500–600. Screen titles xl/2xl. Spoken caption lg, 2 lines max on mobile. Line-height 1.15.
- **Body:** Sora. Weight 400–600. Chip and card labels md / 600, one line. Quiz options ≥ 16px. Body measure ≤ 60ch on desktop. Line-height 1.5.
- **Label / chrome:** Sora. Weight 500–600. Nouns and verbs: *Đang nghe*, *Nói lại*, *Trang này*.
- **Mono:** JetBrains Mono (stand-in for IBM Plex Mono). Timestamps and page numbers only (`trang · 12`, `03:14`).

Base 16px. Do not set body under 14px.

---

## Spacing and shape

4px grid: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96.

- Page gutter 24 mobile, 32+ desktop.
- Chip gap ≥ 8px.
- Tap target ≥ 56px (learner floor). Mic disc ≥ 80px.
- Card radius 18px (choice cards only). Stage itself is unboxed.
- Pill radius 999px on primary/secondary CTAs and chips.
- Input radius 12px.
- Stitch roundness token: ROUND_TWELVE. Pills are documented as full-round exceptions, not the stage.

No elevation / shadow stack. Structure is hairline rule on paper. The mic is a disc on the dock, not a floating marketing FAB.

---

## Layout — Presence Stage

Every learner screen is the same room:

```
rail: topic · page/time · overflow     (hairline, not a product nav)
PRESENCE or ARTIFACT                   (character + one spoken line, or page/clip/figure/stem)
decision band                          (0–4 chips or choice cards; empty is correct)
voice dock                             (mic · state word · interrupt)
```

Rules of the room:

1. One focus. Presence *or* artifact owns the middle. Never presence + transcript + artifact + composer.
2. Decision band is empty until the tutor asks. Do not invent shortcuts to fill it.
3. Voice dock is permanent. Keyboard is overflow, not default.
4. Caption is ephemeral: one or two lines under the character. Full transcript lives behind overflow labelled "Lời thoại".
5. No two-line tap labels. Shorten copy instead of shrinking type.
6. No bottom tab bar. Navigation is session overflow + system back.
7. Root overflow-x clip. Safe-area insets on rail and dock.
8. Accent colour appears in ≤ 2 places at once.

### Mobile

Single column. When an artifact takes the middle, the character shrinks to a 48px corner still in the rail (still speaking). Mic thumb-reachable. Read / Watch are sequential, not 50/50. Landscape only for Watch and figure. Enter shows at most three plates.

### Desktop

Three bands, not three products: slim context rail (≤ 280px) / stage / dock. Character may stay visible in the rail while a page is open. Space = hold-to-talk. Esc interrupts. Artifact can be large. Transcript drawer docks left, closed by default.

Verified widths: 320 / 375 / 414 / 768 / 1280 / 1440.

---

## Components

### VoiceDock (permanent)

Disc + state word + optional interrupt hint. Hit area ≥ 80px.

| State | Disc | Ring | Label |
| --- | --- | --- | --- |
| default | paper raised | none | Giữ để nói |
| hover | paper sunken | none | |
| focus-visible | paper raised | 2px focus | |
| active | paper-3, no layout jump | none | |
| listening | paper | 3px listen + pulse | Đang nghe |
| thinking | paper raised | 2px wait | Đang nghĩ |
| speaking | paper | 3px ember | Đang nói · chạm để ngắt |
| disabled | 50% | none | |
| error | danger wash | 2px danger | Nói lại |

Desktop: Space holds-to-talk. Pressed feedback 80–150ms without changing bounds.

### Chip

Height 56. Pill. Label ≤ 22 characters, one line. Max 4 in the band; fifth+ becomes a picker sheet.

Default: paper raised, ink, 1px rule. Selected/success: ember fill, on-accent text.

### ChoiceCard

Quiz options and Auto-route forks. Min height 64 mobile. Padding 24. Radius 18. 1px rule at rest; selected = 2px ember rule + ember tick SVG; wrong = 2px danger + dash. Color is never the only signal.

### PickerSheet

Full-width sheet for long lists (topic, chapter). Rows ≥ 56. Icon 24 + short label. Speak-to-filter; dock stays usable. Close: chip "Đóng" + swipe down + Esc. Not a native select. Not a command palette.

### ArtifactStage

Mounts exactly one: page | player | figure | stem | none. No chat list. Page is a paper plate with mono page number. Player uses native controls + timestamp chips in the band. Figure is SVG/canvas with no card-shadow stack. Stem is the quiz question in display face.

### Caption

One block under presence. Max 2 lines. Fades when the next listen starts. Not a chat log.

### TranscriptDrawer

Overflow only. Label "Lời thoại". Closed by default.

### Character

Still, readable silhouette. Moods only: listen, think, speak, wait, encourage. Furniture of the room, not a 3D mascot product shot. No lip-sync theatre in v1.

### Primary CTA

Ember fill, pill, padding 16/22, label ≤ 22 characters, one line, on-accent text.

### Secondary CTA

Hairline rule, paper fill, same pill.

### Progress

"Câu 2 / 5" or "Còn một mục" in the rail. No charts, streaks, XP, or leaderboards.

Components we do not ship: navbar mega-menu, data table, toast success, badge XP, input composer, mode tabs, sidebar of tools, theme toggle, confetti, fake device chrome.

---

## Motion

Silent room. Two primitives only:

- State crossfade: opacity ≤ 240ms, ease cubic-bezier(0.16, 1, 0.3, 1).
- Listen pulse: scale 1 → 1.04, 900ms, respects reduced motion.

Reduced motion: drop pulse; ≤ 150ms opacity. No page-load hero choreography. No confetti on correct quiz. Correct = card rule turns ember, tutor speaks. Silent success — no "Saved!" toast.

---

## Voice and copy

Warm, short, concrete, second person, honest.

Do: "Bạn thử nói đáp án." / "Hôm qua mình dừng ở trang 12." / "Mình chưa nghe rõ."
Don't: "Submit your response to proceed." / "Hành trình chinh phục tri thức." / fake scores.

Spoken line ≤ 2 sentences. If the tutor must list options, the options are cards — do not read four long choices aloud. UI chrome is nouns and verbs, no exclamation marketing.

---

## Screens (same system, different emphasis)

| Screen | Middle owner | Decision band |
| --- | --- | --- |
| Enter | resume card + 2–3 topic plates | none, or "talk to pick" |
| Scene | character | chips when the tutor asks |
| Read | document page | Giải thích trang này · Đặt 3 câu · Trang sau |
| Watch | player | Đoạn này · Tóm tắt vừa rồi · Quiz đoạn này |
| Check | stem + options or one step card | those options *are* the band |
| Wrap | 3 fact plates | Luyện thêm · Xong |

Enter: no marketing hero, no 3-feature grid, no streak flame. Resume plate first if a session exists.
Scene: no message list, no composer, no mode tabs.
Read: citation chip seeks; highlight color is not the only cue.
Watch: native playback; no second waveform; dock reachable in landscape.
Check: one item visible; 2–4 choice cards; no rainbow A/B/C/D; no timer pressure; no phone-shake.
Wrap: honest recap; no dashboard, no share-to-social, no "top 10%".

Routes: `/` Enter · `/scene` · `/read` · `/watch` · `/check` · `/wrap`. Overflow sheet: transcript, voice speed, tutor voice, leave session.

---

## Icons

One family, outline, 1.5px stroke (Lucide or equivalent SVG). No emoji as structure. Outline everywhere; filled only for the selected tick. Set: mic, stop, check, minus, book, play, pause, flag-page, overflow, close, retry. Sizes 16 / 24 / 32.

---

## Accessibility

- Contrast body ≥ 4.5:1 (ink on paper).
- Keyboard: Tab order rail → stage choices → dock. Space talks on desktop.
- `aria-live` on caption and dock state. Icon-only controls have names.
- Color never sole indicator.
- Dynamic Type: labels wrap; dock stays ≥ tap-min; no clipped captions.
- Drag/swipe always has a button alternative.
- User-scalable not disabled.

---

## Do's and Don'ts

Do:

- Lock this fingerprint across every screen. Screen voice may shift; tokens, type, chrome, and motion may not.
- Spend ember on live state only.
- Leave the decision band empty when the tutor is not asking.
- Ship 8 VoiceDock states.
- Use Vietnamese UI labels as specified.

Don't:

- Hero → 3 feature cards → CTA → footer.
- Gradient mesh, glassmorphism, glow orbs.
- Persistent composer + infinite bubbles as the primary surface.
- Invented metrics, streaks, XP, leaderboards.
- Rainbow quiz options or confetti.
- Mid-render colour improvisation (every fill references a token).
- Fake phone chrome or fake browser bars.
- Two-column tiny split on a phone.
- Open a textarea because `ask_user` fired — terminate on the decision band.
- Restyle a single route away from Presence Stage.
