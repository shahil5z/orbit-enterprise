import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { FilterProvider, useFilters } from "../hooks/useFilters";

function Probe() {
  const { filters, setFilter, reset, active } = useFilters();
  const loc = useLocation();
  return (
    <div>
      <span data-testid="region">{filters.region_id ?? "none"}</span>
      <span data-testid="active">{active}</span>
      <span data-testid="url">{loc.search}</span>
      <button onClick={() => setFilter("region_id", "R04")}>set</button>
      <button onClick={reset}>reset</button>
    </div>
  );
}

describe("global filters", () => {
  it("reads from the URL first", () => {
    render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/x?region_id=R02"]}><FilterProvider><Probe /></FilterProvider></MemoryRouter>);
    expect(screen.getByTestId("region")).toHaveTextContent("R02");
  });
  it("writes to URL and localStorage, and restores from storage", () => {
    const { unmount } = render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/x"]}><FilterProvider><Probe /></FilterProvider></MemoryRouter>);
    act(() => screen.getByText("set").click());
    expect(screen.getByTestId("url")).toHaveTextContent("region_id=R04");
    expect(JSON.parse(localStorage.getItem("orbit.filters")!)).toMatchObject({ region_id: "R04" });
    unmount();
    render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={["/y"]}><FilterProvider><Probe /></FilterProvider></MemoryRouter>);
    expect(screen.getByTestId("region")).toHaveTextContent("R04");
    act(() => screen.getByText("reset").click());
    expect(screen.getByTestId("active")).toHaveTextContent("0");
  });
});
