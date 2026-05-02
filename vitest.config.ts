import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: false,
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    exclude: ["e2e/**", "e2e-test/**", "node_modules/**", ".next/**"],
    cache: false,
  },
});
