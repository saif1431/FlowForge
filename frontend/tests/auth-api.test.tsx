import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

test.each(["localhost", "127.0.0.1"])("%s uses the local cookie-preserving proxy", async (host) => {
  vi.stubGlobal("window", { location: new URL(`http://${host}:3000`) });
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000");
  const fetch = vi.fn().mockResolvedValue(new Response('{"email":"alice@example.com"}'));
  vi.stubGlobal("fetch", fetch);
  const { authRequest } = await import("../src/lib/auth-api");
  await authRequest("/login", "POST", { email: "alice@example.com", password: "test password" });
  expect(fetch).toHaveBeenCalledWith("/api/v1/auth/login", expect.objectContaining({
    credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Protection": "1" },
  }));
});

test("a remote API keeps its configured destination and exposes duplicate errors", async () => {
  vi.stubGlobal("window", { location: new URL("https://app.example.com") });
  vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: {
    code: "EMAIL_ALREADY_REGISTERED", message: "Account already exists.", details: {},
  } }), { status: 409 }));
  vi.stubGlobal("fetch", fetch);
  const { authRequest } = await import("../src/lib/auth-api");
  await expect(authRequest("/register", "POST", {})).rejects.toMatchObject({
    status: 409, code: "EMAIL_ALREADY_REGISTERED", message: "Account already exists.",
  });
  expect(fetch).toHaveBeenCalledWith("https://api.example.com/api/v1/auth/register", expect.objectContaining({ credentials: "include" }));
});
