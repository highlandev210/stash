import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { FileWatcher } from "@/features/FileWatcher";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows saved file changes separately and enables the watcher through the API", async () => {
  let enabled = false;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === "PUT")
      enabled = JSON.parse(String(options.body)).enabled;
    const data = url.endsWith("file-observations")
      ? [
          {
            id: "change",
            observed_at: "2026-10-03T10:00:00Z",
            added: [],
            modified: ["src/main.ts"],
            removed: [],
            complete: true,
            warnings: [],
          },
        ]
      : { enabled, checked_at: null, complete: null, warnings: [] };
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetch);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <FileWatcher
        projectId="project"
        actor={{ name: "Owner", kind: "human" }}
      />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByText("src/main.ts", { exact: false }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/not task completion or verification/),
  ).toBeInTheDocument();
  fireEvent.click(
    await screen.findByRole("button", { name: "Enable watcher" }),
  );
  expect(
    await screen.findByRole("button", { name: "Disable watcher" }),
  ).toBeInTheDocument();
  const mutation = fetch.mock.calls.find(
    ([, options]) => options?.method === "PUT",
  );
  expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({
    enabled: true,
    actor: { name: "Owner", kind: "human" },
  });
});
