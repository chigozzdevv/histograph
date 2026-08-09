# Histograph client

The Histograph marketing client is a standalone Next.js App Router application styled with
Tailwind CSS v4.

## Development

```bash
npm install
npm run dev
```

The app runs at `http://localhost:3000` by default.

## Structure

```text
src/
├── app/          # Routes, metadata, and global design tokens
├── components/
│   ├── brand/    # Histograph brand primitives
│   ├── incident/ # Product-story visuals
│   ├── layout/   # Shared page chrome
│   └── sections/ # Landing-page sections such as hero.tsx
└── content/      # Typed landing-page copy and navigation
```

Folders provide the component context, so files use concise names such as `sections/hero.tsx`
instead of repeating that context in names such as `hero-section.tsx`.
