import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { tsconfigPaths: true },
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
