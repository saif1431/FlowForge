import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout observer. Canvas layout and drag behavior are covered by
// the real-browser suite; component tests exercise forms and API responses.
vi.stubGlobal("ResizeObserver", class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
});

afterEach(cleanup);
