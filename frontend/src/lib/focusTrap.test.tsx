import { useRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useFocusTrap } from "./focusTrap";

function Panel({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(true, ref, onClose);
  return (
    <div ref={ref} tabIndex={-1}>
      <button type="button">First</button>
      <button type="button">Last</button>
    </div>
  );
}

describe("focus trap (mobile drawer and dialogs)", () => {
  it("moves focus in, keeps Tab inside, closes on Escape and restores focus", () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const onClose = vi.fn();

    const view = render(<Panel onClose={onClose} />);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));

    // from the last control Tab wraps to the first, so focus cannot leave the panel
    screen.getByRole("button", { name: "Last" }).focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();

    view.unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
