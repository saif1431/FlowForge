import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import AuthForm from "../src/components/auth-form";
import AccountPage from "../src/app/account/page";
import { ApiError, authRequest } from "../src/lib/auth-api";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
const { replace } = router;
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("../src/lib/auth-api", async (original) => ({
  ...(await original<typeof import("../src/lib/auth-api")>()),
  authRequest: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
});

test("login displays a server error and allows retry without navigating", async () => {
  vi.mocked(authRequest).mockRejectedValueOnce(new ApiError(401, "Email or password is incorrect."));
  render(<AuthForm mode="login" />);
  fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "alice@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a long test password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  expect(replace).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});

test("successful login navigates to the protected account", async () => {
  vi.mocked(authRequest).mockResolvedValueOnce({ email: "alice@example.com" });
  render(<AuthForm mode="login" />);
  fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/account"));
});

test("verification uses the fragment token only after explicit submission", async () => {
  const token = "a".repeat(43);
  window.history.replaceState(null, "", `/verify-email#token=${token}`);
  vi.mocked(authRequest).mockResolvedValueOnce({ message: "Email verified." });
  render(<StrictMode><AuthForm mode="verify-email" /></StrictMode>);
  await waitFor(() => expect(window.location.hash).toBe(""));
  expect(authRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Verify email" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Email verified.");
  expect(authRequest).toHaveBeenCalledWith("/verify-email", "POST", { token });
});

test("unauthenticated account redirects without exposing account content", async () => {
  vi.mocked(authRequest).mockRejectedValue(new ApiError(401, "Sign in to continue."));
  render(<AccountPage />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  expect(screen.queryByRole("heading", { name: "Your account" })).not.toBeInTheDocument();
});
