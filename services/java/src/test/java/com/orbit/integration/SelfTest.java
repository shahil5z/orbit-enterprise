package com.orbit.integration;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/** Dependency-free test runner (no JUnit available offline). Exit code 0 only if every check passes. */
public final class SelfTest {
    private static int passed, failed;

    static void check(String name, boolean cond) {
        if (cond) { passed++; System.out.println("PASS " + name); }
        else { failed++; System.out.println("FAIL " + name); }
    }

    public static void main(String[] args) throws Exception {
        check("json parse flat object", Json.parseObject("{\"a\":\"x\",\"b\":2.5,\"c\":true,\"d\":null}").get("b").equals(2.5));
        check("json rejects nested", throwsIAE(() -> Json.parseObject("{\"a\":{\"b\":1}}")));
        check("json rejects trailing", throwsIAE(() -> Json.parseObject("{\"a\":1} x")));
        check("json escapes", Json.write(Map.of("k", "a\"b\n")).equals("{\"k\":\"a\\\"b\\n\"}"));
        check("csv quoted comma", DataStore.splitCsv("a,\"b,c\",d").equals(List.of("a", "b,c", "d")));
        check("limit bounds", throwsIAE(() -> IntegrationServer.parseLimit("0")) && IntegrationServer.parseLimit("10") == 10);

        Path dir = Files.createTempDirectory("orbit-java-test");
        Files.writeString(dir.resolve("a.csv"), "customer_id,name,region_id\nC1,\"Acme, Inc\",R01\nC2,Beta,R02\n");
        Files.writeString(dir.resolve("s.csv"), "supplier_id,name\nS1,Sup\n");
        DataStore store = new DataStore(dir.resolve("a.csv"), dir.resolve("s.csv"));
        check("accounts loaded", store.accountCount() == 2 && store.account("C1").get("name").equals("Acme, Inc"));
        check("region filter", store.accounts("R02", 10).size() == 1);
        check("valid PO accepted", store.createPurchaseOrder(Map.of("supplier_id", "S1", "sku", "SKU-1", "quantity", 3.0,
                "unit_price", 2.5)).get("total").equals(7.5));
        check("unknown supplier rejected", !store.validate(Map.of("supplier_id", "S9", "sku", "A", "quantity", 1.0, "unit_price", 1.0)).isEmpty());
        check("negative quantity rejected", !store.validate(Map.of("supplier_id", "S1", "sku", "A", "quantity", -1.0, "unit_price", 1.0)).isEmpty());
        check("fractional quantity rejected", !store.validate(Map.of("supplier_id", "S1", "sku", "A", "quantity", 1.5, "unit_price", 1.0)).isEmpty());
        check("unknown field rejected", !store.validate(Map.of("supplier_id", "S1", "sku", "A", "quantity", 1.0, "unit_price", 1.0, "x", 1.0)).isEmpty());

        IntegrationServer srv = new IntegrationServer(store);
        int port = 18081;
        srv.start(port);
        try {
            HttpClient c = HttpClient.newHttpClient();
            HttpResponse<String> h = get(c, port, "/health");
            check("GET /health 200", h.statusCode() == 200 && h.body().contains("\"status\":\"ok\""));
            check("GET unknown 404", get(c, port, "/nope").statusCode() == 404);
            check("GET bad region 400", get(c, port, "/api/crm/accounts?region_id=X").statusCode() == 400);
            check("POST PO 201", post(c, port, "{\"supplier_id\":\"S1\",\"sku\":\"A1\",\"quantity\":2,\"unit_price\":4}", "application/json").statusCode() == 201);
            check("POST invalid PO 422", post(c, port, "{\"supplier_id\":\"S1\",\"sku\":\"A1\",\"quantity\":0,\"unit_price\":4}", "application/json").statusCode() == 422);
            check("POST malformed JSON 400", post(c, port, "{bad", "application/json").statusCode() == 400);
            check("POST wrong content type 415", post(c, port, "{}", "text/plain").statusCode() == 415);
            check("DELETE health 405", c.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/health")).DELETE().build(),
                    HttpResponse.BodyHandlers.ofString()).statusCode() == 405);
        } finally {
            srv.stop();
        }
        System.out.println("RESULT passed=" + passed + " failed=" + failed);
        System.exit(failed == 0 ? 0 : 1);
    }

    static HttpResponse<String> get(HttpClient c, int port, String p) throws IOException, InterruptedException {
        return c.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + p)).GET().build(), HttpResponse.BodyHandlers.ofString());
    }

    static HttpResponse<String> post(HttpClient c, int port, String body, String ct) throws IOException, InterruptedException {
        return c.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/erp/purchase-orders"))
                .header("Content-Type", ct).POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    static boolean throwsIAE(Runnable r) {
        try { r.run(); return false; } catch (IllegalArgumentException e) { return true; }
    }
}
