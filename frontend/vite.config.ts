import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The backend API base. In dev we proxy /api to the FastAPI server so the SPA
// talks to the same relative paths it uses in production (served behind nginx).
const API_TARGET = process.env.VITE_API_PROXY ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
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
