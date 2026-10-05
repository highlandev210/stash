import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Actor, type Settings } from "@/lib/api/client";
import { ErrorNotice } from "./shared";
import { Shelf } from "@/features/Shelf";
import { Workspace } from "@/features/Workspace";

export default function App() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectMode, setProjectMode] = useState<"new" | "existing">(
    "existing",
  );
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const actor: Actor = {
    name: settings.data?.identity || "You",
    kind: "human",
  };
  const refresh = async () => {
    await client.invalidateQueries();
  };
  if (settings.isPending)
    return <main className="p-10 text-sm">Connecting to stash…</main>;
  if (settings.error || !settings.data)
    return (
      <main className="mx-auto max-w-2xl p-10">
        <h1 className="text-xl font-semibold">stash</h1>
        <ErrorNotice
          error={settings.error}
          retry={() => void settings.refetch()}
        />
        <p className="text-sm text-muted-foreground">
          Start the backend with <code>npm run dev:api</code>, then retry.
        </p>
      </main>
    );
  return (
    <>
      <div hidden={!!projectId}>
        <Shelf
          settings={settings.data}
          actor={actor}
          refresh={refresh}
          onOpen={(id, mode) => {
            setProjectMode(mode || "existing");
            setProjectId(id);
            void api(`/projects/${id}/opened`, "POST", { actor })
              .then(refresh)
              .catch(() => {});
          }}
        />
      </div>
      {projectId && (
        <Workspace
          id={projectId}
          initialMode={projectMode}
          actor={actor}
          refresh={refresh}
          onBack={() => {
            setProjectId(null);
            void refresh();
          }}
        />
      )}
    </>
  );
}
