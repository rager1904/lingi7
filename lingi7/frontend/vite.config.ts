import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: true,
    proxy: {
      // Proxy API calls to Django in development — no CORS issues
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/media": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split vendor bundle for better caching
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          state: ["zustand"],
          http: ["axios"],
        },
      },
    },
  },
});
