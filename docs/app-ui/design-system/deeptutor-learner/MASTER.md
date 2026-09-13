<!-- Hallmark · pre-emit critique: P5 H5 E5 S5 R4 V4 -->
<!-- Sources: Hallmark v1.1 + ui-ux-pro-max (cuongpt083) brand / design-system / ui-styling / ui-ux-pro-max -->

# MASTER — DeepTutor Learner

Global source of truth. Page files in `pages/` may add constraints; they may not change tokens, genre, or Presence Stage.

Product: learner-only voice tutor (mobile + desktop).  
Not: DeepTutor workspace, dashboard, Books, Partners, Memory graph.

---

## 0. How the skills combine

| Skill | What we take | What we refuse |
| --- | --- | --- |
| **Hallmark** | Locked fingerprint, anti-slop, token purity, roman headings, no fake chrome, pre-emit critique | Theme rotation per screen |
| **ui-ux-pro-max** | Priority 1→10 UX rules, style/product reasoning, icon + motion + a11y gates, pre-delivery checklist | Glassmorphism, Bento marketing, emoji icons, chart-led home |
| **brand** | Voice, messaging, asset rules, consistency checklist | Marketing slogans, invented proof |
| **design-system** | Primitive → semantic → component tokens, 8-state specs | Raw hex in components |
| **ui-styling** | Accessible primitives (focus, dialog/sheet, label), mobile-first, semantic HTML | shadcn Card farm as the product UI |

Dials used for this product (Pro Max):

- variance **3** — centered room, not brutalist / bento
- motion **2** — listen pulse + crossfade only
- density **3** — spacious study desk (24–96px air on desktop; mobile still thumb-first)

Style match (Pro Max style domain, then Hallmark veto):

- Keep: **AI-native presence**, **content-first**, **soft paper**, **minimal chrome**
- Veto: glassmorphism, claymorphism, neumorphism, aurora mesh, 3-column bento home, dark-first SaaS

Product type: **EdTech companion / voice tutor**, not LMS admin.

---

## 1. Brand

### Promise

A person-shaped tutor in a quiet room. The learner speaks. The room answers with one artifact and, only when needed, a few large choices.

### Voice (tutor + UI)

| Trait | Do | Don't |
| --- | --- | --- |
| Warm | "Bạn thử nói đáp án." | "Submit your response to proceed." |
| Short | ≤ 2 spoken sentences per turn | Lecture in one bubble |
| Concrete | "Trang 12", "Câu 2 / 5" | "Hành trình chinh phục tri thức" |
| Second person | bạn / mình (tutor) | "Người dùng", "hệ thống đã ghi nhận" |
| Honest | "Mình chưa nghe rõ." | Fake scores, fake streaks |

UI chrome labels are nouns and verbs: *Đang nghe*, *Nói lại*, *Trang này*. No exclamation marketing.

### Messaging map

| Moment | Line |
| --- | --- |
| Enter, resume | "Hôm qua mình dừng ở trang 12." |
| Ambiguous route | "Bạn muốn mình giảng, hay kiểm tra?" |
| Mishear | "Nói lại giúp mình, hoặc chọn thẻ." |
| Correct | Tutor speaks. Card rule turns ember. No confetti. |
| Wrap | "Hôm nay: phân số. Còn một mục nếu bạn muốn." |

### Logo / mark

- Wordmark "DeepTutor" in `--font-display`, roman, ink on paper.
- Optional companion mark: a small period-square (Hallmark Grid habit) in ember, 0.5em, never a gradient orb.
- Clear space = 1 cap-height on all sides.
- Do not recolor unofficially. Do not put the mark on the mic.

### Assets

- Icons: one family, outline, 1.5px stroke (Lucide or equivalent SVG). No emoji as structure.
- Character: still silhouette + 5 moods. Not a store-style 3D render on every screen.
- No fake device frames in marketing shots inside the app.

---

## 2. Token architecture

Three layers. Components bind only to **semantic** or **component** tokens.

### 2.1 Primitive

```css
:root {
  /* paper band */
  --p-paper-0: oklch(0.97 0.012 85);
  --p-paper-1: oklch(0.94 0.018 80);
  --p-paper-2: oklch(0.90 0.024 75);
  --p-paper-3: oklch(0.86 0.028 72);

  /* ink */
  --p-ink-0: oklch(0.22 0.025 55);
  --p-ink-1: oklch(0.42 0.020 60);
  --p-ink-2: oklch(0.58 0.018 65);

  /* ember (accent hue 45) */
  --p-ember-0: oklch(0.72 0.10 45);
  --p-ember-1: oklch(0.62 0.14 45);
  --p-ember-2: oklch(0.48 0.12 45);
  --p-ember-ink: oklch(0.28 0.08 45);

  /* listen green — isolated hue */
  --p-listen-0: oklch(0.72 0.08 155);
  --p-listen-1: oklch(0.58 0.11 155);

  /* focus cool — isolated hue */
  --p-focus-1: oklch(0.55 0.12 230);

  /* danger */
  --p-danger-1: oklch(0.55 0.14 25);
  --p-danger-0: oklch(0.92 0.04 25);

  /* type */
  --p-font-display: "Fraunces", "Iowan Old Style", "Palatino Linotype", serif;
  --p-font-body: "Sora", "Source Sans 3", "Segoe UI", sans-serif;
  --p-font-mono: "IBM Plex Mono", ui-monospace, monospace;

  /* space 4pt */
  --p-space-1: 4px;
  --p-space-2: 8px;
  --p-space-3: 12px;
  --p-space-4: 16px;
  --p-space-5: 24px;
  --p-space-6: 32px;
  --p-space-7: 48px;
  --p-space-8: 64px;
  --p-space-9: 96px;

  /* type 1.25 */
  --p-text-xs: 0.75rem;
  --p-text-sm: 0.875rem;
  --p-text-md: 1rem;
  --p-text-lg: 1.25rem;
  --p-text-xl: 1.6rem;
  --p-text-2xl: 2.25rem;

  --p-leading-body: 1.5;
  --p-leading-display: 1.15;

  --p-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --p-dur-1: 180ms;
  --p-dur-2: 240ms;
  --p-dur-3: 320ms;

  --p-radius-18: 18px;
  --p-radius-pill: 999px;
}
```

### 2.2 Semantic

```css
:root {
  --color-bg: var(--p-paper-0);
  --color-bg-raised: var(--p-paper-1);
  --color-bg-sunken: var(--p-paper-2);
  --color-ink: var(--p-ink-0);
  --color-ink-muted: var(--p-ink-1);
  --color-rule: var(--p-paper-3);
  --color-accent: var(--p-ember-1);
  --color-accent-ink: var(--p-ember-ink);
  --color-listen: var(--p-listen-1);
  --color-focus: var(--p-focus-1);
  --color-danger: var(--p-danger-1);
  --color-danger-bg: var(--p-danger-0);
  --color-on-accent: var(--p-paper-0);

  --font-display: var(--p-font-display);
  --font-body: var(--p-font-body);
  --font-mono: var(--p-font-mono);

  --space-page-x: var(--p-space-5);     /* 24 mobile; 32+ desktop via media */
  --space-band: var(--p-space-4);
  --space-stack: var(--p-space-5);

  --tap-min: 56px;
  --mic-min: 80px;
  --icon-sm: 16px;
  --icon-md: 24px;
  --icon-lg: 32px;

  --z-stage: 1;
  --z-band: 2;
  --z-dock: 3;
  --z-sheet: 4;
  --z-focus: 5;
}
```

Optional dark theme later maps the *semantic* layer only. Do not ship dark v1 unless contrast is measured. Default product is paper-light (study desk).

### 2.3 Component

```css
:root {
  --dock-size: var(--mic-min);
  --dock-bg: var(--color-bg-raised);
  --dock-fg: var(--color-ink);
  --dock-listen: var(--color-listen);
  --dock-speak: var(--color-accent);
  --dock-wait: var(--color-ink-muted);

  --chip-h: var(--tap-min);
  --chip-pad-x: var(--p-space-4);
  --chip-bg: var(--color-bg-raised);
  --chip-bg-on: var(--color-accent);
  --chip-fg-on: var(--color-on-accent);
  --chip-radius: var(--p-radius-pill);

  --card-radius: var(--p-radius-18);
  --card-bg: var(--color-bg-raised);
  --card-rule: var(--color-rule);
  --card-rule-on: var(--color-accent);
  --card-pad: var(--p-space-5);

  --caption-size: var(--p-text-md);
  --caption-fg: var(--color-ink);

  --sheet-bg: var(--color-bg);
  --sheet-scrim: oklch(0.22 0.025 55 / 0.45);
}
```

**Rule:** no `oklch()`, hex, or font-family names inside component files.

---

## 3. Typography

| Role | Face | Size | Weight | Notes |
| --- | --- | --- | --- | --- |
| Screen title | display | xl / 2xl | 600 | Roman only |
| Spoken line / caption | display | lg | 500 | 2 lines max on mobile |
| Chip / card label | body | md | 600 | one line, overflow-wrap anywhere |
| Helper / timestamp | mono or body sm | sm | 500 | page · 12, 03:14 |
| Body rare | body | md | 400 | lh 1.5; measure ≤ 60ch on desktop |

Base 16px. Do not set body under 14px. Quiz options ≥ 16px.

Google import (if web):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Sora:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
```

---

## 4. Layout — Presence Stage

Verified widths: 320 / 375 / 414 / 768 / 1280 / 1440.

```
mobile                          desktop
┌─────────────────────┐         ┌──┬──────────────────┐
│ rail 44–48          │         │  │ rail             │
├─────────────────────┤         │C │                  │
│                     │         │o │   STAGE          │
│ STAGE               │         │n │                  │
│                     │         │t │                  │
├─────────────────────┤         │x │──────────────────│
│ decision band       │         │t │ decision band    │
├─────────────────────┤         ├──┼──────────────────┤
│ dock + safe area    │         │  │ dock             │
└─────────────────────┘         └──┴──────────────────┘
```

- Root `overflow-x: clip` on `html, body`.
- Safe-area insets on rail and dock (`env(safe-area-inset-*)`).
- Bottom content padding ≥ dock height + safe area so nothing hides behind the mic.
- Desktop context rail ≤ 280px. Stage owns the rest.
- Long text on tablet/desktop: max-width 60ch, not edge-to-edge.

Breakpoints (Tailwind-compatible, mobile-first):

```
sm  375
md  768
lg  1024
xl  1280
```

No bottom tab bar of 5 items. Navigation is session overflow + back. Pro Max nav cap (≤5) is satisfied by *almost no nav*.

---

## 5. Component specifications

Every interactive component implements: default, hover, focus-visible, active, disabled, loading, error, success — even if some are rare on touch.

Pressed feedback 80–150ms. Pressed visuals must **not** change layout bounds.

### 5.1 VoiceDock

Anatomy: disc + state word + optional interrupt hint.

| State | Disc fill | Ring | Label |
| --- | --- | --- | --- |
| default | `--dock-bg` | none | Giữ để nói |
| hover | `--p-paper-2` | none | |
| focus-visible | `--dock-bg` | 2px `--color-focus` | |
| active | `--p-paper-3` | none | translateY 0 (no jump) |
| listening | `--color-bg` | 3px `--dock-listen` + pulse | Đang nghe |
| thinking / loading | `--dock-bg` | 2px `--dock-wait` | Đang nghĩ |
| speaking | `--color-bg` | 3px `--dock-speak` | Đang nói · chạm để ngắt |
| disabled | `--dock-bg` 50% | none | |
| error | `--color-danger-bg` | 2px `--color-danger` | Nói lại |
| success | unused on dock | — | result lives on stage |

Size: `--mic-min` (80) visual; hit area at least that. Desktop Space = hold-to-talk.

`aria-label` changes with state. Live region: polite for thinking/speaking, assertive for error.

### 5.2 Chip

Height `--chip-h`. Pill. Label ≤ 22 characters, one line.

| State | Background | Foreground | Rule |
| --- | --- | --- | --- |
| default | `--chip-bg` | `--color-ink` | 1px `--color-rule` |
| hover / focus-visible | `--p-paper-2` | `--color-ink` | focus ring |
| active | `--p-paper-3` | `--color-ink` | |
| selected / success | `--chip-bg-on` | `--chip-fg-on` | none |
| disabled | `--chip-bg` | `--color-ink-muted` | |
| loading | `--chip-bg` | `--color-ink-muted` | |

Max 4 chips in the band. Fifth+ → PickerSheet.

### 5.3 ChoiceCard

Used for quiz options and Auto-route forks.

```
┌──────────────────────────────┐
│  [mark]  Label               │
│          optional stem line  │
└──────────────────────────────┘
```

Min height 64 mobile. Padding `--card-pad`. Radius `--card-radius`.

| State | Rule | Mark |
| --- | --- | --- |
| default | 1px `--card-rule` | empty |
| hover / focus | 1px `--color-ink-muted` | |
| selected | 2px `--card-rule-on` | ember tick (SVG) |
| correct / success | 2px `--card-rule-on` | tick |
| error (wrong pick) | 2px `--color-danger` | dash |
| disabled | faded | |

Color is not the only signal: tick / dash + tutor speech.

### 5.4 PickerSheet (combo-box for learners)

Full-width sheet. Scrim `--sheet-scrim` measured on paper-0 (must isolate foreground).

- Rows ≥ 56px
- Icon 24 + label
- Speak-to-filter: dock stays usable
- Close: chip "Đóng" + swipe down + Esc
- Focus trap inside sheet; restore focus to opener

Not a native `<select>`. Not a command palette.

### 5.5 ArtifactStage

Mounts exactly one: page | player | figure | stem | none (character owns the middle).

- Page: paper plate, page number in mono
- Player: native controls + timestamp chips from the band, not a second control cluster
- Figure: SVG/canvas, no card shadow stack
- Stem: quiz question in display face

When artifact takes the middle on mobile, character becomes a 48px still in the rail, still announcing mood to AT.

### 5.6 Caption

One block under presence. Max 2 lines. Fades after the next listen starts. Not a chat log.

### 5.7 TranscriptDrawer

Overflow only. Labelled "Lời thoại". Closed default. Desktop may dock; still closed default.

### 5.8 Character

Moods: listen, think, speak, wait, encourage.  
No lip-sync requirement in v1 if it adds >200ms. Presence > theatrics.

### 5.9 Components we do not ship on learner surface

Navbar mega-menu, data table, toast success, badge XP, input composer, tabs of modes, sidebar of 8 tools, theme toggle in v1.

shadcn primitives allowed *under* the room (Dialog/Sheet, Focus scope, VisuallyHidden) — not Card/Dashboard layouts.

---

## 6. UX rules applied (Pro Max 1→10)

### 1 Accessibility — CRITICAL

- Contrast body ≥ 4.5:1 on paper (ink-0 on paper-0).
- Accent-on-paper for large controls only after check; ember fill uses `--color-on-accent`.
- Keyboard: Tab order = rail → stage choices → dock. Space talks on desktop.
- `aria-live` on caption and dock state.
- Icon-only controls need names (mic, close, overflow).
- Decorative character marks `aria-hidden` when caption already carries the line.
- Color never sole indicator (quiz wrong = dash + speech).
- Reduced motion: no pulse; ≤150ms fade.
- Dynamic Type: labels wrap; dock stays ≥ tap-min; no clipped captions.
- Drag/swipe always has a button alternative.

### 2 Touch & interaction — CRITICAL

- Targets ≥ 56 learner (stricter than 44/48).
- 8px+ gap between chips.
- Feedback ≤ 150ms.
- No hover-only affordance.
- One primary gesture per region (stage tap ≠ dock hold).

### 3 Performance — HIGH

- Character is vector or one static + mood swap, not a 4K loop.
- Reserve stage height to keep CLS < 0.1 when a figure arrives.
- Lazy-load transcript and video.
- WebP/AVIF for any photo of material pages if raster.

### 4 Style selection — HIGH

- One style: paper desk + ember live state.
- SVG icons, outline, one stroke.
- Do not mix skeuomorphic mic photoreal with flat cards.

### 5 Layout & responsive — HIGH

- Viewport meta; user-scalable not disabled (a11y).
- No horizontal scroll.
- Safe areas.
- Hallmark 320–768 plus desktop.

### 6 Typography & color — MEDIUM

- Tokens only.
- No gray-on-gray captions (`ink-muted` on `paper-0` must pass 4.5:1; if not, use `ink`).
- No italic headings.

### 7 Animation — MEDIUM

- Motion has a name: *listen pulse*, *band mount fade*.
- Do not animate width/height of the dock.
- Shared `--p-dur-*` + `--p-ease-out`.

### 8 Forms & feedback — MEDIUM

- Almost no forms. FailedHear may offer one field: visible label "Gõ một lần", error inline.
- No placeholder-as-label.

### 9 Navigation — HIGH

- Back is always the system back + rail close.
- Deep link `{session, artifact, turn}`.
- No 5-item tab bar.

### 10 Charts — LOW

- No charts on learner v1. Progress is "2 / 5".

---

## 7. Icon system

| Token | Size | Use |
| --- | --- | --- |
| icon-sm | 16 | inline in caption rare |
| icon-md | 24 | chips, picker rows |
| icon-lg | 32 | empty stage marks |

Set: mic, stop, check, minus, book, play, pause, flag-page, overflow, close, retry.  
Filled vs outline: outline everywhere; filled only for selected tick.

---

## 8. Stack guidance

Do not assume a stack. When implementing:

- **Web (Next / React):** Presence Stage as a layout route; Radix Dialog/Sheet for picker; tokens in CSS variables; Tailwind `@theme` maps semantic tokens only.
- **React Native / Flutter:** same tokens; native pressable for dock; no CSS hover as the only state.
- **Desktop shell:** same web UI in a window; Space / Esc bindings.

Avoid dynamic Tailwind class construction that drops tokens from the bundle.

---

## 9. Page overrides

See `pages/`. Each page keeps Presence Stage. Overrides are emphasis only:

| Page | Stage owner | Band |
| --- | --- | --- |
| enter | resume + topic plates | empty or talk-to-pick |
| scene | character | on demand |
| read | page | explain / quiz-page / next |
| watch | player | this-moment / recap / quiz |
| check | stem + cards | the cards |
| wrap | 3 fact plates | practice / done |

---

## 10. Pre-delivery checklist

Process

- [ ] Tokens only (no raw hex in components)
- [ ] 375 portrait + landscape watch/figure
- [ ] 320 no horizontal scroll
- [ ] Reduced motion
- [ ] Largest Dynamic Type
- [ ] Safe area + dock inset
- [ ] Contrast 4.5:1 light (dark not shipped)

Visual

- [ ] No emoji icons
- [ ] One icon family / stroke
- [ ] Accent on ≤ 2 live points
- [ ] Pressed state does not shift layout

Interaction

- [ ] Dock 8 states present
- [ ] Decision band empty unless choices exist
- [ ] ask_user never opens a textarea by default
- [ ] Screen reader order matches visual order

Product

- [ ] No chat composer on stage
- [ ] No confetti
- [ ] Transcript behind overflow
- [ ] Hallmark critique stamped if a new screen is emitted

---

## 11. File map

```
design-system/deeptutor-learner/MASTER.md      ← this file
design-system/deeptutor-learner/pages/*.md
tokens.css                                     ← generated from §2
DEEPTUTOR_SYSTEM_DESIGN.md                     ← architecture + turn machine
```

Amend MASTER when the room changes. Do not restyle a route away from Presence Stage.
