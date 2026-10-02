export default async function teardown() {
  // Graceful shutdown lets the test backend remove its schema even on Windows.
  await fetch("http://127.0.0.1:8100/__test__/shutdown", { method: "POST" });
  for (let attempt = 0; attempt < 20; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    try {
      await fetch("http://127.0.0.1:8100/health/live");
    } catch {
      return;
    }
  }
  throw new Error("The browser-test backend did not shut down cleanly.");
}
