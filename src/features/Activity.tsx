import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { UserRound, WandSparkles } from "lucide-react";
import {
  api,
  date,
  label,
  projectPath,
  type Activity,
  type Page,
} from "@/lib/api/client";
import { ErrorNotice, Pager } from "@/app/shared";
import type { ProjectProps, Tab } from "./Workspace";
export function ActivityView({
  project,
  jump,
}: ProjectProps & { jump: (tab: Tab, record?: string) => void }) {
  const [actor, setActor] = useState("");
  const [kind, setKind] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    actor,
    kind,
    since: since ? `${since}T00:00:00` : "",
    until: until ? `${until}T23:59:59.999999` : "",
    offset: String(offset),
  });
  const events = useQuery({
    queryKey: ["activity", project.id, params.toString()],
    refetchInterval: 5000,
    queryFn: () =>
      api<Page<Activity>>(`${projectPath(project.id)}/activity?${params}`),
  });
  return (
    <div className="mx-auto max-w-3xl">
      <h2 className="text-base font-semibold">Activity</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Tracker updates by humans and agents. Git history remains in the
        repository.
      </p>
      <div className="my-5 flex flex-wrap gap-2">
        <select
          className="stash-input w-auto"
          aria-label="Actor filter"
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All actors</option>
          <option value="human">Human</option>
          <option value="agent">Agent</option>
        </select>
        <select
          className="stash-input w-auto"
          aria-label="Activity type filter"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All events</option>
          {[
            "registration",
            "metadata",
            "issue",
            "comment",
            "decision",
            "handoff",
            "document",
            "session",
            "checkpoint",
            "observation",
            "file_observation",
            "watcher",
            "assessment",
          ].map((v) => (
            <option key={v} value={v}>
              {label(v)}
            </option>
          ))}
        </select>
        <label className="text-xs">
          From
          <input
            type="date"
            className="stash-input"
            value={since}
            onChange={(e) => {
              setSince(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="text-xs">
          Until
          <input
            type="date"
            className="stash-input"
            value={until}
            onChange={(e) => {
              setUntil(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      {events.isPending && <p className="text-sm">Loading activity…</p>}
      {events.error && <ErrorNotice error={events.error} />}
      {events.data?.total === 0 && (
        <p className="text-sm text-muted-foreground">
          No matching tracker activity.
        </p>
      )}
      <div className="space-y-6">
        {events.data?.items.map((e) => (
          <div key={e.id} className="flex gap-4">
            <span
              className={`grid size-8 shrink-0 place-items-center rounded-full border ${e.actor.kind === "agent" ? "bg-agent text-agent-foreground" : "bg-background"}`}
            >
              {e.actor.kind === "agent" ? (
                <WandSparkles className="size-3.5" />
              ) : (
                <UserRound className="size-3.5" />
              )}
            </span>
            <div>
              <p className="text-sm">
                <span className="font-semibold">{e.actor.name}</span> ·{" "}
                {e.summary}
              </p>
              <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                <button
                  className="underline"
                  onClick={() =>
                    jump(
                      e.kind === "assessment"
                        ? "Overview"
                        : e.kind === "issue" || e.kind === "comment"
                          ? "Issues"
                          : [
                                "decision",
                                "handoff",
                                "session",
                                "checkpoint",
                                "observation",
                                "file_observation",
                                "watcher",
                                "assessment",
                              ].includes(e.kind)
                            ? "Context"
                            : e.kind === "document"
                              ? "Docs"
                              : "Overview",
                      e.kind === "watcher" ? undefined : e.record_id,
                    )
                  }
                >
                  {label(e.kind)} · {e.record_id.slice(0, 10)}
                </button>
                <span>{date(e.created_at)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
      {events.data && (
        <Pager offset={offset} total={events.data.total} onChange={setOffset} />
      )}
    </div>
  );
}
