import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  api,
  date,
  projectPath,
  projectPayload,
  type ContextData,
  type Project,
} from "@/lib/api/client";
import {
  Copy,
  ErrorNotice,
  Panel,
  Preview,
  RecordForm,
  Section,
  type Field,
} from "@/app/shared";
import type { ProjectProps, Tab } from "./Workspace";

const fields: Field[] = [
  { name: "name", title: "Name", required: true },
  {
    name: "path",
    title: "Project path",
    required: true,
    hint: "Update this when the project moves; its ID and records stay the same.",
  },
  {
    name: "status",
    title: "Status",
    options: ["active", "paused", "archived"],
  },
  { name: "description", title: "Description", kind: "area" },
  { name: "purpose", title: "Purpose", kind: "area" },
  { name: "tags", title: "Tags", kind: "list" },
  { name: "stack", title: "Stack", kind: "list" },
  { name: "focus", title: "Current focus", kind: "area" },
  { name: "next_step", title: "Next step", kind: "area" },
  { name: "brief", title: "Persistent project brief", kind: "area" },
  { name: "setup_command", title: "Setup command" },
  { name: "run_command", title: "Run command" },
  { name: "test_command", title: "Test command" },
  { name: "services", title: "Required services", kind: "list" },
  {
    name: "env_names",
    title: "Environment variable names",
    kind: "list",
    hint: "Names only, such as API_KEY. Never enter secret values.",
  },
  { name: "repo_url", title: "Repository URL" },
  { name: "demo_url", title: "Demo URL" },
  {
    name: "screenshot",
    title: "Screenshot path",
    hint: "Optional project-relative PNG, JPEG, or WebP file.",
  },
  {
    name: "doc_roots",
    title: "Readable document paths",
    kind: "list",
    hint: "Use .stash/docs, .stash/decisions, and .stash/handoffs for development notes. The Docs tab shows only stash notes.",
  },
  {
    name: "writable_doc_roots",
    title: "Writable document paths",
    kind: "list",
    hint: "Include .stash/docs for editing development notes. Decision and handoff history is read-only in Docs.",
  },
];
export function Overview({
  project: p,
  actor,
  refresh,
  jump,
  onRemoved,
}: ProjectProps & { jump: (tab: Tab) => void; onRemoved: () => void }) {
  const [editing, setEditing] = useState<Project | null>(null);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const context = useQuery({
    queryKey: ["context", p.id],
    queryFn: () => api<ContextData>(`${projectPath(p.id)}/context`),
  });
  const latest = context.data?.handoffs[0];
  const git = p.observations.git;
  return (
    <>
      <div className="mb-6 flex flex-wrap justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setEditing(structuredClone(p))}
        >
          Edit project
        </Button>
        <a
          className="inline-flex items-center rounded-md border px-3 text-xs"
          href={`/api/v1/projects/${p.id}/export`}
        >
          Export JSON
        </a>
        <a
          className="inline-flex items-center rounded-md border px-3 text-xs"
          href={`/api/v1/projects/${p.id}/export?format=markdown`}
        >
          Export Markdown
        </a>
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,.75fr)]">
        <div className="space-y-8">
          <Section title={p.description || "What is this project?"}>
            <div className="overflow-hidden rounded border">
              <Preview
                name={p.name}
                image={
                  p.screenshot
                    ? `/api/v1/projects/${p.id}/screenshot`
                    : undefined
                }
              />
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
              {p.purpose || "Add the project's purpose in Edit project."}
            </p>
            <Button variant="ghost" size="sm" onClick={() => jump("Docs")}>
              Read docs →
            </Button>
            {p.demo_url && (
              <a
                className="ml-3 text-xs underline"
                href={p.demo_url}
                target="_blank"
                rel="noreferrer"
              >
                Open demo
              </a>
            )}
          </Section>
          <div className="grid gap-5 sm:grid-cols-2">
            <section className="border-l-2 border-status-active pl-4">
              <h2 className="text-[10px] font-semibold uppercase text-muted-foreground">
                Where did I stop?
              </h2>
              {context.isPending ? (
                <p className="mt-3 text-sm">Loading handoff…</p>
              ) : (
                <>
                  <p className="mt-3 whitespace-pre-wrap text-sm">
                    {latest
                      ? String(latest.summary)
                      : "No handoff recorded yet."}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {latest && date(latest.created_at)}
                  </p>
                </>
              )}
              <Button variant="link" size="sm" onClick={() => jump("Context")}>
                Open context
              </Button>
            </section>
            <section className="border-l-2 border-foreground pl-4">
              <h2 className="text-[10px] font-semibold uppercase text-muted-foreground">
                Next step
              </h2>
              <p className="mt-3 whitespace-pre-wrap text-sm">
                {p.next_step ||
                  (latest ? String(latest.next_actions) : "Not recorded")}
              </p>
            </section>
          </div>
          <Section title="Current focus">
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {p.focus || "Not recorded"}
            </p>
          </Section>
          {context.error && <ErrorNotice error={context.error} />}
        </div>
        <aside className="space-y-6">
          <div className="rounded border bg-card p-4">
            <Section title="Local development">
              {(
                [
                  ["Setup", p.setup_command],
                  ["Run", p.run_command],
                  ["Test", p.test_command],
                ] as const
              ).map(([title, command]) => (
                <div key={title}>
                  <p className="mb-1 text-[10px] uppercase text-muted-foreground">
                    {title}
                  </p>
                  {command ? (
                    <div className="flex items-center justify-between gap-2 rounded bg-code p-3">
                      <code className="whitespace-pre-wrap break-all text-xs text-code-foreground">
                        {command}
                      </code>
                      <Copy
                        text={command}
                        title={`Copy ${title.toLowerCase()} command`}
                        compact
                      />
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Not recorded
                    </p>
                  )}
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                Commands are displayed only. stash does not execute them.
              </p>
              <p className="text-xs">
                Services: {p.services.join(", ") || "Not recorded"}
              </p>
              <p className="text-xs">
                Environment names: {p.env_names.join(", ") || "Not recorded"}
              </p>
            </Section>
          </div>
          <div className="rounded border p-4">
            <Section title="Project details">
              <dl className="space-y-3 text-xs">
                {[
                  ["Open issues", String(p.open_issue_count)],
                  [
                    "Branch",
                    git?.available
                      ? git.branch || "Unknown"
                      : "Git unavailable",
                  ],
                  ["Latest commit", git?.commit || "Not recorded"],
                  [
                    "Working tree",
                    git?.available
                      ? git.dirty
                        ? "Has tracked changes"
                        : "No tracked changes"
                      : "Unavailable",
                  ],
                  ["Tracker update", date(p.tracker_updated_at)],
                  ["Code activity", date(p.code_activity_at)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3">
                    <dt className="shrink-0 text-muted-foreground">{k}</dt>
                    <dd className="break-all text-right font-mono">{v}</dd>
                  </div>
                ))}
              </dl>
              {git?.error && (
                <p className="text-xs text-muted-foreground">{git.error}</p>
              )}
              {p.observations.scan_truncated && (
                <p className="text-xs text-muted-foreground">
                  Filesystem check was bounded; code activity may be incomplete.
                </p>
              )}
            </Section>
          </div>
          <div className="rounded border p-4">
            <Section title="Stack and tags">
              <div className="flex flex-wrap gap-2">
                {[...p.stack, ...p.tags].map((t, i) => (
                  <span
                    key={`${t}-${i}`}
                    className="rounded border bg-muted px-2 py-1 text-[10px]"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </Section>
          </div>
          <button
            className="text-xs text-destructive underline"
            onClick={() => setRemoving(true)}
          >
            Remove from shelf
          </button>
        </aside>
      </div>
      {editing && (
        <Panel title="Edit project" onClose={() => setEditing(null)}>
          <RecordForm
            fields={fields}
            initial={projectPayload(editing)}
            onClose={() => setEditing(null)}
            onSave={async (value) => {
              await api(projectPath(p.id), "PUT", {
                ...value,
                revision: editing.revision,
                actor,
              });
              await refresh();
            }}
          />
        </Panel>
      )}
      {removing && (
        <Panel
          title="Remove project?"
          description="This removes only the shelf registration. Source files and the .stash folder, including issues and handoffs, stay on disk. Register the folder again to restore it to your shelf."
          onClose={() => setRemoving(false)}
        >
          <a
            className="text-sm underline"
            href={`/api/v1/projects/${p.id}/export`}
          >
            Export records first
          </a>
          {error != null && <ErrorNotice error={error} />}
          <div className="mt-6 flex gap-3">
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  await api(
                    `${projectPath(p.id)}?revision=${p.revision}`,
                    "DELETE",
                    { actor },
                  );
                  await refresh();
                  onRemoved();
                } catch (e) {
                  setError(e);
                }
              }}
            >
              Remove from shelf
            </Button>
            <Button variant="outline" onClick={() => setRemoving(false)}>
              Cancel
            </Button>
          </div>
        </Panel>
      )}
    </>
  );
}
