import { defineConfig } from "vite";
import { readFileSync } from "node:fs";
import { URL as NodeURL } from "node:url";
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({
  plugins: [cloudflare({
    experimental: { newConfig: { cfBuildOutput: true, types: { generate: false } } },
  }), {
    name: "bsq-vue-html",
    transformIndexHtml() {
      return readFileSync(new NodeURL("../frontend/dist/index.html", import.meta.url), "utf8");
    },
  }],
  // Built Vue files are copied here before the Worker build.
  publicDir: "../frontend/dist",
  build: { sourcemap: false },
});
