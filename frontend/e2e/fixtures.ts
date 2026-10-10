import { test as base, expect } from "@playwright/test";

export { expect };

// The harness runs one worker. Each scenario exercises the real limits with
// fresh counters instead of inheriting earlier scenarios' loopback traffic.
export const test = base.extend<{ isolatedRateLimits: void }>({
  isolatedRateLimits: [async ({ request }, use) => {
    const reset = await request.post("http://127.0.0.1:8100/__test__/reset-rate-limits");
    expect(reset.status()).toBe(204);
    await use();
  }, { auto: true }],
});
