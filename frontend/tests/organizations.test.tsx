import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import Organizations from "../src/components/organizations";
import { ApiError, apiRequest } from "../src/lib/auth-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn(), push: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("../src/lib/auth-api", async (original) => ({
  ...(await original<typeof import("../src/lib/auth-api")>()), apiRequest: vi.fn(),
}));
beforeEach(() => { vi.resetAllMocks(); });

test("requires sign-in without rendering tenant data", async () => {
  vi.mocked(apiRequest).mockRejectedValue(new ApiError(401, "Sign in."));
  render(<Organizations orgId="foreign" />);
  await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
  expect(screen.queryByRole("heading", { name: "Members" })).not.toBeInTheDocument();
});

test("unverified users see the verification requirement and no tenant requests", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ id: "user", email_verified_at: null });
  render(<Organizations />);
  expect(await screen.findByRole("heading", { name: "Verify your email" })).toBeVisible();
  expect(apiRequest).toHaveBeenCalledTimes(1);
});

test("switching tenants discards a late response from the previous tenant", async () => {
  let resolveOld: (value: unknown) => void = () => {};
  const delayed = new Promise((resolve) => { resolveOld = resolve; });
  vi.mocked(apiRequest).mockImplementation(async (path) => {
    if (path === "/auth/me") return { id: "user", email_verified_at: "today" };
    if (path === "/organizations") return { items: [], next_cursor: null };
    if (path === "/organizations/a") return delayed;
    if (path === "/organizations/b") throw new ApiError(404, "Organization not found.");
    return { items: [], next_cursor: null };
  });
  const { rerender } = render(<Organizations key="a" orgId="a" />);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/organizations/a"));
  rerender(<Organizations key="b" orgId="b" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("not found");
  resolveOld({ id: "a", name: "Private old tenant", owner_user_id: "user" });
  await waitFor(() => expect(screen.queryByText("Private old tenant")).not.toBeInTheDocument());
});
