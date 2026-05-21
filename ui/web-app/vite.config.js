import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

const API_BASE = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010';

export default defineConfig({
  plugins: [preact()],
  server: {
    port: 5174,
    proxy: {
      '/api': { target: API_BASE, changeOrigin: true, secure: false },
      '/auth': { target: API_BASE, changeOrigin: true, secure: false },
      '/v1': { target: API_BASE, changeOrigin: true, secure: false },
      // /health is root-level on the backend (the footer status check hits it).
      // Without this, local dev shows a false "Unable to reach api"; prod is
      // same-origin so it resolves there.
      '/health': { target: API_BASE, changeOrigin: true, secure: false },
      // /extension/* are root-level backend endpoints the workspace also uses
      // (e.g. Records reads /extension/worklist). Same-origin in prod.
      '/extension': { target: API_BASE, changeOrigin: true, secure: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'es2022',
  },
  test: {
    environment: 'happy-dom',
    globals: true,
  },
});
