import { defineConfig } from "vite";

// Relative base: a Tauri shell loads the bundle from a file:// URL, where an
// absolute "/assets/..." resolves to the filesystem root and every asset 404s.
export default defineConfig({
  base: "./",
  build: { outDir: "dist", emptyOutDir: true, target: "es2022" },
  server: { port: 5173, strictPort: true },
});
