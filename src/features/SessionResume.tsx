import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, projectPath, type Actor } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Panel, RecordForm, type Field } from "@/app/shared";

type Observation = {
  git: boolean;
  branch: string | null;
  head: string | null;
  dirty: boolean | null;
  warnings: string[];
};
type Session = {
  id: string;
  task: string;
  status: string;
  revision: string;
  created_at: string;
  actor: Actor;
  observation: Observation;
};
type Checkpoint = {
  id: string;
  created_at: string;
  actor: Actor;
  explanation: {
    progress: string;
    blockers: string;
    unfinished_work: string;
    next_actions: string;
    verification: string;
    verification_includes_uncommitted: boolean | null;
    final: boolean;
  };
  observation: Observation;
};
type ResumeData = {
  session: Session;
  checkpoint: Checkpoint | null;
  changes: {
    added: string[];
    removed: string[];
    modified: string[];
    head_changed: boolean;
    branch_changed: boolean;
    complete: boolean;
  };
  current_observation: Observation;
  incomplete_sessions: Session[];
};
const checkpointFields: Field[] = [
  { name: "progress", title: "Progress", kind: "area" },
  { name: "unfinished_work", title: "Unfinished work", kind: "area" },
  { name: "blockers", title: "Blockers", kind: "area" },
  {
    name: "verification",
    title: "Actual verification and results",
    kind: "area",
  },
  {
    name: "verification_scope",
    title: "Did verification include uncommitted changes?",
    options: ["Not recorded", "Yes", "No"],
  },
  { name: "next_actions", title: "Next actions", kind: "area", required: true },
  {
    name: "completion",
    title: "Session state",
    options: ["Checkpoint — unfinished", "Final handoff — completed"],
  },
];
export function SessionResume({
  projectId,
  actor,
  refresh,
  targetSessionId,
  onCloseReference,
}: {
  targetSessionId?: string | null;
  onCloseReference?: () => void;
  projectId: string;
  actor: Actor;
  refresh: () => Promise<void>;
}) {
  const [form, setForm] = useState<"start" | "checkpoint" | null>(null);
  const [writeId, setWriteId] = useState("");
  const [snapshot, setSnapshot] = useState<Session | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const shownHistoryId = historyId || targetSessionId;
  const base = projectPath(projectId);
  const resume = useQuery({
    queryKey: ["resume", projectId],
    queryFn: () => api<ResumeData | null>(`${base}/resume`),
  });
  const sessions = useQuery({
    queryKey: ["sessions", projectId],
    queryFn: () => api<Session[]>(`${base}/sessions`),
  });
  const history = useQuery({
    queryKey: ["session", projectId, shownHistoryId],
    queryFn: () =>
      api<{ session: Session; checkpoints: Checkpoint[] }>(
        `${base}/sessions/${shownHistoryId}`,
      ),
    enabled: !!shownHistoryId,
  });
  const observed = useQuery({
    queryKey: ["hook-observations", projectId],
    queryFn: () =>
      api<
        {
          id: string;
          event: string;
          session_id: string;
          observed_at: string;
          tool: string | null;
          exit_code: number | null;
          tool_error: boolean | null;
        }[]
      >(`${base}/observations`),
    refetchInterval: 5000,
  });
  const integration = useQuery({
    queryKey: ["codex-integration", projectId],
    queryFn: () =>
      api<{
        enabled: boolean;
        pending: number;
        worker: { error: string | null } | null;
      }>(`${base}/integrations/codex`),
    refetchInterval: 5000,
  });
  const data = resume.data;
  const open = (kind: "start" | "checkpoint", session = data?.session) => {
    setWriteId(crypto.randomUUID());
    setSnapshot(session || null);
    setForm(kind);
  };
  return (
    <section className="space-y-4 rounded-md border-2 bg-card p-5">
      <h2 className="text-xl font-semibold">Session checkpoint and recovery</h2>
      {resume.error && <ErrorNotice error={resume.error} />}
      {resume.isPending && <p>Loading session checkpoint…</p>}
      {data ? (
        <>
          <p className="text-sm font-medium">{data.session.task}</p>
          <p className="text-xs text-muted-foreground">
            {data.session.actor.name} · {date(data.session.created_at)} ·{" "}
            {data.session.id}
          </p>
          <p className="text-sm">
            {data.session.status === "incomplete"
              ? "Unfinished session: no final handoff checkpoint was saved. Inspect current code before resuming."
              : "Final handoff checkpoint recorded."}
          </p>
          {data.checkpoint ? (
            <CheckpointView checkpoint={data.checkpoint} />
          ) : (
            <p className="text-sm">
              Task intent saved; no progress checkpoint yet.
            </p>
          )}
          <div className="space-y-2 border-t pt-3 text-sm">
            <p>
              Repository changes since{" "}
              {data.checkpoint ? "checkpoint" : "session start"}
            </p>
            {(["added", "modified", "removed"] as const).map((kind) => (
              <p key={kind}>
                {kind}: {data.changes[kind].join(", ") || "None observed"}
              </p>
            ))}
            <p>
              HEAD changed: {data.changes.head_changed ? "Yes" : "No"} · Branch
              changed: {data.changes.branch_changed ? "Yes" : "No"}
            </p>
            {!data.changes.complete && (
              <p role="alert">
                Observation is partial; omitted files cannot be compared
                reliably.
              </p>
            )}
            {data.current_observation.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
          {data.incomplete_sessions.length > 1 && (
            <p>
              {data.incomplete_sessions.length} sessions remain unfinished.
              Review history before choosing work.
            </p>
          )}
        </>
      ) : (
        !resume.isPending &&
        !resume.error && (
          <p className="text-sm">
            No session recorded. Save task intent before changing code.
          </p>
        )
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => open("start")}>
          Start session
        </Button>
        {data?.session.status === "incomplete" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => open("checkpoint")}
          >
            Save checkpoint
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            void resume.refetch();
            void sessions.refetch();
            void refresh();
          }}
        >
          Refresh observations
        </Button>
      </div>
      <details>
        <summary className="cursor-pointer text-sm">
          Observed agent events
        </summary>
        <p className="mt-2 text-xs text-muted-foreground">
          Lifecycle and tool facts are separate from written progress. They do
          not establish verification or task completion.
        </p>
        {integration.data?.enabled && (
          <p className="text-sm">
            Codex integration enabled · {integration.data.pending} pending
            events
            {integration.data.worker?.error
              ? ` · ${integration.data.worker.error}`
              : ""}
            . Client hook trust is required separately.
          </p>
        )}
        {observed.error && <ErrorNotice error={observed.error} />}
        {Array.isArray(observed.data) &&
          observed.data.slice(0, 20).map((event) => (
            <p key={event.id} className="mt-2 text-xs">
              {date(event.observed_at)} · {event.event} · session{" "}
              {event.session_id} · {event.tool || "lifecycle"}
              {event.exit_code !== null && event.exit_code !== undefined
                ? ` · observed exit ${event.exit_code}`
                : ""}
              {event.tool_error === true ? " · tool reported an error" : ""}
            </p>
          ))}
      </details>
      <details>
        <summary className="cursor-pointer text-sm">Session history</summary>
        {sessions.error && <ErrorNotice error={sessions.error} />}
        {Array.isArray(sessions.data) &&
          sessions.data.map((s) => (
            <div key={s.id} className="mt-2 flex items-center gap-2">
              <button
                className="text-left text-sm underline"
                onClick={() => setHistoryId(s.id)}
              >
                {s.task} · {s.actor.name} · {s.status}
              </button>
              {s.status === "incomplete" && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => open("checkpoint", s)}
                >
                  Checkpoint
                </Button>
              )}
            </div>
          ))}
      </details>
      {form && (
        <Panel
          title={
            form === "start"
              ? "Record session intent"
              : "Save progress checkpoint"
          }
          onClose={() => setForm(null)}
        >
          <RecordForm
            fields={
              form === "start"
                ? [
                    {
                      name: "task",
                      title: "Current task",
                      required: true,
                      kind: "area",
                    },
                  ]
                : checkpointFields
            }
            onClose={() => setForm(null)}
            onSave={async (value) => {
              if (form === "start")
                await api(`${base}/sessions`, "POST", {
                  id: writeId,
                  task: value["task"],
                  actor,
                });
              else if (snapshot)
                await api(
                  `${base}/sessions/${snapshot.id}/checkpoints`,
                  "POST",
                  {
                    id: writeId,
                    revision: snapshot.revision,
                    actor,
                    progress: value["progress"],
                    unfinished_work: value["unfinished_work"],
                    blockers: value["blockers"],
                    verification: value["verification"],
                    next_actions: value["next_actions"],
                    verification_includes_uncommitted:
                      value["verification_scope"] === "Not recorded"
                        ? null
                        : value["verification_scope"] === "Yes",
                    final: value["completion"] === "Final handoff — completed",
                  },
                );
              await refresh();
            }}
          />
        </Panel>
      )}
      {shownHistoryId && (
        <Panel
          title="Session checkpoint history"
          onClose={() => {
            setHistoryId(null);
            onCloseReference?.();
          }}
        >
          {history.error && <ErrorNotice error={history.error} />}
          {history.data?.checkpoints?.map((c) => (
            <CheckpointView key={c.id} checkpoint={c} />
          ))}
        </Panel>
      )}
    </section>
  );
}
function CheckpointView({ checkpoint: c }: { checkpoint: Checkpoint }) {
  return (
    <div className="space-y-2 border-t py-3 text-sm">
      <p className="text-xs text-muted-foreground">
        {date(c.created_at)} · {c.actor.name} · {c.id}
      </p>
      {(
        [
          "progress",
          "unfinished_work",
          "blockers",
          "verification",
          "next_actions",
        ] as const
      ).map((key) => (
        <p key={key} className="whitespace-pre-wrap">
          <strong>{key.replaceAll("_", " ")}: </strong>
          {c.explanation[key] || "Not recorded"}
        </p>
      ))}
      <p>
        Verification included uncommitted changes:{" "}
        {c.explanation.verification_includes_uncommitted === null
          ? "Not recorded"
          : c.explanation.verification_includes_uncommitted
            ? "Yes"
            : "No"}
      </p>
      <p className="font-mono text-xs">
        {c.observation.git
          ? `Branch ${c.observation.branch || "detached/unborn"} · HEAD ${c.observation.head || "unborn"} · dirty ${String(c.observation.dirty)}`
          : "Project without Git"}
      </p>
    </div>
  );
}
