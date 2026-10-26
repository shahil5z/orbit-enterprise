import { byUnit, DASH, money, num, pct } from "../utils/format";
import { toCsv } from "../utils/csv";

describe("format", () => {
  it("formats money with magnitude suffixes and sign", () => {
    expect(money(1_403_946_594)).toBe("1.40B");
    expect(money(49_585_628)).toBe("49.6M");
    expect(money(-2_500)).toBe("-2.5K");
    expect(money(12)).toBe("12");
  });
  it("returns n/a for missing values instead of inventing zeros", () => {
    expect(money(null)).toBe(DASH);
    expect(pct(undefined)).toBe(DASH);
    expect(num(Number.NaN)).toBe(DASH);
  });
  it("formats signed percentages", () => {
    expect(pct(0.0383, 1, true)).toBe("+3.8%");
    expect(pct(-0.261, 1, true)).toBe("-26.1%");
    expect(pct(0.5, 0)).toBe("50%");
  });
  it("formats by governed KPI unit", () => {
    expect(byUnit(0.4072, "percent")).toBe("40.7%");
    expect(byUnit(13.14, "hours")).toBe("13.1 h");
    expect(byUnit(99.61, "score")).toBe("99.6");
  });
});

describe("toCsv", () => {
  it("escapes quotes, commas and newlines (RFC 4180)", () => {
    const csv = toCsv([{ a: 'say "hi"', b: "x,y", c: "l1\nl2", d: null }], [
      { key: "a", header: "A", value: (r) => r.a }, { key: "b", header: "B", value: (r) => r.b },
      { key: "c", header: "C", value: (r) => r.c }, { key: "d", header: "D", value: (r) => r.d },
    ]);
    expect(csv).toBe('A,B,C,D\n"say ""hi""","x,y","l1\nl2",\n');
  });
});
