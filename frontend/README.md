# Autocharge Dashboard (frontend)

Single-page dashboard for the Ohme EV charging scheduler. React 18 + TypeScript +
Vite, no UI framework — a small hand-rolled design system and dependency-free SVG
charts keep the bundle lean (~50 kB gzipped).

## Scripts

```bash
npm install
npm run dev            # Vite dev server (:5173), proxies /api → http://localhost:8000
npm run test           # Vitest: component unit tests + MSW-backed integration test
npm run test:coverage  # with V8 coverage report
npm run lint           # ESLint
npm run build          # tsc --noEmit + vite build → dist/
```

Set `VITE_API_PROXY` to point the dev server at a different backend, or
`VITE_API_BASE` to call an absolute API origin (only needed when the API is not
served from the same origin as the SPA).

## Layout

- `src/api/` — typed fetch client (`client.ts`), response types, and the
  `usePolling` hook that refreshes data on an interval.
- `src/components/` — the three dashboard sections plus reusable pieces
  (`BatteryRing`, `ScheduleTimeline`, `EnergyBarChart`, `ConnectionBadge`).
- `src/utils/` — formatting helpers and the schedule-timeline geometry.
- `src/test/` — MSW request handlers, fixtures, and the end-to-end dashboard test.

## Tests

- **Component tests** render individual components and assert their output and
  accessibility attributes.
- **Integration test** (`src/test/integration/Dashboard.test.tsx`) mounts the whole
  `Dashboard`, mocks all three API endpoints with [MSW](https://mswjs.io), and
  verifies the sections render real data and react to user input (time-range
  switching, error states).
- **Accessibility test** runs axe-core against the fully populated dashboard;
  colour contrast is verified separately in a real browser because the test DOM
  has no paint engine.

## PWA screenshots

The manifest screenshots are captures of the real application using a local,
read-only demo API. Start it with `VITE_DEMO_MODE=1 npm run dev`, then capture
the page at 1280×720 and 720×1280. The demo middleware is enabled only by that
environment variable and is never included in the production client bundle.
`PwaAssets.test.ts` treats the reviewed captures as golden assets; update its
hashes intentionally whenever the screenshots are recaptured.

## Production image

`Dockerfile` is a multi-stage build: a Node stage compiles the static bundle, then
the assets are copied into a non-root `nginx-unprivileged` image listening on
**8080**. `nginx.conf` adds security headers (CSP, `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`), gzip, long-lived
caching for hashed assets, a SPA fallback, and proxies `/api` to the `backend`
service.
