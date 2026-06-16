import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/app/layout.tsx",
        "src/app/favicon.ico",
        "src/**/*.test.{ts,tsx}",
      ],
      thresholds: {
        statements: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
});
