import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** Typed API client. All paths are same-origin (`/api/...`); Vite proxies them in dev. */
export const api = createClient<paths>({
  baseUrl: "",
  // Resolve fetch per call (not at import time) so the dev mock API can intercept it.
  fetch: (request: Request) => globalThis.fetch(request),
});

/** An HTTP error with a human-readable message and, for 422s, per-field problems. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly problems: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Turn a FastAPI error body (`{detail: string}` or `{detail: ValidationError[]}`) into an ApiError. */
export function toApiError(status: number, body: unknown): ApiError {
  const detail = isRecord(body) ? body.detail : undefined;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const problems = detail.map((item: unknown) => {
      if (!isRecord(item)) return String(item);
      const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
      const msg = typeof item.msg === "string" ? item.msg : "invalid";
      return loc ? `${loc}: ${msg}` : msg;
    });
    return new ApiError(status, "The request was rejected by validation.", problems);
  }
  return new ApiError(status, `Request failed (HTTP ${status}).`);
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Unwrap an openapi-fetch result, throwing an ApiError on any non-2xx response. */
export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok) throw toApiError(response.status, error);
  return data as T;
}

/** Like `unwrap`, but maps a 404 to `null` (used for "not computed yet" resources). */
export async function unwrapOrNull<T>(promise: Promise<FetchResult<T>>): Promise<T | null> {
  const { data, error, response } = await promise;
  if (response.status === 404) return null;
  if (!response.ok) throw toApiError(response.status, error);
  return data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
