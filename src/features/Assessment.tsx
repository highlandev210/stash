import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, projectPath } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/app/shared";
import type { ProjectProps } from "./Workspace";

type Candidate = {
  id: string;
  title: string;
  description: string;
  evidence: string;
  confidence: string;
  existing_issue_id: string | null;
};
type Report = {
  id: string;
  revision: string;
  created_at: string;
  status: string;
  needs_goal: boolean;
  goal: string;
  mode: "new" | "existing";
  requirements: string[];
  proposed: Record<string, string | string[]>;
  candidates: Candidate[];
  warnings: string[];
  checks: {
    name: string;
    status: string;
    evidence: string;
    exit_code?: number;
  }[];
  evidence: { path: string; kind: string }[];
  available_checks: string[];
};

export function Assessment({
  project,
  actor,
  refresh,
  initialMode = "existing",
}: ProjectProps & { initialMode?: "new" | "existing" }) {
  const base = projectPath(project.id);
  const history = useQuery({
    queryKey: ["assessments", project.id],
    queryFn: () => api<Report[]>(`${base}/assessments`),
  });
  const [mode, setMode] = useState<"new" | "existing">(initialMode);
  const [goal, setGoal] = useState(project.purpose || "");
  const [requirements, setRequirements] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [fields, setFields] = useState<string[]>([]);
  const [issues, setIssues] = useState<string[]>([]);
  const [checks, setChecks] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string | string[]>>({});
  const [analysis, setAnalysis] = useState("");
  const [watcher, setWatcher] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const toggle = (items: string[], value: string) =>
    items.includes(value)
      ? items.filter((x) => x !== value)
      : [...items, value];
  const inspect = async (runChecks: string[] = []) => {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const data = await api<Report>(`${base}/assessments`, "POST", {
        mode,
        goal,
        requirements: requirements
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean),
        run_checks: runChecks,
        actor,
      });
      setReport(data);
      setEdits(data.proposed);
      setAnalysis("");
      setIssues([]);
      setChecks([]);
      setFields(
        Object.keys(data.proposed).filter(
          (key) => !project[key as keyof typeof project],
        ),
      );
      await history.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="mb-6 space-y-4 rounded-lg border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {history.data?.some((x) => x.status === "accepted")
              ? "Reassess project"
              : "Initialize project"}
          </h2>
          <p className="text-sm text-muted-foreground">
            Establish context, review evidence and choose what to track.
          </p>
        </div>
        <select
          aria-label="Project kind"
          className="rounded border bg-background p-2"
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        >
          <option value="existing">Existing repository</option>
          <option value="new">New project</option>
        </select>
      </div>
      <label className="block text-sm">
        What should this project do?
        <textarea
          className="mt-1 w-full rounded border bg-background p-2"
          rows={2}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Who is it for, and what should it accomplish?"
        />
      </label>
      <label className="block text-sm">
        Requirements and initial tasks (one per line)
        <textarea
          className="mt-1 w-full rounded border bg-background p-2"
          rows={3}
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
        />
      </label>
      <Button disabled={busy} onClick={() => void inspect()}>
        {busy
          ? "Assessing…"
          : report
            ? "Refresh assessment"
            : "Inspect project"}
      </Button>
      <p className="text-xs text-muted-foreground">
        Inspection reads bounded source and documentation, existing memory and
        Git state. It checks manifest and Python syntax. Repository commands run
        only when selected below.
      </p>
      {error != null && <ErrorNotice error={error} />}
      {done && (
        <p role="status">
          Assessment saved. Context and selected issues are ready; tracking
          settings have been applied.
        </p>
      )}
      {report && !done && (
        <div className="space-y-4 border-t pt-4">
          {report.warnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-600">
              {w}
            </p>
          ))}
          <h3 className="font-semibold">Review context changes</h3>
          <p className="text-xs text-muted-foreground">
            Existing text is retained unless you select its replacement.
            Inferred summaries require review.
          </p>
          {Object.entries(report.proposed).map(([key, value]) => (
            <div key={key} className="rounded border p-3">
              <label className="flex gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={fields.includes(key)}
                  onChange={() => setFields(toggle(fields, key))}
                />
                {key.replaceAll("_", " ")}
              </label>
              {!!project[key as keyof typeof project] && (
                <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">
                  Current: {String(project[key as keyof typeof project])}
                </p>
              )}
              <textarea
                aria-label={`Proposed ${key.replaceAll("_", " ")}`}
                className="mt-2 w-full rounded border bg-background p-2 text-sm"
                rows={key === "brief" ? 10 : 2}
                value={
                  Array.isArray(edits[key] ?? value)
                    ? ((edits[key] as string[]) ?? (value as string[])).join(
                        ", ",
                      )
                    : String(edits[key] ?? value)
                }
                onChange={(e) =>
                  setEdits({
                    ...edits,
                    [key]: Array.isArray(value)
                      ? e.target.value
                          .split(",")
                          .map((x) => x.trim())
                          .filter(Boolean)
                      : e.target.value,
                  })
                }
              />
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                const refined = await api<Report>(
                  `${base}/assessments/${report.id}`,
                  "PUT",
                  { revision: report.revision, proposed: edits, actor },
                );
                setReport(refined);
                await history.refetch();
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            Save context corrections to draft
          </Button>
          <h3 className="font-semibold">Review issue candidates</h3>
          {report.candidates.length === 0 && (
            <p className="text-sm">
              No supported candidates found in this inspection. This does not
              establish that the project is bug-free.
            </p>
          )}
          {report.candidates.map((c) => (
            <label key={c.id} className="block rounded border p-3 text-sm">
              <input
                type="checkbox"
                className="mr-2"
                checked={issues.includes(c.id)}
                onChange={() => setIssues(toggle(issues, c.id))}
              />
              {c.title}
              <span className="ml-2 text-xs text-muted-foreground">
                {c.existing_issue_id ? "Link existing issue" : c.confidence}
              </span>
              <p className="mt-1">{c.description}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Evidence: {c.evidence}
              </p>
            </label>
          ))}
          <details>
            <summary className="cursor-pointer text-sm">
              Inspection and verification evidence
            </summary>
            <ul className="mt-2 space-y-1 text-xs">
              {report.checks.map((c, i) => (
                <li key={i}>
                  {c.name}: {c.status}
                  {c.exit_code !== undefined && ` (exit ${c.exit_code})`}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs">
              Files inspected: {report.evidence.map((e) => e.path).join(", ")}
            </p>
          </details>
          {!!report.available_checks.length && (
            <div className="space-y-2 rounded border p-3">
              <h3 className="text-sm font-semibold">Run repository checks</h3>
              <p className="text-xs text-muted-foreground">
                These execute project code and may write build or test files.
                Each command has a 60-second limit. Results generate a fresh
                assessment.
              </p>
              {report.available_checks.map((c) => (
                <label key={c} className="mr-4 inline-block text-sm">
                  <input
                    type="checkbox"
                    checked={checks.includes(c)}
                    onChange={() => setChecks(toggle(checks, c))}
                  />{" "}
                  {c}
                </label>
              ))}
              <Button
                size="sm"
                variant="outline"
                disabled={busy || checks.length === 0}
                onClick={() => void inspect(checks)}
              >
                Run selected checks and reassess
              </Button>
            </div>
          )}
          <details>
            <summary className="cursor-pointer text-sm">
              Add coding-agent analysis
            </summary>
            <p className="my-2 text-xs">
              Use the stash skill to inspect architecture, features and bugs.
              Paste its refinement JSON here (proposed context, analysis and
              findings with project file references). Findings are added to this
              review; existing issues are preserved.
            </p>
            <textarea
              aria-label="Agent analysis JSON"
              className="w-full rounded border bg-background p-2 text-xs"
              rows={6}
              value={analysis}
              onChange={(e) => setAnalysis(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !analysis.trim()}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  const incoming = JSON.parse(analysis);
                  const refined = await api<Report>(
                    `${base}/assessments/${report.id}`,
                    "PUT",
                    {
                      ...incoming,
                      revision: report.revision,
                      actor: { name: "Imported coding agent", kind: "agent" },
                    },
                  );
                  setReport(refined);
                  setEdits(refined.proposed);
                  setAnalysis("");
                  await history.refetch();
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Import analysis for review
            </Button>
          </details>
          <label className="block text-sm">
            <input
              type="checkbox"
              checked={watcher}
              onChange={(e) => setWatcher(e.target.checked)}
            />{" "}
            Track saved file changes while stash runs
          </label>
          <p className="text-xs text-muted-foreground">
            File tracking starts from this baseline. For explanations and
            session progress, use Context checkpoints or the optional stash
            coding-agent skill and hooks.
          </p>
          <Button
            disabled={
              busy ||
              report.needs_goal ||
              JSON.stringify(edits) !== JSON.stringify(report.proposed)
            }
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await api(`${base}/assessments/${report.id}/approve`, "POST", {
                  revision: report.revision,
                  fields,
                  candidates: issues,
                  enable_watcher: watcher,
                  actor,
                });
                setDone(true);
                await refresh();
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            Accept selected context and issues
          </Button>
        </div>
      )}
      {!!history.data?.length && (
        <details>
          <summary className="cursor-pointer text-sm">
            Assessment history ({history.data.length})
          </summary>
          {history.data.map((r) => (
            <div key={r.id} className="mt-2 rounded border p-3 text-xs">
              <p>
                {new Date(r.created_at).toLocaleString()} · {r.status} ·{" "}
                {r.goal || "Goal inferred from documentation"}
              </p>
              {r.status === "accepted" && (
                <details className="mt-2">
                  <summary>Accepted context and evidence</summary>
                  <p className="whitespace-pre-wrap">
                    {String(r.proposed["brief"] || "")}
                  </p>
                  <ul>
                    {r.checks.map((c, i) => (
                      <li key={i}>
                        {c.name}: {c.status}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {r.status === "draft" && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setReport(r);
                    setEdits(r.proposed);
                    setGoal(r.goal);
                    setMode(r.mode);
                    setRequirements(r.requirements.join("\n"));
                    setFields([]);
                    setIssues([]);
                    setDone(r.status === "accepted");
                  }}
                >
                  Review draft
                </Button>
              )}
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
