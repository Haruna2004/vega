/**
 * MEND edge API (Cloudflare Worker, free tier).
 *
 * - Serves the frontend (static assets, SPA fallback).
 * - Serves run results straight from R2 (JSON, video with Range, images, docs),
 *   so browsing never wakes the processing engine.
 * - Accepts large uploads into R2 with multipart (parts < 100 MB).
 * - Proxies everything else under /api to the engine on Google Cloud Run.
 * - /internal/r2/* lets the engine read/write R2 with a shared secret.
 */
export interface Env {
  ASSETS: Fetcher;
  BUCKET: R2Bucket;
  ENGINE_URL: string;
  ENGINE_KEY: string;
}

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*" } });

const TYPES: Record<string, string> = { json: "application/json", mp4: "video/mp4", webm: "video/webm", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", html: "text/html; charset=utf-8", md: "text/markdown; charset=utf-8", pdf: "application/pdf", csv: "text/csv", svg: "image/svg+xml" };
const typeOf = (key: string) => TYPES[key.split(".").pop()!.toLowerCase()] ?? "application/octet-stream";

async function serveObject(env: Env, req: Request, key: string): Promise<Response> {
  const range = req.headers.get("range");
  let r2range: R2Range | undefined;
  const m = range && /bytes=(\d*)-(\d*)/.exec(range);
  if (m) {
    const head = await env.BUCKET.head(key);
    if (!head) return json({ detail: "not found" }, 404);
    const size = head.size;
    const start = m[1] ? +m[1] : size - +m[2];
    const end = m[1] && m[2] ? Math.min(+m[2], size - 1) : size - 1;
    r2range = { offset: start, length: end - start + 1 };
    const obj = await env.BUCKET.get(key, { range: r2range });
    if (!obj) return json({ detail: "not found" }, 404);
    return new Response(obj.body, { status: 206, headers: { "content-type": typeOf(key), "content-range": `bytes ${start}-${end}/${size}`, "accept-ranges": "bytes", "content-length": String(end - start + 1), "cache-control": "public, max-age=60" } });
  }
  const obj = await env.BUCKET.get(key);
  if (!obj) return json({ detail: "not found" }, 404);
  return new Response(obj.body, { headers: { "content-type": typeOf(key), "accept-ranges": "bytes", "content-length": String(obj.size), "cache-control": key.endsWith(".json") ? "no-cache" : "public, max-age=60", etag: obj.httpEtag } });
}

async function proxy(env: Env, req: Request, url: URL): Promise<Response> {
  if (!env.ENGINE_URL) return json({ detail: "processing engine is not deployed" }, 503);
  const target = env.ENGINE_URL.replace(/\/$/, "") + url.pathname + url.search;
  const headers = new Headers(req.headers);
  headers.set("x-mend-key", env.ENGINE_KEY);
  headers.delete("host");
  return fetch(target, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body, redirect: "manual" });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const p = url.pathname;
    if (req.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": "*", "access-control-allow-methods": "*", "access-control-allow-headers": "*" } });

    // ---- engine <-> R2 (shared secret) ----
    if (p.startsWith("/internal/")) {
      if (req.headers.get("x-mend-key") !== env.ENGINE_KEY || !env.ENGINE_KEY) return json({ detail: "forbidden" }, 403);
      if (p === "/internal/list") {
        const prefix = url.searchParams.get("prefix") ?? "";
        const out: { key: string; size: number }[] = [];
        let cursor: string | undefined;
        do {
          const l = await env.BUCKET.list({ prefix, cursor, limit: 1000 });
          out.push(...l.objects.map((o) => ({ key: o.key, size: o.size })));
          cursor = l.truncated ? l.cursor : undefined;
        } while (cursor);
        return json(out);
      }
      const key = decodeURIComponent(p.slice("/internal/r2/".length));
      if (req.method === "PUT") { await env.BUCKET.put(key, req.body, { httpMetadata: { contentType: typeOf(key) } }); return json({ ok: true }); }
      if (req.method === "DELETE") { await env.BUCKET.delete(key); return json({ ok: true }); }
      return serveObject(env, req, key);
    }

    // public downloads (e.g. the rendered demo video): R2 prefix downloads/
    if ((req.method === "GET" || req.method === "HEAD") && p.startsWith("/download/")) {
      const name = decodeURIComponent(p.slice("/download/".length));
      const res = await serveObject(env, req, `downloads/${name}`);
      if (!url.searchParams.has("dl") || !res.ok) return res;
      // ?dl=1: ask the browser to save the file instead of playing it (iOS Chrome / Safari "Save to Files")
      const h = new Headers(res.headers);
      h.set("content-disposition", `attachment; filename="${name.replace(/"/g, "")}"`);
      return new Response(res.body, { status: res.status, headers: h });
    }

    if (!p.startsWith("/api/")) return env.ASSETS.fetch(req);

    // ---- read-only results straight from R2 ----
    let m: RegExpExecArray | null;
    if (req.method === "GET" && (m = /^\/api\/runs\/([^/]+)\/files\/(.+)$/.exec(p))) return serveObject(env, req, `runs/${m[1]}/${decodeURIComponent(m[2])}`);
    if (req.method === "GET" && (m = /^\/api\/runs\/([^/]+)\/data\/([a-z_0-9]+)$/.exec(p))) return serveObject(env, req, `runs/${m[1]}/${m[2]}.json`);
    if (req.method === "GET" && p === "/api/runs") {
      const obj = await env.BUCKET.get("index.json");
      return obj ? new Response(obj.body, { headers: { "content-type": "application/json" } }) : json([]);
    }
    if (req.method === "GET" && (m = /^\/api\/runs\/([^/]+)$/.exec(p))) {
      const [meta, summary] = await Promise.all([env.BUCKET.get(`runs/${m[1]}/run.json`), env.BUCKET.get(`runs/${m[1]}/summary.json`)]);
      if (!meta) return json({ detail: "not found" }, 404);
      const run: any = await meta.json();
      run.summary = summary ? await summary.json() : {};
      run.running = run.status === "running";
      return json(run);
    }
    if (req.method === "GET" && p === "/api/config") {
      const obj = await env.BUCKET.get("config.json");
      if (obj) return new Response(obj.body, { headers: { "content-type": "application/json" } });
    }

    // ---- multipart uploads into R2 (each part < 100 MB) ----
    if ((m = /^\/api\/uploads\/(.+)$/.exec(p))) {
      const key = `uploads/${decodeURIComponent(m[1])}`;
      const action = url.searchParams.get("action");
      if (req.method === "POST" && action === "create") { const u = await env.BUCKET.createMultipartUpload(key, { httpMetadata: { contentType: typeOf(key) } }); return json({ uploadId: u.uploadId, key }); }
      if (req.method === "PUT" && action === "part") {
        const u = env.BUCKET.resumeMultipartUpload(key, url.searchParams.get("uploadId")!);
        const part = await u.uploadPart(+url.searchParams.get("part")!, req.body!);
        return json(part);
      }
      if (req.method === "POST" && action === "complete") {
        const { uploadId, parts } = (await req.json()) as any;
        const obj = await env.BUCKET.resumeMultipartUpload(key, uploadId).complete(parts);
        return json({ key, size: obj.size });
      }
      return json({ detail: "bad upload request" }, 400);
    }

    // ---- everything else: the engine on Cloud Run ----
    return proxy(env, req, url);
  },
};
