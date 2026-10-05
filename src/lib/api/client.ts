export type Actor = { name: string; kind: "human" | "agent" };
export type Settings = {
  master_folder: string;
  identity: string;
  revision: number;
};
export type Project = {
  id: string;
  name: string;
  path: string;
  status: string;
  availability: string;
  storage_error?: string | null;
  migration_pending?: boolean;
  description: string;
  purpose: string;
  brief: string;
  focus: string;
  next_step: string;
  tags: string[];
  stack: string[];
  services: string[];
  env_names: string[];
  setup_command: string;
  run_command: string;
  test_command: string;
  repo_url: string;
  demo_url: string;
  screenshot: string;
  doc_roots: string[];
  writable_doc_roots: string[];
  revision: string;
  created_at: string;
  tracker_updated_at: string;
  code_activity_at: string | null;
  last_activity_at: string;
  activity_source: string;
  last_opened_at: string | null;
  open_issue_count: number;
  observations: {
    observed_at?: string;
    error?: string;
    scan_truncated?: boolean;
    git?: {
      available: boolean;
      error?: string;
      branch?: string;
      commit?: string;
      subject?: string;
      dirty?: boolean;
    };
  };
};
export type Issue = {
  id: string;
  project_id: string;
  number: number;
  title: string;
  type: string;
  status: string;
  priority: string;
  description: string;
  acceptance_criteria: string;
  reproduction_steps: string;
  expected_behavior: string;
  actual_behavior: string;
  affected_version: string;
  verification: string;
  labels: string[];
  links: string[];
  creator: Actor;
  created_at: string;
  updated_at: string;
  revision: string;
};
export type Entry = {
  id: string;
  project_id: string;
  kind: string;
  actor: Actor;
  created_at: string;
  summary?: string;
  choice?: string;
  reasoning?: string;
  alternatives?: string;
  reference?: string;
  completed_work?: string;
  changed_files?: string;
  verification?: string;
  unresolved_problems?: string;
  blockers?: string;
  next_actions?: string;
  commit?: string;
  body?: string;
  [key: string]: unknown;
};
export type ContextData = {
  project: Project;
  issues: Issue[];
  decisions: Entry[];
  handoffs: Entry[];
  markdown: string;
};
export type Activity = {
  id: string;
  kind: string;
  record_id: string;
  summary: string;
  actor: Actor;
  created_at: string;
};
export type Document = {
  path: string;
  content: string;
  html: string;
  revision: string;
};
export type Candidate = {
  name: string;
  path: string;
  project_id: string | null;
  error: string | null;
};
export type Page<T> = { items: T[]; total: number };

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(key ? { "Idempotency-Key": key } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    throw new ApiError(
      "server_unavailable",
      "stash server is unavailable. Start the local backend and retry.",
      0,
    );
  }
  const data = (await response.json().catch(() => null)) as {
    code?: string;
    message?: string;
    details?: { field: string; message: string }[];
  } | null;
  if (!response.ok)
    throw new ApiError(
      data?.code || "server_error",
      [
        data?.message || "The local server could not complete this request.",
        ...(data?.details?.map((d) => `${d.field}: ${d.message}`) || []),
      ].join("\n"),
      response.status,
    );
  return data as T;
}
export const projectPath = (id: string) =>
  `/projects/${encodeURIComponent(id)}`;
export const label = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (s) => s.toUpperCase());
export const date = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : "Not recorded";
export function projectPayload(p: Project) {
  const keys = [
    "revision",
    "name",
    "path",
    "status",
    "description",
    "purpose",
    "brief",
    "focus",
    "next_step",
    "tags",
    "stack",
    "setup_command",
    "run_command",
    "test_command",
    "services",
    "env_names",
    "repo_url",
    "demo_url",
    "screenshot",
    "doc_roots",
    "writable_doc_roots",
  ] as const;
  return Object.fromEntries(keys.map((key) => [key, p[key]]));
}
export function issuePayload(i: Issue) {
  const {
    id: _id,
    project_id: _project,
    number: _number,
    creator: _creator,
    created_at: _created,
    updated_at: _updated,
    ...data
  } = i;
  return data;
}
