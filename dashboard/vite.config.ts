import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const port = Number(process.env.FLEETPULSE_API_PORT ?? 8000);
if (!Number.isInteger(port) || port < 1024 || port > 65535)
  throw new Error("Invalid local API port");
const proxy = {
  "/api": { target: `http://127.0.0.1:${port}`, changeOrigin: true },
};
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["recharts"],
          framework: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
    pool: "threads",
    maxWorkers: 1,
    fileParallelism: false,
  },
});
