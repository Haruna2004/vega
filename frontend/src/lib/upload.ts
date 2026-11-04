import { API, send } from "./api";

const PART = 50 * 1024 * 1024; // < 100 MB Worker body limit

/** Multipart upload into storage (R2 in production, local disk in dev). Returns the storage key. */
export async function uploadFile(file: Blob, name: string, onProgress?: (f: number) => void): Promise<string> {
  const path = `${crypto.randomUUID().slice(0, 8)}/${name.replace(/[^\w.\-]+/g, "_")}`;
  const { uploadId, key } = await send(`/api/uploads/${path}?action=create`, "POST");
  const parts: { partNumber: number; etag: string }[] = [];
  const n = Math.max(1, Math.ceil(file.size / PART));
  for (let i = 0; i < n; i++) {
    const r = await fetch(`${API}/api/uploads/${path}?action=part&uploadId=${uploadId}&part=${i + 1}`, { method: "PUT", body: file.slice(i * PART, (i + 1) * PART) });
    if (!r.ok) throw new Error(`upload failed: ${r.status}`);
    parts.push(await r.json());
    onProgress?.((i + 1) / n);
  }
  await send(`/api/uploads/${path}?action=complete`, "POST", { uploadId, parts });
  return key;
}

export async function startRun(files: { blob: Blob; name: string }[], opts: Record<string, any>, onProgress?: (f: number) => void): Promise<string> {
  const keys: string[] = [];
  for (let i = 0; i < files.length; i++) keys.push(await uploadFile(files[i].blob, files[i].name, (f) => onProgress?.((i + f) / files.length)));
  const r = await send("/api/runs/from-uploads", "POST", { keys, ...opts });
  return r.id;
}
