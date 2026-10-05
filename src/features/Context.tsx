import { FileWatcher } from "./FileWatcher";
import { SessionResume } from "./SessionResume";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  api,
  date,
  projectPath,
  projectPayload,
  type ContextData,
  type Entry,
  type Project,
} from "@/lib/api/client";
import {
  Copy,
  ErrorNotice,
  Panel,
  RecordForm,
  Section,
  type Field,
} from "@/app/shared";
import type { ProjectProps } from "./Workspace";

const handoffFields: Field[] = [
  { name: "summary", title: "Session summary", kind: "area", required: true },
  { name: "completed_work", title: "Completed work", kind: "area" },
  { name: "changed_files", title: "Changed files", kind: "area" },
  {
    name: "verification",
    title: "Verification performed and results",
    kind: "area",
    hint: "State what actually ran and its result. Include failures and checks not performed.",
  },
  { name: "unresolved_problems", title: "Unresolved problems", kind: "area" },
  { name: "blockers", title: "Blockers", kind: "area" },
  {
    name: "next_actions",
    title: "Concrete next actions",
    kind: "area",
    required: true,
  },
  { name: "commit", title: "Commit reference (optional)" },
];
export function Context({
  project: p,
  actor,
  refresh,
  targetRecord,
}: ProjectProps & { targetRecord: string | null }) {
  const [form, setForm] = useState<"handoff" | "decision" | "brief" | null>(
    null,
  );
  const [snapshot, setSnapshot] = useState<Project>(p);
  const [writeKey, setWriteKey] = useState(() => crypto.randomUUID());
  const openForm = (value: "handoff" | "decision" | "brief") => {
    setSnapshot(structuredClone(p));
    setWriteKey(crypto.randomUUID());
    setForm(value);
  };
  const [history, setHistory] = useState<Entry | null>(null);
  const [requestedRecord, setRequestedRecord] = useState(targetRecord);
  const referenced = useQuery({
    queryKey: ["record", p.id, requestedRecord],
    queryFn: () =>
      api<Entry>(`${projectPath(p.id)}/records/${requestedRecord}`),
    enabled: !!requestedRecord,
  });
  const sessionReference =
    referenced.data &&
    ["session", "checkpoint", "observation"].includes(referenced.data.kind)
      ? referenced.data
      : null;
  const shownHistory = history || (sessionReference ? null : referenced.data);
  const [offset, setOffset] = useState(0);
  const [decisionOffset, setDecisionOffset] = useState(0);
  const query = useQuery({
    queryKey: ["context", p.id],
    refetchInterval: 5000,
    queryFn: () => api<ContextData>(`${projectPath(p.id)}/context`),
  });
  const handoffs = useQuery({
    queryKey: ["handoffs", p.id, offset],
    queryFn: () =>
      api<Entry[]>(`${projectPath(p.id)}/handoffs?limit=20&offset=${offset}`),
  });
  const decisions = useQuery({
    queryKey: ["decisions", p.id, decisionOffset],
    queryFn: () =>
      api<Entry[]>(
        `${projectPath(p.id)}/decisions?limit=20&offset=${decisionOffset}`,
      ),
  });
  const latest = query.data?.handoffs[0];
  const fields =
    form === "handoff"
      ? handoffFields
      : form === "decision"
        ? [
            { name: "choice", title: "Choice", required: true },
            { name: "reasoning", title: "Reasoning", kind: "area" as const },
            {
              name: "alternatives",
              title: "Alternatives considered",
              kind: "area" as const,
            },
            { name: "reference", title: "Code/commit reference" },
          ]
        : [
            { name: "brief", title: "Project brief", kind: "area" as const },
            { name: "focus", title: "Current focus", kind: "area" as const },
            { name: "next_step", title: "Next step", kind: "area" as const },
          ];
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <FileWatcher projectId={p.id} actor={actor} />
      <SessionResume
        projectId={p.id}
        actor={actor}
        refresh={refresh}
        targetSessionId={
          sessionReference ? String(sessionReference["session_id"]) : null
        }
        onCloseReference={() => setRequestedRecord(null)}
      />
      {query.error && <ErrorNotice error={query.error} />}
      {referenced.error && <ErrorNotice error={referenced.error} />}
      <section className="rounded-md border-2 border-foreground/15 bg-card p-5 md:p-7">
        <div className="flex flex-wrap justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase text-muted-foreground">
              Latest handoff {latest && `· ${date(latest.created_at)}`}
            </p>
            <h2 className="mt-2 text-xl font-semibold">Continue from here</h2>
          </div>
          {query.data && (
            <Copy text={query.data.markdown} title="Copy agent context" />
          )}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Recorded context may be stale. Inspect the repository and references
          before relying on it.
        </p>
        {query.isPending ? (
          <p className="mt-5 text-sm">Loading context…</p>
        ) : latest ? (
          <Handoff entry={latest} />
        ) : (
          <p className="mt-6 text-sm text-muted-foreground">
            No handoff yet. Next step: {p.next_step || "Not recorded"}
          </p>
        )}
        <Button className="mt-6" size="sm" onClick={() => openForm("handoff")}>
          Save session handoff
        </Button>
      </section>
      <Section title="Project brief and current focus">
        <p className="whitespace-pre-wrap text-sm leading-6">
          {p.brief || p.purpose || "No project brief recorded."}
        </p>
        <p className="whitespace-pre-wrap text-sm text-muted-foreground">
          Focus: {p.focus || "Not recorded"}
        </p>
        <p className="whitespace-pre-wrap text-sm text-muted-foreground">
          Next step: {p.next_step || "Not recorded"}
        </p>
        <Button variant="outline" size="sm" onClick={() => openForm("brief")}>
          Edit brief and focus
        </Button>
      </Section>
      <Section title="Decisions">
        <Button
          variant="outline"
          size="sm"
          onClick={() => openForm("decision")}
        >
          Record decision
        </Button>
        {decisions.error && <ErrorNotice error={decisions.error} />}
        {decisions.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No decisions recorded.
          </p>
        )}
        {decisions.data?.map((d) => (
          <details key={d.id} className="border-b py-4">
            <summary className="cursor-pointer text-sm font-medium">
              {String(d.choice)}{" "}
              <span className="ml-2 text-[11px] font-normal text-muted-foreground">
                {date(d.created_at)} · {d.actor.name}
              </span>
            </summary>
            <p className="mt-3 whitespace-pre-wrap text-sm">
              Reasoning: {String(d.reasoning || "Not recorded")}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
              Alternatives: {String(d.alternatives || "Not recorded")}
            </p>
            <p className="mt-2 font-mono text-xs">
              Reference: {String(d.reference || "Not recorded")}
            </p>
          </details>
        ))}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!decisionOffset}
            onClick={() => setDecisionOffset(Math.max(0, decisionOffset - 20))}
          >
            Newer
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={(decisions.data?.length || 0) < 20}
            onClick={() => setDecisionOffset(decisionOffset + 20)}
          >
            Older
          </Button>
        </div>
      </Section>
      <Section title="Handoff history">
        {handoffs.error && <ErrorNotice error={handoffs.error} />}
        {handoffs.data?.map((h) => (
          <button
            key={h.id}
            className="flex w-full flex-wrap items-center justify-between gap-2 rounded border p-3 text-left"
            onClick={() => setHistory(h)}
          >
            <span className="text-sm font-medium">{String(h.summary)}</span>
            <span className="text-[11px] text-muted-foreground">
              {h.actor.name} · {date(h.created_at)}
            </span>
          </button>
        ))}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Newer
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={(handoffs.data?.length || 0) < 20}
            onClick={() => setOffset(offset + 20)}
          >
            Older
          </Button>
        </div>
      </Section>
      {form && (
        <Panel
          title={
            form === "handoff"
              ? "Save session handoff"
              : form === "decision"
                ? "Record decision"
                : "Edit project context"
          }
          description={
            form === "handoff"
              ? "Handoffs are historical records. Corrections should be saved as another handoff."
              : undefined
          }
          onClose={() => setForm(null)}
        >
          <RecordForm
            fields={fields}
            initial={form === "brief" ? projectPayload(snapshot) : undefined}
            onClose={() => setForm(null)}
            onSave={async (value) => {
              if (form === "brief")
                await api(projectPath(p.id), "PUT", {
                  ...projectPayload(snapshot),
                  ...value,
                  actor,
                });
              else
                await api(
                  `${projectPath(p.id)}/${form === "decision" ? "decisions" : "handoffs"}`,
                  "POST",
                  { ...value, actor },
                  writeKey,
                );
              await refresh();
            }}
          />
        </Panel>
      )}
      {shownHistory && (
        <Panel
          title={
            shownHistory.kind === "file_observation"
              ? "Saved file observation"
              : shownHistory.kind === "handoff"
                ? "Historical handoff"
                : "Recorded decision"
          }
          description={`${date(shownHistory.created_at)} · ${shownHistory.actor.name}`}
          onClose={() => {
            setHistory(null);
            setRequestedRecord(null);
          }}
        >
          {shownHistory.kind === "file_observation" ? (
            <div className="space-y-3 text-sm">
              <p>
                Observed saved changes; task completion and verification are not
                inferred.
              </p>
              {["added", "modified", "removed"].map((key) => (
                <p key={key}>
                  <strong>{key}: </strong>
                  {Array.isArray(shownHistory[key])
                    ? (shownHistory[key] as string[]).join(", ")
                    : "Not recorded"}
                </p>
              ))}
            </div>
          ) : shownHistory.kind === "handoff" ? (
            <Handoff entry={shownHistory} />
          ) : (
            <div className="space-y-4">
              <h3 className="font-semibold">{String(shownHistory.choice)}</h3>
              <p className="whitespace-pre-wrap text-sm">
                {String(shownHistory.reasoning || "No reasoning recorded")}
              </p>
              <p className="whitespace-pre-wrap text-sm">
                Alternatives:{" "}
                {String(shownHistory.alternatives || "Not recorded")}
              </p>
              <p className="font-mono text-xs">
                {String(shownHistory.reference || "No code reference")}
              </p>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
function Handoff({ entry }: { entry: Entry }) {
  return (
    <div className="mt-6 space-y-4">
      <p className="whitespace-pre-wrap text-sm font-medium">
        {String(entry.summary)}
      </p>
      <div className="grid gap-5 md:grid-cols-2">
        {handoffFields
          .filter((f) => !["summary", "commit"].includes(f.name))
          .map((f) => (
            <div key={f.name} className="border-l-2 pl-4">
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">
                {f.title}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6">
                {String(
                  entry[f.name] ||
                    (f.name === "verification"
                      ? "No verification recorded."
                      : "Not recorded"),
                )}
              </p>
            </div>
          ))}
      </div>
      <p className="border-t pt-3 text-[11px] text-muted-foreground">
        {entry.actor.name} ({entry.actor.kind}) · {date(entry.created_at)} ·
        Commit {String(entry.commit || "not recorded")}
      </p>
    </div>
  );
}
