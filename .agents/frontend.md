# Frontend — Next.js app

Next.js 16 (App Router) / React 19 / TypeScript / Chakra UI v3 / Tailwind v4 / Framer Motion. Lives in `frontend/`. Talks to the backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8060`; set in `.env.local`).

> Next.js 16 and Chakra v3 differ from training data — check `node_modules/next/dist/docs/` and Chakra types before assuming old APIs.

## Structure

```
frontend/src/
├── app/
│   ├── (app)/            # Sidebar shell — all product pages live here
│   │   ├── chat/  chats/  chats/[id]/     # chat UI (SSE streaming)
│   │   ├── trips/  trips/[id]/            # trip cards + detail (Itinerary/Journal/Places tabs)
│   │   ├── memories/  usage/  settings/
│   │   └── layout.tsx
│   ├── layout.tsx        # Root layout (providers, fonts)
│   └── page.tsx          # Landing / redirect
├── components/           # providers.tsx, sidebar.tsx, theme-switcher.tsx
└── lib/
    ├── api.ts            # ALL backend calls — typed fetch wrappers; never fetch directly in components
    └── theme.ts / theme-context.tsx
```

## Conventions

- Backend calls only through `src/lib/api.ts`.
- New in-shell pages go under `(app)/`.
- Minimal `"use client"` — only where interactivity or browser APIs are needed.
- Tailwind v4 is CSS-first (`globals.css`), no `tailwind.config.js`.
- **Theme switching (Chakra v3):** use `.dark`/`.light` class names on `<html>` (not `data-theme`), with `_light`/`_dark` conditions in semanticTokens.
- Chat pages consume the backend SSE stream: token/step events render live progress (planning-graph node labels appear as steps).

## Commands & tests

```bash
npm run dev      # :3000
npm run build
npm run lint
npm run test     # vitest (src/tests/)
npx playwright test   # e2e/smoke.spec.ts
```

No auth yet — don't add auth middleware or protected routes until Month 6.
