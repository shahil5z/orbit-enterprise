import { ApiError, recentTimings, request } from "../services/http";
import { qs } from "../services/api";

const envelope = (data: unknown, success = true, errors: unknown[] = []) => ({ success, data, metadata: {}, errors });

describe("http client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("unwraps the envelope and records timing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(envelope({ x: 1 })), { status: 200 }));
    await expect(request<{ x: number }>("/thing")).resolves.toEqual({ x: 1 });
    expect(fetch).toHaveBeenCalledWith("/api/v1/thing", expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }));
    expect(recentTimings().at(-1)).toMatchObject({ path: "/thing", status: 200 });
  });

  it("raises ApiError with server messages on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(envelope(null, false, [{ code: "NOT_FOUND", message: "no such dataset" }])), { status: 404 }));
    const err = await request("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe("no such dataset");
    expect((err as ApiError).retryable).toBe(false);
  });

  it("maps network failure to a retryable error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await request("/x").catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(0);
    expect(err.retryable).toBe(true);
  });

  it("sends JSON bodies with a content type", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(envelope({ ok: 1 }))));
    await request("/run", { method: "POST", body: JSON.stringify({ a: 1 }) });
    expect(fetch).toHaveBeenCalledWith("/api/v1/run", expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
  });

  it("builds query strings without empty values", () => {
    expect(qs({ a: "R01", b: null, c: undefined, d: "", e: 0 })).toBe("?a=R01&e=0");
    expect(qs({})).toBe("");
  });
});
