import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, forward API calls to FastAPI (uvicorn api:app --reload).
const API = "http://127.0.0.1:8000";
const apiPaths = ["/chat", "/api", "/approvals", "/threads", "/config", "/health"];

export default defineConfig({
  plugins: [react()],
  server: { proxy: Object.fromEntries(apiPaths.map((p) => [p, API])) },
  // `npm run build` writes the finished site into ../public, which FastAPI and Vercel serve.
  build: { outDir: "../public", emptyOutDir: true },
});
