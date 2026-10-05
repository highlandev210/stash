import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  api,
  date,
  projectPath,
  type Actor,
  type Project,
} from "@/lib/api/client";
import { Badge, Brand, Copy, ErrorNotice } from "@/app/shared";
import { Assessment } from "./Assessment";
import { Overview } from "./Overview";
import { Docs } from "./Docs";
import { Issues } from "./Issues";
import { Context } from "./Context";
import { ActivityView } from "./Activity";

const tabs = ["Overview", "Docs", "Issues", "Context", "Activity"] as const;
export type Tab = (typeof tabs)[number];
export type ProjectProps = {
  project: Project;
  actor: Actor;
  refresh: () => Promise<void>;
};
export function Workspace({
  id,
  initialMode = "existing",
  actor,
  refresh,
  onBack,
}: {
  id: string;
  initialMode?: "new" | "existing";
  actor: Actor;
  refresh: () => Promise<void>;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<Tab>("Overview");
  const [targetIssue, setTargetIssue] = useState<string | null>(null);
  const [targetRecord, setTargetRecord] = useState<string | null>(null);
  const [targetDoc, setTargetDoc] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["project", id],
    queryFn: () => api<Project>(projectPath(id)),
  });
  const project = query.data;
  if (!project)
    return (
      <main className="p-8">
        <Button variant="outline" onClick={onBack}>
          Back to shelf
        </Button>
        {query.isPending ? (
          <p className="mt-4">Loading project…</p>
        ) : (
          <ErrorNotice error={query.error} retry={() => void query.refetch()} />
        )}
      </main>
    );
  const props = { project, actor, refresh };
  const jump = (next: Tab, record?: string) => {
    if (next === "Issues") setTargetIssue(record || null);
    setTargetRecord(next === "Context" ? record || null : null);
    setTargetDoc(next === "Docs" ? record || null : null);
    setTab(next);
  };
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background">
        <div className="flex h-12 items-center gap-3 px-4 md:px-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={onBack}
            aria-label="Back to projects"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <Brand />
          <div className="ml-auto">
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await api(`${projectPath(id)}/refresh`, "POST", { actor });
                  await refresh();
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <RefreshCw className="size-3.5" />
              {busy ? "Refreshing…" : "Refresh observations"}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3 md:px-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold">{project.name}</h1>
              <Badge value={project.status} />
              {project.availability !== "available" && (
                <Badge value={project.availability} />
              )}
            </div>
            <div className="mt-1 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
              <span className="break-all">{project.path}</span>
              {project.repo_url && (
                <a
                  href={project.repo_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1"
                >
                  Repository <ExternalLink className="size-3" />
                </a>
              )}
            </div>
          </div>
          <Copy text={project.path} title="Copy path" />
        </div>
        <nav className="flex gap-6 overflow-x-auto px-4 md:px-6">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => jump(t)}
              className={`h-10 whitespace-nowrap border-b-2 text-xs font-medium ${tab === t ? "border-foreground text-foreground" : "border-transparent text-muted-foreground"}`}
            >
              {t}
              {t === "Issues" && (
                <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[9px]">
                  {project.open_issue_count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 md:px-8">
        {error != null && <ErrorNotice error={error} />}
        {project.availability !== "available" && (
          <div className="mb-5 rounded border bg-muted p-4 text-sm">
            Directory {project.availability}. Tracker records are retained.
            Update its path in Overview if it moved.
            <p className="mt-1 text-xs text-muted-foreground">
              {project.storage_error || project.observations.error}
            </p>
          </div>
        )}
        <p className="mb-5 text-[11px] text-muted-foreground">
          Filesystem/Git last checked: {date(project.observations.observed_at)}
        </p>
        {tab === "Overview" && (
          <>
            <Assessment {...props} initialMode={initialMode} />
            <Overview {...props} jump={jump} onRemoved={onBack} />
          </>
        )}
        {tab === "Docs" && (
          <Docs key={targetDoc || "docs"} {...props} targetDoc={targetDoc} />
        )}
        {tab === "Issues" && (
          <Issues
            key={targetIssue || "issues"}
            {...props}
            targetIssue={targetIssue}
          />
        )}
        {tab === "Context" && (
          <Context
            key={targetRecord || "context"}
            {...props}
            targetRecord={targetRecord}
          />
        )}
        {tab === "Activity" && <ActivityView {...props} jump={jump} />}
      </main>
    </div>
  );
}
