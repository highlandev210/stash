import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, projectPath, type Actor } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/app/shared";

type State = {
  enabled: boolean;
  checked_at: string | null;
  complete: boolean | null;
  warnings: string[];
};
type Change = {
  id: string;
  observed_at: string;
  added: string[];
  modified: string[];
  removed: string[];
  complete: boolean;
  warnings: string[];
};
export function FileWatcher({
  projectId,
  actor,
}: {
  projectId: string;
  actor: Actor;
}) {
  const base = projectPath(projectId);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const state = useQuery({
    queryKey: ["watcher", projectId],
    queryFn: () => api<State>(`${base}/watcher`),
    refetchInterval: 5000,
  });
  const changes = useQuery({
    queryKey: ["file-observations", projectId],
    queryFn: () => api<Change[]>(`${base}/file-observations`),
    refetchInterval: 5000,
  });
  return (
    <section className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Saved file observations</h2>
        <Button
          size="sm"
          variant="outline"
          disabled={!state.data || saving}
          onClick={async () => {
            setSaving(true);
            setError(null);
            try {
              await api(`${base}/watcher`, "PUT", {
                enabled: !state.data?.enabled,
                actor,
              });
              await state.refetch();
            } catch (e) {
              setError(e);
            } finally {
              setSaving(false);
            }
          }}
        >
          {state.data?.enabled ? "Disable watcher" : "Enable watcher"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Optional polling while stash runs. File changes are observations, not
        task completion or verification.
      </p>
      {(error || state.error || changes.error) && (
        <ErrorNotice error={error || state.error || changes.error} />
      )}
      {state.data?.enabled && (
        <p className="text-xs">
          Last scan:{" "}
          {state.data.checked_at
            ? date(state.data.checked_at)
            : "Waiting for first scan"}
          {state.data.complete === false ? " · Partial scan" : ""}
        </p>
      )}
      {state.data?.warnings?.map((warning) => (
        <p className="text-xs" key={warning}>
          {warning}
        </p>
      ))}
      <details>
        <summary className="cursor-pointer text-sm">
          File change history
        </summary>
        {Array.isArray(changes.data) &&
          changes.data.map((change) => (
            <div
              key={change.id}
              className="mt-3 space-y-1 border-t pt-2 text-xs"
            >
              <p>
                {date(change.observed_at)}
                {!change.complete && " · Partial scan"}
              </p>
              {(["added", "modified", "removed"] as const).map(
                (kind) =>
                  change[kind].length > 0 && (
                    <p key={kind}>
                      <strong>{kind}: </strong>
                      {change[kind].join(", ")}
                    </p>
                  ),
              )}
            </div>
          ))}
      </details>
    </section>
  );
}
