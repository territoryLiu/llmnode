import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:4000';
  const proxyApiKey = env.VITE_API_PROXY_KEY || '';

  function proxyHeaders() {
    return proxyApiKey ? {'x-api-key': proxyApiKey} : {};
  }

  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      css: true,
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: {
        '/admin': {
          target: proxyTarget,
          changeOrigin: true,
          headers: proxyHeaders(),
        },
        '/health': {
          target: proxyTarget,
          changeOrigin: true,
          headers: proxyHeaders(),
        },
        '/v1': {
          target: proxyTarget,
          changeOrigin: true,
          headers: proxyHeaders(),
        },
      },
    },
  };
});
