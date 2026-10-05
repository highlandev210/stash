import { useState, type FormEvent, type ReactNode } from "react";
import { Check, Clipboard, Folder, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { label } from "@/lib/api/client";

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-7 place-items-center rounded-md bg-foreground text-sm font-semibold text-background">
        s
      </span>
      <span className="font-semibold">stash</span>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex rounded border px-2 py-0.5 text-[11px] ${value === "active" || value === "done" ? "bg-status-active text-status-active-foreground" : value === "missing" || value === "blocked" ? "bg-priority-high text-priority-high-foreground" : "bg-muted text-muted-foreground"}`}
    >
      {label(value)}
    </span>
  );
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="my-4 whitespace-pre-wrap rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm"
    >
      <p>{error instanceof Error ? error.message : String(error)}</p>
      {retry && (
        <Button className="mt-3" variant="outline" size="sm" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}
export function Copy({
  text,
  title = "Copy",
  compact = false,
}: {
  text: string;
  title?: string;
  compact?: boolean;
}) {
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <Button
        size={compact ? "icon" : "sm"}
        variant="outline"
        aria-label={title}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setDone(true);
            setTimeout(() => setDone(false), 1600);
          } catch {
            setError(
              "Clipboard unavailable; select and copy the text manually.",
            );
          }
        }}
      >
        {done ? (
          <Check className="size-3.5" />
        ) : (
          <Clipboard className="size-3.5" />
        )}
        {!compact && (done ? "Copied" : title)}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
    </>
  );
}
export function Preview({
  name,
  image,
}: {
  name: string;
  image?: string | undefined;
}) {
  return image ? (
    <img
      src={image}
      alt={`${name} screenshot`}
      className="h-44 w-full border-b object-cover"
    />
  ) : (
    <div className="flex h-44 items-center justify-center gap-3 border-b bg-preview text-muted-foreground">
      <Folder className="size-7" />
      <span className="font-mono text-xs">{name}</span>
    </div>
  );
}
export function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}
export function Panel({
  title,
  description,
  children,
  onClose,
}: {
  title: string;
  description?: string | undefined;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
        <SheetHeader className="border-b p-6">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {description || "Changes are saved to your local stash records."}
          </SheetDescription>
        </SheetHeader>
        <div className="p-6">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
export type Field = {
  name: string;
  title: string;
  kind?: "area" | "list";
  options?: string[];
  required?: boolean;
  hint?: string;
};
export function RecordForm({
  fields,
  initial,
  onSave,
  onClose,
  saveLabel = "Save",
}: {
  fields: Field[];
  initial?: Record<string, unknown> | undefined;
  onSave: (value: Record<string, unknown>) => Promise<unknown>;
  onClose: () => void;
  saveLabel?: string;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.name,
        Array.isArray(initial?.[f.name])
          ? (initial[f.name] as string[]).join("\n")
          : String(initial?.[f.name] ?? f.options?.[0] ?? ""),
      ]),
    ),
  );
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await onSave(
        Object.fromEntries(
          fields.map((f) => [
            f.name,
            f.kind === "list"
              ? (draft[f.name] || "")
                  .split("\n")
                  .map((x) => x.trim())
                  .filter(Boolean)
              : draft[f.name] || "",
          ]),
        ),
      );
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-5">
      {fields.map((f) => (
        <label key={f.name} className="block space-y-2">
          <span className="text-xs font-medium">
            {f.title}
            {f.required && " *"}
          </span>
          {f.options ? (
            <select
              aria-label={f.title}
              className="stash-input"
              value={draft[f.name]}
              onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })}
            >
              {f.options.map((x) => (
                <option key={x} value={x}>
                  {label(x)}
                </option>
              ))}
            </select>
          ) : f.kind ? (
            <textarea
              aria-label={f.title}
              className="stash-input min-h-24"
              required={f.required}
              value={draft[f.name]}
              onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })}
            />
          ) : (
            <Input
              aria-label={f.title}
              required={f.required}
              value={draft[f.name]}
              onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })}
            />
          )}
          {(f.hint || f.kind === "list") && (
            <p className="text-[11px] text-muted-foreground">
              {f.hint || "One item per line"}
            </p>
          )}
        </label>
      ))}
      {error != null && <ErrorNotice error={error} />}
      <div className="sticky bottom-0 flex gap-2 border-t bg-background py-4">
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : saveLabel}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={onClose}
          disabled={pending}
        >
          Cancel
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Keep secret values out of project records.
      </p>
    </form>
  );
}
export function Pager({
  offset,
  total,
  size = 100,
  onChange,
}: {
  offset: number;
  total: number;
  size?: number;
  onChange: (offset: number) => void;
}) {
  return total > size ? (
    <div className="mt-5 flex items-center gap-3 text-xs">
      <Button
        variant="outline"
        size="sm"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - size))}
      >
        Previous
      </Button>
      <span>
        {offset + 1}–{Math.min(offset + size, total)} of {total}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={offset + size >= total}
        onClick={() => onChange(offset + size)}
      >
        Next
      </Button>
    </div>
  ) : null;
}
