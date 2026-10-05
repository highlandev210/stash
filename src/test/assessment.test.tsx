import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Assessment } from "@/features/Assessment";
import type { Project } from "@/lib/api/client";

const project = {
  id: "project",
  name: "Reader app",
  path: "/projects/reader",
  status: "active",
  availability: "available",
  tags: [],
  services: [],
  env_names: [],
  setup_command: "",
  run_command: "",
  test_command: "",
  repo_url: "",
  demo_url: "",
  screenshot: "",
  doc_roots: ["README.md"],
  writable_doc_roots: [],
  revision: "project-revision",
  created_at: "2026-10-05T12:00:00Z",
  tracker_updated_at: "2026-10-05T12:00:00Z",
  code_activity_at: null,
  last_activity_at: "2026-10-05T12:00:00Z",
  activity_source: "tracker",
  last_opened_at: null,
  open_issue_count: 0,
  observations: {},
  purpose: "Human purpose",
  description: "Human description",
  brief: "Human brief",
  stack: [],
  next_step: "",
  focus: "",
} as Project;
const report = {
  id: "assessment",
  revision: "original-revision",
  created_at: "2026-10-05T12:00:00Z",
  mode: "existing",
  goal: "Book organizer",
  requirements: [],
  status: "draft",
  needs_goal: false,
  proposed: {
    description: "Proposed description",
    next_step: "Fix the supported issue",
  },
  warnings: [],
  evidence: [{ path: "main.py", kind: "inspected" }],
  available_checks: ["npm:check"],
  checks: [{ name: "npm:check", status: "not_run", evidence: "package.json" }],
  candidates: [
    {
      id: "candidate",
      title: "Fix syntax",
      description: "Syntax failed",
      evidence: "main.py:1",
      confidence: "observed",
      existing_issue_id: "human-issue",
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount(fetch: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetch);
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Assessment
        project={project}
        actor={{ name: "Ben", kind: "human" }}
        refresh={vi.fn(async () => {})}
      />
    </QueryClientProvider>,
  );
}
function mock(conflict = false) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST" && url.endsWith("/approve"))
      return new Response(
        JSON.stringify(
          conflict
            ? {
                code: "stale_assessment",
                message:
                  "Repository changed since assessment. Reassess before accepting",
              }
            : { status: "accepted" },
        ),
        { status: conflict ? 409 : 200 },
      );
    if (init?.method === "POST") return new Response(JSON.stringify(report));
    return new Response(JSON.stringify([]));
  });
}

describe("project assessment review", () => {
  it("captures goal, preserves human context by default, and links selected findings with original revision", async () => {
    const fetch = mock();
    mount(fetch);
    fireEvent.change(screen.getByLabelText("What should this project do?"), {
      target: { value: "Book organizer" },
    });
    fireEvent.change(screen.getByLabelText(/Requirements and initial tasks/), {
      target: { value: "Add books\nMark as read" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Inspect project" }));
    await screen.findByText("Review context changes");
    const inspectCall = fetch.mock.calls.find(
      ([, init]) => init?.method === "POST",
    );
    expect(JSON.parse(String(inspectCall?.[1]?.body))).toMatchObject({
      goal: "Book organizer",
      requirements: ["Add books", "Mark as read"],
      run_checks: [],
    });
    expect(screen.getByLabelText("description")).not.toBeChecked();
    expect(screen.getByLabelText("next step")).toBeChecked();
    expect(screen.getByText("Current: Human description")).toBeVisible();
    expect(screen.getByText("Link existing issue")).toBeVisible();
    fireEvent.click(screen.getByLabelText(/Fix syntax/));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Accept selected context and issues",
      }),
    );
    await screen.findByRole("status");
    const approval = fetch.mock.calls.find(([url]) => url.endsWith("/approve"));
    expect(JSON.parse(String(approval?.[1]?.body))).toMatchObject({
      revision: "original-revision",
      fields: ["next_step"],
      candidates: ["candidate"],
      enable_watcher: true,
    });
  });

  it("retains a stale draft and never silently refreshes its revision", async () => {
    const fetch = mock(true);
    mount(fetch);
    fireEvent.click(screen.getByRole("button", { name: "Inspect project" }));
    await screen.findByText("Review context changes");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Accept selected context and issues",
      }),
    );
    await screen.findByText(/Repository changed since assessment/);
    expect(screen.getByLabelText("Proposed description")).toHaveValue(
      "Proposed description",
    );
    expect(
      screen.getByRole("button", { name: "Refresh assessment" }),
    ).toBeVisible();
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.endsWith("/approve")),
      ).toHaveLength(1),
    );
  });

  it("runs checks only through an explicit selection and execution action", async () => {
    const fetch = mock();
    mount(fetch);
    fireEvent.click(screen.getByRole("button", { name: "Inspect project" }));
    await screen.findByText("Review context changes");
    expect(
      screen.getByRole("button", { name: "Run selected checks and reassess" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByLabelText("npm:check"));
    fireEvent.click(
      screen.getByRole("button", { name: "Run selected checks and reassess" }),
    );
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
      ).toHaveLength(2),
    );
    const requests = fetch.mock.calls.filter(
      ([, init]) => init?.method === "POST",
    );
    expect(JSON.parse(String(requests[1]?.[1]?.body)).run_checks).toEqual([
      "npm:check",
    ]);
  });
});
