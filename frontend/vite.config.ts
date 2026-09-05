import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss(), reactRouter()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  resolve: {
    tsconfigPaths: true,
  },
});
