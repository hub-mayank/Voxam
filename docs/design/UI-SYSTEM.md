# Voxam UI system

Voxam uses a warm paper-and-ink palette to make oral assessment feel clear and measured. Deep teal is reserved for primary actions, current progress, links, and score indicators. Success, warning, failure, and pending colors appear only where they explain a state. The dark theme has its own surface, border, text, and semantic values; it does not invert the light palette. Light mode is the default, and the header toggle saves the choice in local storage.

## Design decisions

- **Quiet institutional tone:** warm neutrals and hairline borders keep the interface calm. No gradients, glow effects, decorative emoji, glass surfaces, or oversized pill controls.
- **Academic hierarchy:** serif page titles distinguish the task at hand; a system sans stack keeps labels, forms, and tables highly readable without a remote font dependency. Timers and scores use tabular numerals.
- **Different density for different work:** student pages stay centered and comfortable to read; faculty pages can use a wider canvas and compact tables. On narrow screens, data rows become labeled cards and the student stepper becomes a vertical list.

## Tokens

The tokens live in `frontend/src/shared/styles.css` under `:root` and `:root[data-theme="dark"]`.

| Token group | Light theme | Dark theme | Use |
| --- | --- | --- | --- |
| Surfaces | `--bg`, `--surface`, `--surface-sunken` | Re-tuned charcoal values | Page, cards, controls, table headers |
| Lines | `--border`, `--border-strong` | Re-tuned charcoal borders | Section dividers and control outlines |
| Text | `--text`, `--muted`, `--faint` | Re-tuned light ink | Content, supporting copy, placeholders |
| Accent | `--accent: #1f5c5a`, `--accent-hover`, `--accent-subtle` | `--accent: #3f8582`, `--accent-hover`, `--accent-subtle` | Main actions and active states |
| Semantic | `--good`, `--warn`, `--bad`, `--pending` plus `*-bg` | Individually tuned values | Released, review, failed, and waiting states |
| Focus | `--focus-ring` | `--focus-ring` | Keyboard focus indication |
| Shape and space | `--radius: 7px`, `--gap: 16px` | Shared | Compact corners and 8px-based spacing |

## Component principles

The existing shared React components are the base library: `Button`, `Page`, `Table`, `Badge`, `Modal`, and `ErrorBanner`. Shared styles define field states, badges, empty states, responsive tables, keyboard focus, and loading skeletons. Components use semantic HTML and real labels. Visual state changes are brief, and reduced-motion preferences disable animated transitions.

The product shell contains a small Voxam mark, a context label, a persistent theme toggle, and an authenticated faculty sign-out action. Student pages use a four-step progress indicator. Faculty tables retain their column labels when converted to stacked rows on mobile. Privacy information is available from the footer.

## Accessibility and responsive behavior

Controls have visible focus rings and at least 42px height; student actions and fields meet the 44px touch target. The page stays usable at 360px, tablet, and desktop widths. Faculty tables become labeled row cards under 700px. Status is conveyed through text as well as color, and the theme toggle exposes its next action in its accessible name. `prefers-reduced-motion` suppresses nonessential motion.
