import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/app/App";
import { api, ApiError, type Project } from "@/lib/api/client";

const project = (id: string, name: string): Project => ({
  id,
  name,
  path: `/projects/${id}`,
  status: "active",
  availability: "available",
  description: `${name} purpose`,
  purpose: "",
  brief: "",
  focus: "",
  next_step: `Continue ${name}`,
  tags: [],
  stack: ["TypeScript"],
  services: [],
  env_names: [],
  setup_command: "",
  run_command: "npm run dev",
  test_command: "",
  repo_url: "",
  demo_url: "",
  screenshot: "",
  doc_roots: ["README.md", "docs"],
  writable_doc_roots: ["docs"],
  revision: "first-revision",
  created_at: "2026-10-03T10:00:00Z",
  tracker_updated_at: "2026-10-03T10:00:00Z",
  code_activity_at: null,
  last_activity_at: "2026-10-03T10:00:00Z",
  activity_source: "tracker",
  last_opened_at: null,
  open_issue_count: 0,
  observations: {
    observed_at: "2026-10-03T10:00:00Z",
    git: { available: false },
  },
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}
function mockApi(initial: Project[]) {
  const items = [...initial];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "http://localhost").pathname.replace(
      "/api/v1",
      "",
    );
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    let data: unknown;
    if (path === "/settings")
      data = { master_folder: "", identity: "Ben", revision: 0 };
    else if (path === "/shelf-summary")
      data = {
        total: items.length,
        statuses: { active: items.length },
        opened: 0,
        tags: [],
      };
    else if (path === "/projects" && init?.method === "POST") {
      const p = { ...project("registered", "New project"), path: body.path };
      items.push(p);
      data = p;
    } else if (path === "/projects") data = { items, total: items.length };
    else {
      const id = path.split("/")[2];
      const p = items.find((x) => x.id === id);
      if (path.endsWith("/context"))
        data = {
          project: p,
          issues: [],
          decisions: [],
          handoffs: [],
          markdown: `# ${p?.name}\nNext step: ${p?.next_step}`,
        };
      else if (
        path.endsWith("/observations") ||
        path.endsWith("/file-observations")
      )
        data = [];
      else if (path.endsWith("/watcher"))
        data = { enabled: false, checked_at: null, warnings: [] };
      else if (path.endsWith("/integrations/codex"))
        data = { enabled: false, pending: 0, worker: null };
      else if (path.endsWith("/resume")) data = null;
      else if (path.endsWith("/sessions")) data = [];
      else if (path.endsWith("/docs"))
        data = {
          files: ["README.md", "docs/setup.md", ".stash/docs/brief.md"],
          missing_roots: [],
        };
      else if (path.endsWith("/document"))
        data = {
          path: ".stash/docs/brief.md",
          content: `# ${p?.name}`,
          html: `<h1>${p?.name} documentation</h1>`,
          revision: "abc",
        };
      else data = p;
    }
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("Real workspace workflow", () => {
  it("registers an existing directory from the empty shelf", async () => {
    const fetch = mockApi([]);
    mount();
    await screen.findByText("No projects on this shelf");
    fireEvent.click(screen.getByRole("button", { name: "Add project" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Existing project path"), {
      target: { value: "/projects/new-project" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Register project" }),
    );
    await screen.findByRole("heading", { name: "New project" });
    expect(
      fetch.mock.calls.some(
        ([url, init]) =>
          url === "/api/v1/projects" &&
          init?.method === "POST" &&
          String(init.body).includes("/projects/new-project"),
      ),
    ).toBe(true);
  });
  it("loads documentation scoped to the selected project", async () => {
    mockApi([project("first", "First"), project("second", "Second")]);
    mount();
    fireEvent.click(
      await screen.findByRole("button", { name: /Second.*purpose/ }),
    );
    await screen.findByRole("heading", { name: "Second" });
    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    expect(
      await screen.findByRole("heading", { name: "Second documentation" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "First documentation" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "brief.md" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "README.md" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "setup.md" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to projects" }));
    expect(screen.getByRole("heading", { name: "All projects" })).toBeVisible();
  });
  it("shows an actionable unavailable-server error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Network error")),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "server is unavailable",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("preserves API conflict errors for editing flows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "conflict",
            message: "Document changed externally",
          }),
          { status: 409 },
        ),
      ),
    );
    await expect(api("/projects/p/document", "PUT", {})).rejects.toMatchObject({
      code: "conflict",
      status: 409,
      message: "Document changed externally",
    });
  });
});

it("keeps the original metadata revision when background data changes", async () => {
  const { Overview } = await import("@/features/Overview");
  const original = project("edit", "Editable");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const fetch = vi.fn(
    async (_url: string, init?: RequestInit) =>
      new Response(
        JSON.stringify(
          init?.method === "PUT"
            ? {
                code: "conflict",
                message: "Project changed. Reload before applying your draft",
              }
            : {
                project: original,
                issues: [],
                decisions: [],
                handoffs: [],
                markdown: "",
              },
        ),
        { status: init?.method === "PUT" ? 409 : 200 },
      ),
  );
  vi.stubGlobal("fetch", fetch);
  const actor = { name: "Ben", kind: "human" as const };
  const props = {
    actor,
    refresh: async () => {},
    jump: () => {},
    onRemoved: () => {},
  };
  const { rerender } = render(
    <QueryClientProvider client={client}>
      <Overview project={original} {...props} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit project" }));
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "My draft" },
  });
  rerender(
    <QueryClientProvider client={client}>
      <Overview
        project={{
          ...original,
          revision: "external-revision",
          description: "External description",
        }}
        {...props}
      />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Project changed"),
  );
  const write = fetch.mock.calls.find(([, init]) => init?.method === "PUT");
  expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({
    revision: "first-revision",
    description: "My draft",
  });
  expect(screen.getByLabelText("Description")).toHaveValue("My draft");
});

it("preserves a human issue draft and its original revision when an agent updates the issue", async () => {
  const { Issues } = await import("@/features/Issues");
  const p = project("shared", "Shared");
  const issue = {
    id: "issue",
    project_id: p.id,
    number: 1,
    title: "Shared task",
    type: "task",
    status: "ready",
    priority: "medium",
    description: "Original",
    acceptance_criteria: "",
    reproduction_steps: "",
    expected_behavior: "",
    actual_behavior: "",
    affected_version: "",
    verification: "",
    labels: [],
    links: [],
    creator: { name: "Codex", kind: "agent" },
    updater: { name: "Codex", kind: "agent" },
    revision: "original-issue-revision",
    created_at: "2026-10-03T10:00:00Z",
    updated_at: "2026-10-03T10:00:00Z",
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    const data =
      options?.method === "PUT"
        ? { code: "conflict", message: "Issue changed; reload and compare" }
        : url.includes("comments")
          ? []
          : url.includes("issues?")
            ? { items: [issue], total: 1 }
            : issue;
    return new Response(JSON.stringify(data), {
      status: options?.method === "PUT" ? 409 : 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetch);
  render(
    <QueryClientProvider client={client}>
      <Issues
        project={p}
        actor={{ name: "Owner", kind: "human" }}
        refresh={async () => {}}
        targetIssue="issue"
      />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Edit issue" }));
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Human draft" },
  });
  client.setQueryData(["issue", p.id, "issue"], {
    ...issue,
    description: "Agent changed",
    revision: "new-agent-revision",
  });
  expect(await screen.findByRole("status")).toHaveTextContent(
    "changed while you were editing",
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Issue changed");
  expect(screen.getByLabelText("Description")).toHaveValue("Human draft");
  const mutation = fetch.mock.calls.find(
    ([, options]) => options?.method === "PUT",
  );
  expect(JSON.parse(String(mutation?.[1]?.body))).toMatchObject({
    revision: "original-issue-revision",
    description: "Human draft",
  });
});
