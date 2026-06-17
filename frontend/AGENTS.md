<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Agent guide — Voyager frontend

## What this app is

The Voyager frontend is a Next.js 16 / React 19 app for an AI travel companion. It talks to the FastAPI backend at `http://localhost:8000` (or `NEXT_PUBLIC_API_URL`).

## Stack

- **Next.js 16** (App Router) with TypeScript
- **React 19**
- **Chakra UI v3** for components
- **Tailwind CSS v4** for utility styles
- **Framer Motion** for animation

## Dev commands

```bash
npm run dev     # start dev server on :3000
npm run build   # production build
npm run lint    # ESLint
```

## Project structure

```
src/
├── app/
│   ├── (app)/              # Authenticated shell (sidebar layout)
│   │   ├── layout.tsx      # Sidebar + content wrapper
│   │   ├── chat/page.tsx
│   │   ├── trips/page.tsx
│   │   ├── journal/page.tsx
│   │   ├── memories/page.tsx
│   │   └── settings/page.tsx
│   ├── layout.tsx          # Root layout (providers, fonts)
│   ├── page.tsx            # Landing / redirect
│   └── globals.css
├── components/
│   ├── providers.tsx       # Chakra + any other context providers
│   └── sidebar.tsx         # Nav sidebar
└── lib/
    └── api.ts              # Typed fetch wrappers for the backend API
```

## Conventions

- All backend calls go through `src/lib/api.ts`. Add new typed fetch functions there; don't call `fetch` directly in components.
- Use the App Router — no `pages/` directory. Route segments live under `src/app/`.
- The `(app)` route group applies the sidebar layout to authenticated pages. New pages that belong inside the shell go there.
- Chakra UI v3 has a different API than v2 — component props and theming changed. Check `node_modules/@chakra-ui/react` types before assuming an old API still works.
- Tailwind v4 uses a CSS-first config (`globals.css`), not `tailwind.config.js`.
- Keep client components minimal: only add `"use client"` where interactivity or browser APIs are actually needed.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL |

Set in `.env.local` (already gitignored).

## Phased roadmap (don't build ahead)

| Month | What's being added |
|-------|--------------------|
| 1 (now) | Chat UI, trips list, basic layout |
| 2 | Memory display, preference UI |
| 3 | Journal ingestion UI |
| 4 | Multi-agent progress / streaming UI |
| 5 | Evaluation dashboards |
| 6 | Auth (Clerk or Auth.js), production deploy to Vercel |

Auth is not wired up yet — don't add auth middleware or protected routes until Month 6.

