import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/chat": "http://localhost:8000",
      "/runs": "http://localhost:8000",
      "/sessions": "http://localhost:8000",
      "/artifacts": "http://localhost:8000",
      "/indices": "http://localhost:8000",
      "/market": "http://localhost:8000",
      "/strategy": "http://localhost:8000",
      "/intraday": {
        target: "http://localhost:8000",
        bypass(req) {
          if (req.headers.accept?.includes("text/html")) return "/index.html";
          return undefined;
        },
      },
      "/health": "http://localhost:8000",
    },
  },
});
