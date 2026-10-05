import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, afterEach } from "vitest";
import { SessionResume } from "@/features/SessionResume";

const actor = { name: "Agent", kind: "agent" as const };
const observation = {
  git: true,
  branch: "main",
  head: "abc",
  dirty: true,
  warnings: [],
};
const session = {
  id: "session",
  task: "Implement filtering",
  status: "incomplete",
  revision: "original-hash",
  created_at: "2026-10-03T10:00:00Z",
  actor,
  observation,
};
const checkpoint = {
  id: "checkpoint",
  created_at: "2026-10-03T10:01:00Z",
  actor,
  explanation: {
    progress: "Filter started",
    unfinished_work: "Tests remaining",
    blockers: "",
    verification: "No tests run",
    verification_includes_uncommitted: null,
    next_actions: "Write filtering tests",
    final: false,
  },
  observation,
};
const resume = {
  session,
  checkpoint,
  changes: {
    added: [],
    removed: [],
    modified: ["src/filter.ts"],
    head_changed: false,
    branch_changed: false,
    complete: true,
  },
  current_observation: observation,
  incomplete_sessions: [session],
};
afterEach(() => vi.unstubAllGlobals());
function mount() {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    let data: unknown = url.endsWith("/resume")
      ? resume
      : url.endsWith("/sessions")
        ? [session]
        : { session, checkpoints: [checkpoint] };
    if (init?.method === "POST") data = checkpoint;
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
      <SessionResume
        projectId="project"
        actor={actor}
        refresh={async () => {}}
      />
    </QueryClientProvider>,
  );
  return fetch;
}
describe("Checkpoint recovery", () => {
  it("shows unfinished progress, verification, next action, and changes after checkpoint", async () => {
    mount();
    expect(await screen.findByText("Implement filtering")).toBeVisible();
    expect(
      screen.getByText(/Unfinished session: no final handoff/),
    ).toBeVisible();
    expect(
      screen.getByText("Write filtering tests", { exact: false }),
    ).toBeVisible();
    expect(screen.getByText(/modified: src\/filter.ts/)).toBeVisible();
    expect(screen.getByText(/No tests run/)).toBeVisible();
    fireEvent.click(screen.getByText("Session history"));
    fireEvent.click(
      screen.getByRole("button", {
        name: /Implement filtering · Agent · incomplete/,
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("dialog")).toHaveTextContent("Tests remaining"),
    );
  });
  it("submits checkpoints using the revision captured when opening the editor", async () => {
    const fetch = mount();
    fireEvent.click(
      await screen.findByRole("button", { name: "Save checkpoint" }),
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Next actions"), {
      target: { value: "Run tests" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url, init]) =>
            url.endsWith("/checkpoints") && init?.method === "POST",
        ),
      ).toBe(true),
    );
    const body = JSON.parse(
      String(
        fetch.mock.calls.find(
          ([url, init]) =>
            url.endsWith("/checkpoints") && init?.method === "POST",
        )?.[1]?.body,
      ),
    );
    expect(body.revision).toBe("original-hash");
    expect(body.next_actions).toBe("Run tests");
    expect(body.final).toBe(false);
    expect(body.verification_includes_uncommitted).toBeNull();
  });
});
