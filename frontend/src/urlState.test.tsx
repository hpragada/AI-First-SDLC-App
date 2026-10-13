// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { useParamState } from "./urlState";

function Probe({ fallback = "" }: { fallback?: string }) {
  const [value, choose, pinned] = useParamState("gate", fallback);
  return (
    <div>
      <span data-testid="value">{value}</span>
      <span data-testid="pinned">{String(pinned)}</span>
      <button onClick={() => choose("chosen")}>choose</button>
    </div>
  );
}

function at(route: string, fallback?: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Probe fallback={fallback} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("useParamState", () => {
  it("honours the URL param on first render and reports it as pinned", () => {
    at("/gates?gate=ap2");
    expect(screen.getByTestId("value").textContent).toBe("ap2");
    expect(screen.getByTestId("pinned").textContent).toBe("true");
  });

  it("behaves exactly as before when no param is present", () => {
    at("/gates", "first-pending");
    expect(screen.getByTestId("value").textContent).toBe("first-pending");
    expect(screen.getByTestId("pinned").textContent).toBe("false");
  });

  it("lets a local choice override the URL without a render loop", () => {
    at("/gates?gate=ap2");
    fireEvent.click(screen.getByText("choose"));
    expect(screen.getByTestId("value").textContent).toBe("chosen");
    expect(screen.getByTestId("pinned").textContent).toBe("false");
  });
});
