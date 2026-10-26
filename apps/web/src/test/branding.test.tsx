import { render, screen } from "@testing-library/react";
import { Page } from "../components/shared/Page";
import { CREDIT, SiteFooter } from "../components/shared/SiteFooter";

describe("branding", () => {
  it("footer carries the exact credit line", () => {
    render(<SiteFooter />);
    expect(screen.getByTestId("site-footer").textContent).toBe("An independent portfolio project \u00b7 \u00a9 2026 Shahil");
    expect(CREDIT).not.toMatch(/\u2014/);
  });
  it("page titles use the ORBIT ENTERPRISE prefix", () => {
    render(<Page title="Executive Overview"><p>x</p></Page>);
    expect(document.title).toBe("ORBIT ENTERPRISE | Executive Overview");
  });
});
