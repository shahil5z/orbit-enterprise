import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Async, RiskBadge, StatusIndicator } from "../components/ui";
import { ApiError } from "../services/http";
import { health } from "../features/quality/QualityPage";
import { flattenMetrics } from "../features/models/ModelsPage";

const base = { reload: () => undefined };

describe("Async states", () => {
  it("shows loading", () => {
    render(<Async state={{ ...base, status: "loading", data: null, error: null }}>{() => <p>done</p>}</Async>);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });
  it("shows error with a working retry", async () => {
    const reload = vi.fn();
    render(<Async state={{ status: "error", data: null, error: new ApiError(503, [{ code: "DB", message: "database unavailable" }]), reload }}>{() => <p>done</p>}</Async>);
    expect(screen.getByRole("alert")).toHaveTextContent("database unavailable (HTTP 503)");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(reload).toHaveBeenCalledOnce();
  });
  it("shows empty", () => {
    render(<Async state={{ ...base, status: "success", data: [] as number[], error: null }} isEmpty={(d) => d.length === 0}>{() => <p>done</p>}</Async>);
    expect(screen.getByText("No data for this selection")).toBeInTheDocument();
  });
  it("shows success", () => {
    render(<Async state={{ ...base, status: "success", data: [1], error: null }}>{(d) => <p>rows {d.length}</p>}</Async>);
    expect(screen.getByText("rows 1")).toBeInTheDocument();
  });
});

describe("status semantics are not colour-only", () => {
  it("risk badge carries level text and score", () => {
    render(<RiskBadge level="HIGH" score={58.39} />);
    expect(screen.getByText(/HIGH 58\.4/)).toBeInTheDocument();
  });
  it("status indicator carries text", () => {
    render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><StatusIndicator status="FAILED" /></MemoryRouter>);
    expect(screen.getByText("FAILED")).toBeInTheDocument();
  });
  it("dataset health thresholds", () => {
    expect(health(99.61).label).toBe("Healthy");
    expect(health(97.05).label).toBe("Watch");
    expect(health(93.89).label).toBe("Unhealthy");
  });
  it("flattens nested model metrics, dropping nulls", () => {
    expect(flattenMetrics({ test: { mape: 0.089952, n: 36 }, k: null, note: "x" })).toEqual([{ key: "test.mape", value: 0.09 }, { key: "test.n", value: 36 }, { key: "note", value: "x" }]);
  });
});
