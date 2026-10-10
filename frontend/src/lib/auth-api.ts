import type { components } from "./api-schema";

export type User = components["schemas"]["UserOutput"];
export type SessionList = components["schemas"]["SessionList"];
export type Message = components["schemas"]["Message"];

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function requestBase(): string {
  // Local browsers use Next's API proxy so cookies stay on the current host.
  // localhost and 127.0.0.1 are different cookie sites; CORS alone cannot fix that.
  const loopback = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (typeof window !== "undefined" && loopback.has(window.location.hostname)
      && loopback.has(new URL(apiBase, window.location.origin).hostname)) return "";
  return apiBase;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "", public details: Record<string, unknown> = {}) {
    super(message);
  }
}

export async function authRequest<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  return apiRequest<T>(`/auth${path}`, method, body);
}

export async function apiRequest<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${requestBase()}/api/v1${path}`, {
      signal,
      method,
      credentials: "include",
      cache: "no-store",
      headers: {
        ...(method === "GET" ? {} : { "X-CSRF-Protection": "1" }),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Unable to connect. Check your connection and try again.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data?.error?.message ?? "Something went wrong. Please try again.", data?.error?.code, data?.error?.details);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
