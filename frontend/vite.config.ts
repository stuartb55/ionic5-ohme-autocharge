import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { scheduleFixture, sessionsFixture, statisticsFixture, statusFixture } from './src/test/fixtures';

// The backend API base. In dev we proxy /api to the FastAPI server so the SPA
// talks to the same relative paths it uses in production (served behind nginx).
const API_TARGET = process.env.VITE_API_PROXY ?? 'http://localhost:8000';

/** Deterministic local API used only to capture representative PWA screenshots. */
function demoApi(): Plugin {
  return {
    name: 'autocharge-demo-api',
    configureServer(server) {
      server.middlewares.use('/api', (request, response, next) => {
        if (process.env.VITE_DEMO_MODE !== '1') return next();
        const path = request.url?.split('?')[0] ?? '';
        const now = Date.now();
        const iso = (offsetMinutes: number) => new Date(now + offsetMinutes * 60_000).toISOString();
        const payloads: Record<string, unknown> = {
          '/status': {
            ...statusFixture,
            updatedAt: iso(-1),
            charger: { ...statusFixture.charger, projectedFinish: iso(170) },
            config: { ...statusFixture.config, readyBy: '06:30', readyByIsManual: true },
          },
          '/schedule': {
            ...scheduleFixture,
            updatedAt: iso(-1),
            nextSlotStart: iso(20),
            nextSlotEnd: iso(110),
            slots: [
              { start: iso(20), end: iso(110), power: 7.4, energy: 11.1 },
              { start: iso(140), end: iso(170), power: 7.4, energy: 3.7 },
            ],
          },
          '/statistics': statisticsFixture,
          '/sessions': sessionsFixture,
          '/soh-history': { enabled: false, history: [] },
          '/tariff': { enabled: false, rates: [], cheapest: [] },
          '/energy-usage': { enabled: false, date: null, slots: [], totals: null },
          '/data-quality': {
            status: 'ok', generatedAt: iso(0), persistenceAvailable: false,
            actualCostExpected: false, sessions: null, telemetry: null,
            consumption: null, daily: null, statisticsCache: { available: true, ageSeconds: 30 },
          },
          '/version': { version: 'demo' },
          '/vehicles': {
            vehicles: [{ id: 'demo-car', name: 'IONIQ 5', vin: null, model: 'IONIQ 5' }],
            selected: 'demo-car',
          },
        };
        const payload = payloads[path];
        if (payload === undefined) return next();
        response.statusCode = 200;
        response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify(payload));
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), demoApi()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
