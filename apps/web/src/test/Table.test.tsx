import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Table, type Column } from "../components/ui";

interface Row { id: string; name: string; score: number }
const rows: Row[] = Array.from({ length: 13 }, (_, i) => ({ id: `r${i}`, name: `Unit ${String.fromCharCode(65 + i)}`, score: (i * 7) % 13 }));
const cols: Column<Row>[] = [{ key: "name", header: "Name", value: (r) => r.name }, { key: "score", header: "Score", align: "right", value: (r) => r.score }];
const bodyRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);

describe("Table", () => {
  it("paginates", async () => {
    render(<Table rows={rows} columns={cols} caption="Units" rowKey={(r) => r.id} pageSize={5} />);
    expect(bodyRows()).toHaveLength(5);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("sorts by column and exposes aria-sort", async () => {
    render(<Table rows={rows} columns={cols} caption="Units" rowKey={(r) => r.id} pageSize={20} />);
    await userEvent.click(screen.getByRole("button", { name: /Score/ }));
    expect(screen.getByRole("columnheader", { name: /Score/ })).toHaveAttribute("aria-sort", "descending");
    expect(bodyRows()[0]).toHaveTextContent("12");
    await userEvent.click(screen.getByRole("button", { name: /Score/ }));
    expect(bodyRows()[0]).toHaveTextContent("0");
  });

  it("filters rows and shows an empty state", async () => {
    render(<Table rows={rows} columns={cols} caption="Units" rowKey={(r) => r.id} />);
    await userEvent.type(screen.getByRole("searchbox"), "Unit C");
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("1 of 13 rows")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText("No rows match the filter")).toBeInTheDocument();
  });

  it("opens row details by click and keyboard", async () => {
    const onRow = vi.fn();
    render(<Table rows={rows} columns={cols} caption="Units" rowKey={(r) => r.id} onRowClick={onRow} />);
    await userEvent.click(bodyRows()[0]!);
    bodyRows()[1]!.focus();
    await userEvent.keyboard("{Enter}");
    expect(onRow).toHaveBeenCalledTimes(2);
    expect(onRow.mock.calls[1]![0]).toMatchObject({ id: "r1" });
  });
});
