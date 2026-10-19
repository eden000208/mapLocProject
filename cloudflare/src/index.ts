import { Container, ContainerProxy, getContainer } from "@cloudflare/containers";
export { ContainerProxy };

export interface Env {
  BACKEND: DurableObjectNamespace<BsqBackend>;
  ASSETS: Fetcher;
  FILES: R2Bucket;
  DATABASE_NETWORK: { connect(address: { hostname: string; port: number }): Promise<Socket> };
  DATABASE_HOST: string;
  DATABASE_PORT: string;
  MYSQL_USER: string;
  MYSQL_PASSWORD: string;
  TIANDITU_KEY: string;
}

// Only reachable through the Container's outbound interception, never public fetch.
export async function files(request: Request, env: Env): Promise<Response> {
  const key = decodeURIComponent(new URL(request.url).pathname.slice(1));
  if (!/^(imports|detail_uploads|chunks|operations|exports)\/[a-zA-Z0-9_.\/-]+$/.test(key)
      || key.split("/").some(part => part === ".." || part === ".")) {
    return new Response(null, { status: 400 });
  }
  if (request.method === "PUT") {
    await env.FILES.put(key, request.body);
    return new Response(null, { status: 204 });
  }
  if (request.method === "DELETE") {
    await env.FILES.delete(key);
    return new Response(null, { status: 204 });
  }
  if (request.method === "GET") {
    const object = await env.FILES.get(key);
    return object ? new Response(object.body, { headers: { "Cache-Control": "no-store" } })
      : new Response(null, { status: 404 });
  }
  return new Response(null, { status: 405 });
}

export async function database(request: Request, env: Env): Promise<Response> {
  if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
    return new Response(null, { status: 426 });
  }
  // The target is deployment configuration; the caller cannot choose a host.
  const socket = await env.DATABASE_NETWORK.connect({
    hostname: env.DATABASE_HOST, port: Number(env.DATABASE_PORT),
  });
  await socket.opened;
  const pair = new WebSocketPair();
  const client = pair[0], server = pair[1];
  server.accept();
  const writer = socket.writable.getWriter();
  const reader = socket.readable.getReader();
  let pending = Promise.resolve();
  let queuedBytes = 0;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    try { server.close(1000); } catch { /* already closed */ }
    void socket.close().catch(() => {});
  };
  server.addEventListener("message", event => {
    if (typeof event.data === "string" || event.data.byteLength > 65536) { close(); return; }
    const data = event.data;
    queuedBytes += data.byteLength;
    if (queuedBytes > 4 * 1024 * 1024) { close(); return; }
    pending = pending.then(async () => {
      await writer.write(data);
      queuedBytes -= data.byteLength;
    }).catch(close);
  });
  server.addEventListener("close", close);
  server.addEventListener("error", close);
  // Lifetime is attached to the accepted WebSocket, not detached background SQL.
  void (async () => {
    try {
      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;
        for (let offset = 0; offset < value.length; offset += 65536) {
          server.send(value.slice(offset, offset + 65536));
        }
      }
    } catch { /* Do not emit SQL, packets or credentials into logs. */ }
    finally { close(); reader.releaseLock(); }
  })();
  return new Response(null, { status: 101, webSocket: client });
}

export class BsqBackend extends Container<Env> {
  defaultPort = 8000;
  // Longer than the maximum query runtime; one instance preserves process locks.
  sleepAfter = "30m";
  enableInternet = false;
  allowedHosts = ["bsq-files.internal", "bsq-db.internal"];
  envVars = {
    CLOUDFLARE_MODE: "true",
    COOKIE_SECURE: "true",
    DATA_DIR: "/app/data",
    DATASOURCE_PATH: "/app/datasource.yaml",
    MYSQL_HOST: "127.0.0.1",
    MYSQL_PORT: "13306",
    MYSQL_USER: this.env.MYSQL_USER,
    MYSQL_PASSWORD: this.env.MYSQL_PASSWORD,
    APP_DATABASE: "bsq_app",
    MYSQL_BRIDGE_URL: "ws://bsq-db.internal/",
    STORAGE_GATEWAY: "http://bsq-files.internal",
    TIANDITU_KEY: this.env.TIANDITU_KEY || "",
  };
}

// Assign through the SDK setter so ContainerProxy registers these handlers.
BsqBackend.outboundByHost = {
  "bsq-files.internal": (request: Request, env: Env) => files(request, env),
  "bsq-db.internal": (request: Request, env: Env) => database(request, env),
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (path !== "/api" && !path.startsWith("/api/")) {
      return env.ASSETS.fetch(request);
    }
    // Do not expose Container control, outbound gateways, database or R2 objects.
    try {
      const response = await getContainer(env.BACKEND, "bsq-singleton").fetch(request);
      const result = new Response(response.body, response);
      result.headers.set("Cache-Control", "no-store, private");
      result.headers.set("X-Content-Type-Options", "nosniff");
      result.headers.set("Referrer-Policy", "same-origin");
      return result;
    } catch {
      return Response.json({ code: "503", message: "服务暂不可用，请稍后重试" },
        { status: 503, headers: { "Cache-Control": "no-store" } });
    }
  },
} satisfies ExportedHandler<Env>;
