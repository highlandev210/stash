import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { Panel, RecordForm } from "@/app/shared";
import { confirmNavigation } from "@/hooks/use-unsaved-changes";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Editor() {
  const [open, setOpen] = useState(true);
  return open ? (
    <Panel title="Edit note" onClose={() => setOpen(false)}>
      <RecordForm
        fields={[{ name: "body", title: "Body" }]}
        onSave={async () => {}}
        onClose={() => setOpen(false)}
      />
    </Panel>
  ) : (
    <p>Closed</p>
  );
}

it("protects dirty forms from Escape, close, cancel, and page unload", () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Editor />);
  fireEvent.change(screen.getByLabelText("Body"), {
    target: { value: "Keep this draft" },
  });
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.getByLabelText("Body")).toHaveValue("Keep this draft");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(confirm).toHaveBeenCalledTimes(3);
  expect(confirmNavigation()).toBe(false);
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.getByText("Closed")).toBeVisible();
  expect(confirmNavigation()).toBe(true);
});

it("closes a pristine form without prompting", () => {
  const confirm = vi.spyOn(window, "confirm");
  render(<Editor />);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.getByText("Closed")).toBeVisible();
  expect(confirm).not.toHaveBeenCalled();
});
