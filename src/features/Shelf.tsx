import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Clock3,
  FolderOpen,
  Grid2X2,
  Inbox,
  LayoutList,
  PauseCircle,
  PlayCircle,
  Plus,
  Search,
  Settings as SettingsIcon,
  Tag,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  date,
  label,
  type Actor,
  type Candidate,
  type Page,
  type Project,
  type Settings,
} from "@/lib/api/client";
import {
  Badge,
  Brand,
  ErrorNotice,
  Pager,
  Panel,
  Preview,
  RecordForm,
} from "@/app/shared";

export function Shelf({
  settings,
  actor,
  refresh,
  onOpen,
}: {
  settings: Settings;
  actor: Actor;
  refresh: () => Promise<void>;
  onOpen: (id: string, mode?: "new" | "existing") => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState("recent");
  const [view, setView] = useState("grid");
  const [sidebar, setSidebar] = useState(true);
  const [dialog, setDialog] = useState<"add" | "settings" | null>(null);
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    q: query,
    status: ["active", "paused", "archived"].includes(filter) ? filter : "",
    opened: String(filter === "opened"),
    tag,
    sort: filter === "opened" ? "opened" : sort,
    offset: String(offset),
  });
  const list = useQuery({
    queryKey: ["projects", params.toString()],
    queryFn: () => api<Page<Project>>(`/projects?${params}`),
  });
  const summary = useQuery({
    queryKey: ["shelf-summary"],
    queryFn: () =>
      api<{
        total: number;
        statuses: Record<string, number>;
        tags: string[];
        opened: number;
      }>("/shelf-summary"),
  });
  const changeFilter = (value: string) => {
    setFilter(value);
    setOffset(0);
  };
  const nav = [
    { value: "all", title: "All projects", icon: Inbox },
    { value: "opened", title: "Recently opened", icon: Clock3 },
    { value: "active", title: "Active", icon: PlayCircle },
    { value: "paused", title: "Paused", icon: PauseCircle },
    { value: "archived", title: "Archived", icon: Archive },
  ];
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b bg-background px-4 md:px-6">
        <Brand />
        <div className="relative mx-auto hidden w-full max-w-xl md:block">
          <Search className="absolute left-3 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            aria-label="Search projects"
            placeholder="Search projects…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
            className="h-8 bg-muted/60 pl-9"
          />
        </div>
        <div className="ml-auto flex gap-2">
          <Button size="sm" onClick={() => setDialog("add")}>
            <Plus className="size-4" /> Add project
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Settings"
            onClick={() => setDialog("settings")}
          >
            <SettingsIcon className="size-4" />
          </Button>
        </div>
      </header>
      <div className="border-b p-3 md:hidden">
        <Input
          placeholder="Search projects…"
          aria-label="Search projects"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
      </div>
      <div className="flex">
        <aside
          className={`hidden min-h-[calc(100vh-56px)] shrink-0 border-r bg-sidebar p-2 md:block ${sidebar ? "w-56" : "w-14"}`}
        >
          <Button
            aria-label="Toggle sidebar"
            variant="ghost"
            size="icon"
            onClick={() => setSidebar(!sidebar)}
          >
            {sidebar ? <PanelLeftClose /> : <PanelLeftOpen />}
          </Button>
          <nav className="mt-3 space-y-1">
            {nav.map((n) => (
              <Button
                key={n.value}
                title={n.title}
                variant="ghost"
                className={`h-8 w-full justify-start px-2 text-xs ${filter === n.value ? "bg-accent" : ""}`}
                onClick={() => changeFilter(n.value)}
              >
                <n.icon className="size-4" />
                {sidebar && (
                  <>
                    <span>{n.title}</span>
                    <span className="ml-auto text-[10px]">
                      {n.value === "all"
                        ? summary.data?.total
                        : n.value === "opened"
                          ? summary.data?.opened
                          : summary.data?.statuses[n.value]}
                    </span>
                  </>
                )}
              </Button>
            ))}
          </nav>
          {sidebar && (
            <>
              <p className="mt-6 px-2 text-[10px] font-semibold uppercase text-muted-foreground">
                Tags
              </p>
              <button
                className="mt-2 px-2 text-xs underline"
                onClick={() => {
                  setTag("");
                  setOffset(0);
                }}
              >
                All tags
              </button>
              {summary.data?.tags.map((t) => (
                <Button
                  key={t}
                  variant="ghost"
                  className={`h-8 w-full justify-start px-2 text-xs ${tag === t ? "bg-accent" : ""}`}
                  onClick={() => {
                    setTag(t);
                    setOffset(0);
                  }}
                >
                  <Tag className="size-3.5" />
                  {t}
                </Button>
              ))}
              <div className="mt-8 border-t px-2 pt-4 text-[11px] text-muted-foreground">
                <p className="break-all">
                  {settings.master_folder || "No master folder configured"}
                </p>
                <button
                  className="mt-2 underline"
                  onClick={() => setDialog("settings")}
                >
                  Configure folders
                </button>
              </div>
            </>
          )}
        </aside>
        <main className="min-w-0 flex-1 px-4 py-7 md:px-8 lg:px-10">
          <div className="mx-auto max-w-7xl">
            <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-5">
              <div>
                <p className="text-xs text-muted-foreground">Your workspace</p>
                <h1 className="mt-1 text-2xl font-semibold">
                  {nav.find((n) => n.value === filter)?.title}
                  {tag && ` · ${tag}`}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {list.data?.total ?? "…"} projects
                </p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  aria-label="Filter projects"
                  className="stash-input md:hidden"
                  value={filter}
                  onChange={(e) => changeFilter(e.target.value)}
                >
                  {nav.map((n) => (
                    <option key={n.value} value={n.value}>
                      {n.title}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Sort projects"
                  className="stash-input"
                  value={sort}
                  onChange={(e) => {
                    setSort(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="recent">Recent activity</option>
                  <option value="name">Name</option>
                  <option value="added">Date added</option>
                </select>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Grid view"
                  onClick={() => setView("grid")}
                  className={view === "grid" ? "bg-accent" : ""}
                >
                  <Grid2X2 className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="List view"
                  onClick={() => setView("list")}
                  className={view === "list" ? "bg-accent" : ""}
                >
                  <LayoutList className="size-4" />
                </Button>
              </div>
            </div>
            {list.isPending && (
              <p className="mt-8 text-sm">Loading projects…</p>
            )}
            {list.error && (
              <ErrorNotice
                error={list.error}
                retry={() => void list.refetch()}
              />
            )}
            {list.data?.total === 0 && (
              <div className="mx-auto mt-20 max-w-lg text-center">
                <FolderOpen className="mx-auto size-9 text-muted-foreground" />
                <h2 className="mt-5 text-lg font-semibold">
                  {query || tag || filter !== "all"
                    ? "No matching projects"
                    : "No projects on this shelf"}
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  {query || tag || filter !== "all"
                    ? "Try clearing your search and filters."
                    : "Discover projects in a master folder or register an existing directory. Your files stay where they are."}
                </p>
                <div className="mt-6 flex justify-center gap-2">
                  {query || tag || filter !== "all" ? (
                    <Button
                      onClick={() => {
                        setQuery("");
                        setTag("");
                        changeFilter("all");
                      }}
                    >
                      Clear filters
                    </Button>
                  ) : (
                    <>
                      <Button onClick={() => setDialog("settings")}>
                        Choose master folder
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setDialog("add")}
                      >
                        Register project
                      </Button>
                    </>
                  )}
                </div>
              </div>
            )}
            <div
              className={
                view === "grid"
                  ? "mt-7 grid gap-5 sm:grid-cols-2 xl:grid-cols-3"
                  : "mt-7 space-y-2"
              }
            >
              {list.data?.items.map((p) => (
                <button
                  key={p.id}
                  onClick={() => onOpen(p.id)}
                  className={`overflow-hidden rounded-md border bg-card text-left transition hover:border-foreground/40 ${view === "list" ? "flex flex-wrap items-center justify-between gap-4 p-4" : ""}`}
                >
                  {view === "grid" && (
                    <Preview
                      name={p.name}
                      image={
                        p.screenshot
                          ? `/api/v1/projects/${p.id}/screenshot`
                          : undefined
                      }
                    />
                  )}
                  <div className={view === "grid" ? "p-4" : "min-w-0"}>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-semibold">{p.name}</h2>
                      <Badge value={p.status} />
                      {p.availability !== "available" && (
                        <Badge value={p.availability} />
                      )}
                    </div>
                    <p className="mt-3 text-sm text-muted-foreground">
                      {p.description ||
                        "Add a description in the project overview."}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {[...p.stack, ...p.tags].map((t, i) => (
                        <span
                          key={`${t}-${i}`}
                          className="rounded border bg-muted/60 px-1.5 py-0.5 font-mono text-[10px]"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <div className="mt-4 border-t pt-3">
                      <p className="text-xs">
                        <span className="text-muted-foreground">Next:</span>{" "}
                        {p.next_step || "Not recorded"}
                      </p>
                      <div className="mt-2 flex flex-wrap justify-between gap-2 text-[11px] text-muted-foreground">
                        <span>{p.open_issue_count} open issues</span>
                        <span title={date(p.last_activity_at)}>
                          {label(p.activity_source)} ·{" "}
                          {date(p.last_activity_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            {list.data && (
              <Pager
                offset={offset}
                total={list.data.total}
                onChange={setOffset}
              />
            )}
          </div>
        </main>
      </div>
      {dialog === "settings" && (
        <SettingsPanel
          settings={settings}
          actor={actor}
          refresh={refresh}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "add" && (
        <RegistrationPanel
          settings={settings}
          actor={actor}
          refresh={refresh}
          onRegistered={(id, mode) => {
            setDialog(null);
            onOpen(id, mode);
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

function SettingsPanel({
  settings,
  actor,
  refresh,
  onClose,
}: {
  settings: Settings;
  actor: Actor;
  refresh: () => Promise<void>;
  onClose: () => void;
}) {
  const [snapshot] = useState(() => structuredClone(settings));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Panel
      title="Settings"
      description="Manage local project discovery and your update identity."
      onClose={onClose}
    >
      <RecordForm
        initial={snapshot}
        fields={[
          {
            name: "master_folder",
            title: "Master folder",
            hint: "Absolute directory path; only immediate subdirectories are discovered.",
          },
          { name: "identity", title: "Your name", required: true },
        ]}
        onClose={onClose}
        onSave={async (value) => {
          await api("/settings", "PUT", {
            ...value,
            revision: snapshot.revision,
            actor,
          });
          await refresh();
        }}
      />
      <div className="mt-6 border-t pt-4">
        <Button
          variant="outline"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api("/rescan", "POST", { actor });
              await refresh();
            } catch (e) {
              setError(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Scanning…" : "Rescan registered projects"}
        </Button>
        <p className="mt-2 text-xs text-muted-foreground">
          Refresh availability and code observations. Descriptions and context
          are preserved.
        </p>
        {error != null && <ErrorNotice error={error} />}
      </div>
    </Panel>
  );
}

function RegistrationPanel({
  settings,
  actor,
  refresh,
  onClose,
  onRegistered,
}: {
  settings: Settings;
  actor: Actor;
  refresh: () => Promise<void>;
  onClose: () => void;
  onRegistered: (id: string, mode: "new" | "existing") => void;
}) {
  const candidates = useQuery({
    queryKey: ["candidates", settings.master_folder],
    queryFn: () => api<Candidate[]>("/discover"),
    enabled: !!settings.master_folder,
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("existing");
  const register = async (path: string) => {
    const project = await api<Project>(
      mode === "new" ? "/projects/create" : "/projects",
      "POST",
      { path, actor },
    );
    await refresh();
    onRegistered(project.id, mode === "new" ? "new" : "existing");
  };
  return (
    <Panel
      title="Add project"
      description="Choose a folder, then initialize its context and tracking."
      onClose={onClose}
    >
      <label className="mb-4 block text-sm">
        Project kind{" "}
        <select
          className="ml-2 rounded border bg-background p-2"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="existing">Existing folder</option>
          <option value="new">Create new folder</option>
        </select>
      </label>
      <RecordForm
        fields={[
          {
            name: "path",
            title: mode === "new" ? "New folder path" : "Existing project path",
            required: true,
            hint: "For example: /home/ben/Projects/HLD210/vibe-wise",
          },
        ]}
        saveLabel={
          mode === "new" ? "Create and initialize" : "Register project"
        }
        onClose={onClose}
        onSave={async (value) => {
          await register(String(value["path"]));
        }}
      />
      {settings.master_folder && mode === "existing" && (
        <div className="mt-6 space-y-3">
          <div className="flex justify-between">
            <h2 className="text-sm font-semibold">Discovered projects</h2>
            <button
              className="text-xs underline"
              onClick={() => void candidates.refetch()}
            >
              Rescan
            </button>
          </div>
          {candidates.isPending && <p className="text-xs">Scanning…</p>}
          {candidates.error && <ErrorNotice error={candidates.error} />}
          {candidates.data?.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No candidate directories found.
            </p>
          )}
          {candidates.data?.map((c) => (
            <div
              key={c.path}
              className="flex items-center justify-between gap-3 rounded border p-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{c.name}</p>
                <p className="break-all text-[11px] text-muted-foreground">
                  {c.path}
                </p>
                {c.error && (
                  <p className="text-xs text-destructive">{c.error}</p>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={!!c.project_id || !!c.error || busy}
                onClick={async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    await register(c.path);
                  } catch (e) {
                    setError(e);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {c.project_id ? "Registered" : "Add"}
              </Button>
            </div>
          ))}
        </div>
      )}
      {error != null && <ErrorNotice error={error} />}
    </Panel>
  );
}
