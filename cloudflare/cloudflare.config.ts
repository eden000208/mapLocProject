import { bindings, defineConfig, defineContainer, exports } from "cf/config";

const backend = defineContainer({
  name: "bsq-backend",
  image: { dockerfile: "../deploy/Dockerfile.cloudflare", buildContext: ".." },
  instanceType: "standard-1",
  maxInstances: 1,
  observability: { enabled: false, logs: { enabled: false } },
});

export default defineConfig({
  containers: [backend],
  worker: {
    name: "bsq-map",
    entrypoint: "./src/index.ts",
    compatibilityDate: "2026-10-19",
    compatibilityFlags: ["nodejs_compat"],
    exports: {
      // Platform-required Container control metadata only; application data is MySQL/R2.
      BsqBackend: exports.durableObject({ storage: "sqlite", container: backend }),
      ContainerProxy: exports.worker(),
    },
    env: {
      BACKEND: bindings.durableObject({ worker: "bsq-map", exportName: "BsqBackend" }),
      ASSETS: bindings.assets(),
      FILES: bindings.r2({ name: "bsq-files" }),
      DATABASE_NETWORK: bindings.vpcNetwork({ tunnelId: "23e4618c-cc45-4214-8a3c-81d403297881" }),
      DATABASE_HOST: bindings.text("10.44.225.184"),
      DATABASE_PORT: bindings.text("3306"),
      MYSQL_USER: bindings.secret(),
      MYSQL_PASSWORD: bindings.secret(),
      TIANDITU_KEY: bindings.secret(),
    },
    assets: { notFoundHandling: "single-page-application", runWorkerFirst: ["/api", "/api/*"] },
    observability: {
      enabled: true,
      logs: { enabled: true, invocationLogs: false },
      traces: { enabled: true },
    },
  },
});
