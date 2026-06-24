import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendEnvPath = path.resolve(__dirname, '../backend/.env');

/** Read a key from backend/.env — single source of truth for dev ports. */
function readBackendEnv(key, fallback) {
  try {
    const text = fs.readFileSync(backendEnvPath, 'utf8');
    for (const line of text.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const k = trimmed.slice(0, eq).trim();
      if (k !== key) continue;
      return trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
    }
  } catch {
    /* backend/.env optional at build time */
  }
  return fallback;
}

const bindHost = readBackendEnv('NEXUS_BIND_HOST', '127.0.0.1');
const backendPort = Number(readBackendEnv('NEXUS_PORT', '8002'));
const frontendPort = Number(readBackendEnv('NEXUS_FRONTEND_PORT', '5175'));

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_NEXUS_BACKEND_PORT': JSON.stringify(String(backendPort)),
    'import.meta.env.VITE_NEXUS_BIND_HOST': JSON.stringify(bindHost),
  },
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: `http://${bindHost}:${backendPort}`,
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
});
