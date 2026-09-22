import type { Job } from "./types";

export class ApiError extends Error {}

// In dev, Vite proxies /api to localhost:8000 (see vite.config.ts), so this
// stays empty. In production (e.g. Vercel), set VITE_API_BASE_URL to the
// deployed backend's origin, e.g. https://beacon-backend.onrender.com
const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

export async function createAudit(url: string): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/api/audits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getAudit(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/audits/${id}`);
  if (!res.ok) {
    throw new ApiError(`Could not fetch audit status (${res.status})`);
  }
  return res.json();
}

export async function pollAudit(
  id: string,
  onUpdate: (job: Job) => void,
  { intervalMs = 2500, timeoutMs = 6 * 60 * 1000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<Job> {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await getAudit(id);
    onUpdate(job);
    if (job.status === "done" || job.status === "error") return job;
    if (Date.now() - start > timeoutMs) {
      throw new ApiError("Audit is taking longer than expected. Please try again.");
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
