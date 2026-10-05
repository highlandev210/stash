import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, ApiError, projectPath, type Document } from "@/lib/api/client";
import { ErrorNotice, Panel, RecordForm } from "@/app/shared";
import type { ProjectProps } from "./Workspace";

const isstashNote = (path: string) =>
  /^\.stash\/(docs|decisions|handoffs)\//.test(path) &&
  !path.split("/").some((part) => part === ".." || part === ".") &&
  !path.includes("\\");

export function Docs({
  project,
  actor,
  refresh,
  targetDoc,
}: ProjectProps & { targetDoc: string | null }) {
  const [selected, setSelected] = useState(
    targetDoc && isstashNote(targetDoc) ? targetDoc : "",
  );
  const [source, setSource] = useState(false);
  const [draft, setDraft] = useState<{
    path: string;
    content: string;
    revision: string;
  } | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const tree = useQuery({
    queryKey: ["docs", project.id],
    queryFn: () =>
      api<{ files: string[]; missing_roots: string[] }>(
        `${projectPath(project.id)}/docs`,
      ),
  });
  const files = (tree.data?.files || []).filter(isstashNote);
  const path = selected || files[0] || "";
  const doc = useQuery({
    queryKey: ["document", project.id, path],
    queryFn: () =>
      api<Document>(
        `${projectPath(project.id)}/document?path=${encodeURIComponent(path)}`,
      ),
    enabled: !!path,
    refetchInterval: 10000,
  });
  const writable = project.writable_doc_roots.some(
    (root) => path === root || path.startsWith(`${root}/`),
  );
  const navigateLink = (e: React.MouseEvent<HTMLElement>) => {
    const anchor = (e.target as HTMLElement).closest("a");
    const href = anchor?.getAttribute("href");
    if (!href) return;
    if (/^https?:\/\//i.test(href)) {
      anchor?.setAttribute("target", "_blank");
      anchor?.setAttribute("rel", "noreferrer");
      return;
    }
    if (href.startsWith("#")) return;
    e.preventDefault();
    try {
      const base = new URL(path, "http://stash.local/");
      const resolved = new URL(href, base);
      if (resolved.origin !== base.origin || !resolved.pathname.endsWith(".md"))
        return;
      const destination = decodeURIComponent(resolved.pathname.slice(1));
      if (isstashNote(destination)) setSelected(destination);
    } catch {
      /* invalid document link */
    }
  };
  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">
        Development notes and history from .stash/. Repository README and
        project documentation stay separate.
      </p>
      <div className="mb-4 flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void tree.refetch();
            void doc.refetch();
          }}
        >
          Refresh files
        </Button>
        <Button size="sm" onClick={() => setCreating(true)}>
          New document
        </Button>
      </div>
      {tree.error && <ErrorNotice error={tree.error} />}
      {tree.data?.missing_roots
        .filter((root) => root.startsWith(".stash/"))
        .map((root) => (
          <p key={root} className="mb-3 text-xs text-muted-foreground">
            Missing document path: {root}
          </p>
        ))}
      <div className="grid min-h-[600px] overflow-hidden rounded border bg-card md:grid-cols-[230px_1fr]">
        <aside className="border-b bg-muted/30 p-3 md:border-b-0 md:border-r">
          <p className="mb-3 px-2 text-[10px] font-semibold uppercase text-muted-foreground">
            Files
          </p>
          {tree.isPending && <p className="text-xs">Loading files…</p>}
          <DocumentTree
            files={files}
            selected={path}
            onSelect={(file) => {
              if (
                draft &&
                !window.confirm("Discard the unsaved document draft?")
              )
                return;
              setDraft(null);
              setSelected(file);
              setError(null);
            }}
          />
          {tree.data && files.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No development notes found in .stash/.
            </p>
          )}
        </aside>
        <article className="min-w-0 p-6 md:p-10">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b pb-3">
            <span className="break-all font-mono text-xs text-muted-foreground">
              {path || "Select a document"}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSource(!source)}
              >
                {source ? "Rendered" : "View source"}
              </Button>
              {doc.data && writable && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setDraft({ ...doc.data! });
                    setError(null);
                  }}
                >
                  Edit
                </Button>
              )}
            </div>
          </div>
          {doc.error && (
            <ErrorNotice error={doc.error} retry={() => void doc.refetch()} />
          )}
          {doc.isFetching && (
            <p className="mb-3 text-xs text-muted-foreground">Checking file…</p>
          )}
          {draft && (
            <>
              {doc.data && doc.data.revision !== draft.revision && (
                <div role="alert" className="mb-4 rounded border p-3 text-sm">
                  The file changed externally. Your draft is retained. Compare
                  the current source below before reapplying changes.
                </div>
              )}
              <textarea
                aria-label="Document draft"
                className="stash-input min-h-96 font-mono"
                value={draft.content}
                onChange={(e) =>
                  setDraft({ ...draft, content: e.target.value })
                }
              />
              {error != null && <ErrorNotice error={error} />}
              <div className="my-4 flex flex-wrap gap-2">
                <Button
                  disabled={pending}
                  onClick={async () => {
                    setPending(true);
                    setError(null);
                    try {
                      await api(`${projectPath(project.id)}/document`, "PUT", {
                        ...draft,
                        actor,
                      });
                      setDraft(null);
                      await refresh();
                    } catch (e) {
                      setError(e);
                      if (e instanceof ApiError && e.status === 409)
                        await doc.refetch();
                    } finally {
                      setPending(false);
                    }
                  }}
                >
                  {pending ? "Saving…" : "Save"}
                </Button>
                <Button variant="outline" onClick={() => setDraft(null)}>
                  Discard draft
                </Button>
                {doc.data && doc.data.revision !== draft.revision && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      if (
                        window.confirm(
                          "Use the current file revision as your draft's base? Review and merge external changes before saving.",
                        )
                      ) {
                        setDraft({ ...draft, revision: doc.data!.revision });
                        setError(null);
                      }
                    }}
                  >
                    Use current revision after merging
                  </Button>
                )}
              </div>
              {doc.data && doc.data.revision !== draft.revision && (
                <details open>
                  <summary className="text-sm">Current external source</summary>
                  <pre className="mt-3 overflow-auto whitespace-pre-wrap rounded bg-muted p-4 text-xs">
                    {doc.data.content}
                  </pre>
                </details>
              )}
            </>
          )}
          {!draft &&
            doc.data &&
            (source ? (
              <pre className="overflow-auto whitespace-pre-wrap text-xs leading-6">
                {doc.data.content}
              </pre>
            ) : (
              <div
                className="markdown"
                onClick={navigateLink}
                dangerouslySetInnerHTML={{ __html: doc.data.html }}
              />
            ))}
        </article>
      </div>
      {creating && (
        <Panel
          title="New Markdown document"
          description="Create a development note inside .stash/docs/."
          onClose={() => setCreating(false)}
        >
          <RecordForm
            fields={[
              {
                name: "path",
                title: "Relative path",
                required: true,
                hint: "For example .stash/docs/notes.md",
              },
              { name: "content", title: "Markdown", kind: "area" },
            ]}
            onClose={() => setCreating(false)}
            onSave={async (value) => {
              const newPath = String(value["path"]);
              if (!isstashNote(newPath) || !newPath.startsWith(".stash/docs/"))
                throw new Error(
                  "Create development notes inside .stash/docs/.",
                );
              await api(`${projectPath(project.id)}/document`, "PUT", {
                ...value,
                revision: null,
                actor,
              });
              setSelected(String(value["path"]));
              await refresh();
            }}
          />
        </Panel>
      )}
    </>
  );
}

type TreeNode = {
  name: string;
  path: string;
  file: boolean;
  children: TreeNode[];
};
function DocumentTree({
  files,
  selected,
  onSelect,
}: {
  files: string[];
  selected: string;
  onSelect: (path: string) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const nodes = useMemo(() => {
    const roots: TreeNode[] = [];
    for (const file of files) {
      let siblings = roots;
      const parts = file.split("/");
      parts.forEach((name, index) => {
        const path = parts.slice(0, index + 1).join("/");
        let node = siblings.find((n) => n.path === path);
        if (!node) {
          node = { name, path, file: index === parts.length - 1, children: [] };
          siblings.push(node);
        }
        siblings = node.children;
      });
    }
    return roots;
  }, [files]);
  const renderNodes = (list: TreeNode[], depth: number): React.ReactNode =>
    list.map((node) => (
      <div key={node.path}>
        <button
          className={`flex w-full items-center gap-1.5 rounded py-2 pr-2 text-left text-xs ${selected === node.path ? "bg-accent" : "hover:bg-muted"}`}
          style={{ paddingLeft: 8 + depth * 12 }}
          title={node.path}
          aria-expanded={node.file ? undefined : !collapsed.has(node.path)}
          onClick={() => {
            if (node.file) onSelect(node.path);
            else {
              const next = new Set(collapsed);
              if (next.has(node.path)) next.delete(node.path);
              else next.add(node.path);
              setCollapsed(next);
            }
          }}
        >
          {node.file ? (
            <FileText className="size-3.5 shrink-0" />
          ) : (
            <>
              {collapsed.has(node.path) ? (
                <ChevronRight className="size-3 shrink-0" />
              ) : (
                <ChevronDown className="size-3 shrink-0" />
              )}
              <Folder className="size-3.5 shrink-0" />
            </>
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {!node.file &&
          !collapsed.has(node.path) &&
          renderNodes(node.children, depth + 1)}
      </div>
    ));
  return <div>{renderNodes(nodes, 0)}</div>;
}
