import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  date,
  issuePayload,
  label,
  projectPath,
  type Entry,
  type Issue,
  type Page,
} from "@/lib/api/client";
import {
  Badge,
  ErrorNotice,
  Pager,
  Panel,
  RecordForm,
  Section,
  type Field,
} from "@/app/shared";
import type { ProjectProps } from "./Workspace";

const statuses = [
  "backlog",
  "ready",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
];
const fields: Field[] = [
  { name: "title", title: "Title", required: true },
  { name: "type", title: "Type", options: ["task", "bug", "feature"] },
  { name: "status", title: "Status", options: statuses },
  { name: "priority", title: "Priority", options: ["medium", "high", "low"] },
  { name: "description", title: "Description", kind: "area" },
  { name: "acceptance_criteria", title: "Acceptance criteria", kind: "area" },
  {
    name: "reproduction_steps",
    title: "Bug: reproduction steps",
    kind: "area",
  },
  { name: "expected_behavior", title: "Bug: expected behaviour", kind: "area" },
  { name: "actual_behavior", title: "Bug: actual behaviour", kind: "area" },
  { name: "affected_version", title: "Affected commit/version" },
  {
    name: "verification",
    title: "Verification evidence",
    kind: "area",
    hint: "Record actual checks and outcomes, including failures or checks not performed.",
  },
  { name: "labels", title: "Labels", kind: "list" },
  {
    name: "links",
    title: "File, document, or commit references",
    kind: "list",
    hint: "For example src/main.ts:42, docs/setup.md, or a commit hash. References do not grant file access.",
  },
];
export function Issues({
  project,
  actor,
  refresh,
  targetIssue,
}: ProjectProps & { targetIssue: string | null }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [priority, setPriority] = useState("");
  const [labelFilter, setLabelFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(targetIssue);
  const [creating, setCreating] = useState(false);
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    q: query,
    status,
    type,
    priority,
    label: labelFilter,
    offset: String(offset),
  });
  const list = useQuery({
    queryKey: ["issues", project.id, params.toString()],
    refetchInterval: 5000,
    queryFn: () =>
      api<Page<Issue>>(`${projectPath(project.id)}/issues?${params}`),
  });
  return (
    <>
      <div className="mb-5 flex flex-wrap gap-3">
        <Input
          className="h-8 max-w-sm"
          aria-label="Search issues"
          placeholder="Search issues…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
        {[
          { title: "Status", value: status, set: setStatus, options: statuses },
          {
            title: "Type",
            value: type,
            set: setType,
            options: ["bug", "task", "feature"],
          },
          {
            title: "Priority",
            value: priority,
            set: setPriority,
            options: ["high", "medium", "low"],
          },
        ].map((f) => (
          <select
            key={f.title}
            aria-label={`Filter ${f.title.toLowerCase()}`}
            className="stash-input w-auto"
            value={f.value}
            onChange={(e) => {
              f.set(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All {f.title.toLowerCase()}s</option>
            {f.options.map((v) => (
              <option key={v} value={v}>
                {label(v)}
              </option>
            ))}
          </select>
        ))}
        <Input
          className="h-8 w-32"
          placeholder="Label filter"
          aria-label="Filter label"
          value={labelFilter}
          onChange={(e) => {
            setLabelFilter(e.target.value);
            setOffset(0);
          }}
        />
        <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}>
          New issue
        </Button>
      </div>
      {list.isPending && <p className="text-sm">Loading issues…</p>}
      {list.error && <ErrorNotice error={list.error} />}
      {list.data?.total === 0 && (
        <p className="rounded border p-8 text-center text-sm text-muted-foreground">
          No matching issues. Create one or adjust the filters.
        </p>
      )}
      <div className="overflow-hidden rounded border bg-card">
        {list.data?.items.map((i) => (
          <button
            key={i.id}
            onClick={() => setSelected(i.id)}
            className="grid w-full grid-cols-[1fr_auto] items-center gap-3 border-b px-4 py-4 text-left last:border-0 hover:bg-muted/40 sm:grid-cols-[70px_1fr_120px_80px]"
          >
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:block">
              #{i.number}
            </span>
            <div>
              <p className="text-sm font-medium">{i.title}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                #{i.number} · {label(i.type)}
                {i.labels.length > 0 && ` · ${i.labels.join(", ")}`}
              </p>
            </div>
            <Badge value={i.status} />
            <span className="hidden text-xs sm:block">{label(i.priority)}</span>
          </button>
        ))}
      </div>
      {list.data && (
        <Pager offset={offset} total={list.data.total} onChange={setOffset} />
      )}
      {creating && (
        <Panel title="New issue" onClose={() => setCreating(false)}>
          <RecordForm
            fields={fields}
            onClose={() => setCreating(false)}
            onSave={async (value) => {
              await api(`${projectPath(project.id)}/issues`, "POST", {
                ...value,
                actor,
              });
              await refresh();
            }}
          />
        </Panel>
      )}
      {selected && (
        <IssueDetail
          key={selected}
          project={project}
          actor={actor}
          refresh={refresh}
          id={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
function IssueDetail({
  project,
  actor,
  refresh,
  id,
  onClose,
}: ProjectProps & { id: string; onClose: () => void }) {
  const path = `${projectPath(project.id)}/issues/${id}`;
  const [editing, setEditing] = useState<Issue | null>(null);
  const [comment, setComment] = useState("");
  const [commentKey, setCommentKey] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const [commentOffset, setCommentOffset] = useState(0);
  const query = useQuery({
    queryKey: ["issue", project.id, id],
    queryFn: () => api<Issue>(path),
    refetchInterval: 5000,
  });
  const comments = useQuery({
    queryKey: ["comments", project.id, id, commentOffset],
    refetchInterval: 5000,
    queryFn: () => api<Entry[]>(`${path}/comments?offset=${commentOffset}`),
  });
  const issue = query.data;
  return (
    <Panel
      title={issue ? `#${issue.number} ${issue.title}` : "Issue"}
      description={
        issue
          ? `${label(issue.type)} · ${date(issue.updated_at)} · Created by ${issue.creator.name}`
          : "Loading issue…"
      }
      onClose={onClose}
    >
      {query.error && <ErrorNotice error={query.error} />}
      {editing && issue && editing.revision !== issue.revision && (
        <p role="status" className="my-3 text-sm">
          This issue changed while you were editing. Your draft is preserved;
          saving will check its original revision. Copy your draft and reload to
          reconcile the changes.
        </p>
      )}
      {issue &&
        (editing ? (
          <RecordForm
            fields={fields}
            initial={issuePayload(editing)}
            onClose={() => setEditing(null)}
            onSave={async (value) => {
              await api(path, "PUT", {
                ...value,
                revision: editing.revision,
                actor,
              });
              await refresh();
            }}
          />
        ) : (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <Badge value={issue.status} />
              <span className="text-xs">{label(issue.priority)} priority</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                onClick={() => setEditing(structuredClone(issue))}
              >
                Edit issue
              </Button>
            </div>
            {[
              ["Description", issue.description],
              ["Acceptance criteria", issue.acceptance_criteria],
              ...(issue.type === "bug"
                ? [
                    ["Reproduction steps", issue.reproduction_steps],
                    ["Expected behaviour", issue.expected_behavior],
                    ["Actual behaviour", issue.actual_behavior],
                    ["Affected commit/version", issue.affected_version],
                  ]
                : []),
              [
                "Verification evidence",
                issue.verification || "No verification recorded.",
              ],
              ["Labels", issue.labels.join(", ")],
              ["File/doc/commit references", issue.links.join("\n")],
            ].map(([title, text]) => (
              <Section key={title} title={title || ""}>
                <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                  {text || "Not recorded"}
                </p>
              </Section>
            ))}
            <Section title="Comments">
              {comments.error && <ErrorNotice error={comments.error} />}
              {comments.data?.map((c) => (
                <div key={c.id} className="rounded bg-muted/50 p-3">
                  <p className="text-xs font-medium">
                    {c.actor.name} · {label(c.actor.kind)} ·{" "}
                    {date(c.created_at)}
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm">
                    {String(c.body)}
                  </p>
                </div>
              ))}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={commentOffset === 0}
                  onClick={() =>
                    setCommentOffset(Math.max(0, commentOffset - 100))
                  }
                >
                  Newer
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={(comments.data?.length || 0) < 100}
                  onClick={() => setCommentOffset(commentOffset + 100)}
                >
                  Older
                </Button>
              </div>
              <textarea
                className="stash-input min-h-24"
                aria-label="New comment"
                placeholder="Add a comment…"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <Button
                size="sm"
                disabled={!comment.trim() || pending}
                onClick={async () => {
                  setPending(true);
                  setError(null);
                  try {
                    await api(
                      `${path}/comments`,
                      "POST",
                      { body: comment, actor },
                      commentKey,
                    );
                    setComment("");
                    setCommentKey(crypto.randomUUID());
                    await refresh();
                  } catch (e) {
                    setError(e);
                  } finally {
                    setPending(false);
                  }
                }}
              >
                {pending ? "Adding…" : "Add comment"}
              </Button>
              {error != null && <ErrorNotice error={error} />}
            </Section>
          </div>
        ))}
    </Panel>
  );
}
