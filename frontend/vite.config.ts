import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  resolve: {
    conditions: ['browser']
  },
  server: {
    host: "127.0.0.1",
    port: 32016,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:62018'
    }
  },
  preview: {
    host: "127.0.0.1",
    port: 32016,
    strictPort: true
  }
});