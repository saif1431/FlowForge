import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import Organizations from "../src/components/organizations";
import { ApiError, apiRequest } from "../src/lib/auth-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn(), push: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("../src/lib/auth-api", async (original) => ({
  ...(await original<typeof import("../src/lib/auth-api")>()), apiRequest: vi.fn(),
}));
beforeEach(() => { vi.resetAllMocks(); });

const people = [
  { id: "owner", user_id: "owner", email: "owner@example.com", role_code: "owner" },
  { id: "admin", user_id: "admin", email: "admin@example.com", role_code: "admin" },
  { id: "peer", user_id: "peer", email: "peer@example.com", role_code: "admin" },
  { id: "member", user_id: "member", email: "member@example.com", role_code: "member" },
];
const management = ["directory:read", "organization:update", "invitation:manage", "role:assign", "member:remove", "team:manage", "membership:leave"];

function setup(user = "admin", permissions = management) {
  vi.mocked(apiRequest).mockImplementation(async (path) => {
    if (path === "/auth/me") return { id: user, email_verified_at: "today" };
    if (path === "/organizations/org") return { id: "org", name: "Studio", owner_user_id: "owner" };
    if (path.endsWith("/access")) return { role_code: user, permissions };
    if (path.endsWith("/roles")) return { items: ["owner", "admin", "designer", "approver", "member", "viewer"].map((code) => ({ code, name: code, permissions: [] })) };
    if (path.endsWith("/teams/team/members")) return { items: [people[3]], next_cursor: null };
    if (path.endsWith("/members")) return { items: people, next_cursor: null };
    if (path.endsWith("/teams")) return { items: [{ id: "team", name: "Finance", organization_id: "org" }], next_cursor: null };
    return { items: [], next_cursor: null };
  });
}

test("admin controls use effective permissions and protect Owner, self and peer Admins", async () => {
  setup();
  render(<Organizations orgId="org" />);
  expect(await screen.findByRole("button", { name: "Invite member" })).toBeVisible();
  expect(screen.getByLabelText("Role for member@example.com")).toBeVisible();
  expect(screen.queryByLabelText("Role for owner@example.com")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Role for admin@example.com")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Role for peer@example.com")).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "admin" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Remove member" })).toHaveLength(1);
});

test("Owner assigns Admin through the role endpoint", async () => {
  setup("owner", [...management, "role:assign_admin"]);
  render(<Organizations orgId="org" />);
  const select = await screen.findByLabelText("Role for member@example.com");
  fireEvent.change(select, { target: { value: "admin" } });
  fireEvent.submit(select.closest("form")!);
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/organizations/org/members/member/role", "PATCH", { role_code: "admin" }));
});

test("read-only permissions show the team directory without management controls", async () => {
  setup("viewer", ["directory:read", "membership:leave"]);
  render(<Organizations orgId="org" view="teams" />);
  fireEvent.click(await screen.findByRole("button", { name: "Finance" }));
  expect(await screen.findByText("member@example.com", { exact: true })).toBeVisible();
  for (const name of ["Create team", "Delete team", "Rename team", "Add to team", "Save name", "Invite member"]) {
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  }
});

test("revoked permissions refresh after a rejected role change", async () => {
  setup();
  const original = vi.mocked(apiRequest).getMockImplementation()!;
  let revoked = false;
  vi.mocked(apiRequest).mockImplementation(async (path, method, ...rest) => {
    if (method === "PATCH") { revoked = true; throw new ApiError(403, "Permission revoked."); }
    if (revoked && path.endsWith("/access")) return { role_code: "viewer", permissions: ["directory:read"] };
    return original(path, method, ...rest);
  });
  render(<Organizations orgId="org" />);
  fireEvent.submit((await screen.findByLabelText("Role for member@example.com")).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent("Permission revoked");
  expect(screen.queryByRole("button", { name: "Save role" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Invite member" })).not.toBeInTheDocument();
});
