import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "../src/app/page";

test("introduces FlowForge with an accessible main heading", () => {
  render(<Home />);
  expect(screen.getByRole("main")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "FlowForge" })).toBeVisible();
  expect(screen.getByText(/Business workflows, clearly connected/)).toBeVisible();
});
