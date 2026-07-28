import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // bb export drops multi-MB overlay videos here mid-session; watching
      // them crashes the dev server on Windows while the copy is in flight.
      ignored: ["**/public/data/**"],
    },
  },
});
