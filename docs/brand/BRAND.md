# Nick of Time — Brand Specification

## 1. Brand

**Name:** Nick of Time  
**Team:** Nick of Time  
**Positioning:** A precise, trustworthy, futuristic identity for an AI dispute-intake system that turns uncertain card-dispute conversations into verified actions, evidence, and a clear deadline.

**Tagline:** **Verified action. Before the deadline.**

## 2. Brand personality

- Futuristic
- Cosmic
- Professional
- Precise
- Trustworthy
- Transparent
- Calm under urgency

The brand should feel like **precision technology expressed through a cosmic visual language**, not like a gaming, cyberpunk, or space-themed consumer brand.

## 3. Core visual idea — Shield Constellation

The logo combines three ideas:

- **Shield:** protection and trust.
- **Constellation:** traceability, connected evidence, and system state.
- **Central star:** resolution / verified outcome.

The shield is intentionally open rather than a conventional financial-security badge. The opening communicates a remaining window to act before the deadline.

## 4. Logo system

### Primary lockup
Shield Constellation + `Nick of Time` wordmark.

### Symbol
Shield Constellation alone. Use for avatars, app icons, favicon, compact UI, and social profiles.

### Variants
- Horizontal primary
- Vertical secondary
- Symbol only
- Monochrome light
- Monochrome dark
- Micro symbol for 16 / 24 / 32 px

## 5. Logo rules

### Clear space
Keep clear space on every side equal to **1× the symbol width (X)** unless a specific product surface requires a tighter system constraint.

### Minimum size
- Symbol: **16 px** minimum for digital use.
- At 16 px, use the simplified micro symbol.
- Do not use the full wordmark at icon scale.

### Do
- Use official brand colors.
- Preserve proportions.
- Preserve the constellation geometry.
- Use approved dark or light backgrounds.
- Use monochrome when color reproduction is unavailable.

### Don't
- Stretch or distort.
- Rotate the symbol.
- Change brand colors arbitrarily.
- Add glow, drop shadows, bevels, or 3D effects.
- Put text inside the symbol.
- Place the mark on low-contrast backgrounds.
- Substitute arbitrary typefaces in the lockup.

## 6. Color system

| Token | Hex | Meaning | Primary use |
|---|---|---|---|
| Violet | `#7C3AED` | Intelligence / system | Primary identity |
| Teal | `#0F766E` | Trust / verification | Secondary identity |
| Amber | `#D97706` | Urgency / intervention | Deadline and attention |
| Space | `#080812` | Dark foundation | Dark-mode background |
| Surface | `#111827` | Product surface | Cards / panels |
| Slate | `#94A3B8` | Secondary text | Supporting text |
| White | `#FFFFFF` | Primary light text | Light backgrounds / dark UI text |

**Color rule:** Violet + teal define the identity. Amber is a signal color and should remain restrained.

**Chart series:** `#0d9488` is allowed for chart series only, because the brand teal `#0F766E` falls below the chroma floor of the palette check on the light surface (0.086, it reads gray next to violet). Identity, text and UI keep `#0F766E`.

## 7. Typography

**Primary typeface:** Sora

- Display / Headlines: Sora Bold
- Subheadings: Sora Semibold
- Body: Sora Regular
- Data / labels: Sora Medium
- Optional technical mono: JetBrains Mono

For the wordmark, use the approved logo asset rather than re-typesetting the name.

## 8. Constellation language

The constellation is a reusable visual system, not decoration.

- Nodes represent signals, evidence, events, or states.
- Connections represent traceability.
- The central star represents a verified resolution.
- Open arcs represent a remaining window or an incomplete state.
- Amber can mark urgency or intervention.

Keep the geometry sparse. Prefer a few intentional nodes over dense star fields.

## 9. Product avatars

### Telegram Bot Avatar
Use the symbol-only mark. Keep it compact, centered, and highly recognizable at small sizes.

### Customer Chat Agent Avatar
Use the same symbol master. Do not create a face, robot, human likeness, or separate mascot.

### Verified State Avatar
Use the same symbol with a small, explicit verification-state treatment. The state cue must not alter the underlying logo geometry.

## 10. Dark-mode direction

Dark mode is the primary brand environment.

Use `#080812` as the foundation with Violet and Teal carrying most of the visual identity. Avoid excessive neon glow; the mark should remain legible and professional even when effects are removed.

## 11. Voice

The voice is:

**Clear. Calm. Precise. Transparent.**

Prefer concrete status language over marketing language.

Examples:

- `Card blocked.`
- `Action verified.`
- `Case opened.`
- `Deadline: October 14.`
- `A human analyst will make the final decision.`

Avoid vague AI claims such as “revolutionary,” “seamless,” or “cutting-edge.”

## 12. Asset manifest

### SVG
- `logo-primary-dark.svg`
- `logo-primary-light.svg`
- `logo-horizontal.svg`
- `logo-horizontal-light.svg`
- `logo-vertical.svg`
- `logo-vertical-light.svg`
- `logo-symbol.svg`
- `logo-symbol-micro.svg`
- `logo-symbol-mono.svg`
- `logo-symbol-mono-dark.svg`

### PNG
- Primary / horizontal / vertical exports
- Symbol exports
- Favicon: 16, 24, 32, 48, 64, 128, 256 px
- Telegram bot avatar: 1024 px
- Chat agent avatar: 1024 px
- Verified-state avatar: 1024 px

## 13. Source of truth

The SVG logo assets are the source of truth. Do not redraw the mark from screenshots or generated mockups.

The brand board images are reference material only; implementation should use the SVG assets and this specification.
