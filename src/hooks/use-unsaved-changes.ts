import { useEffect, useId, useLayoutEffect } from "react";

const drafts = new Map<string, { dirty: boolean; pending: boolean }>();

export function confirmDiscard(dirty: boolean, pending = false) {
  if (pending) return false;
  return !dirty || window.confirm("Discard unsaved changes?");
}

export function confirmNavigation() {
  return confirmDiscard(
    [...drafts.values()].some((draft) => draft.dirty),
    [...drafts.values()].some((draft) => draft.pending),
  );
}

export function useUnsavedChanges(dirty: boolean, pending = false) {
  const id = useId();
  useLayoutEffect(() => {
    drafts.set(id, { dirty, pending });
    return () => {
      drafts.delete(id);
    };
  }, [id, dirty, pending]);
  useEffect(() => {
    if (!dirty && !pending) return;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty, pending]);
}
