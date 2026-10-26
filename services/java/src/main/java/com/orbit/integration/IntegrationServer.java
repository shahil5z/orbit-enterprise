package com.orbit.integration;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;

/**
 * ORBIT enterprise integration service: simulated CRM (accounts) and ERP (suppliers, purchase orders)
 * endpoints. JDK only (com.sun.net.httpserver); responses use the platform envelope.
 */
public final class IntegrationServer {
    private static final int MAX_BODY = 16 * 1024;
    private final DataStore store;
    private final Instant startedAt = Instant.now();
    private HttpServer server;

    public IntegrationServer(DataStore store) { this.store = store; }

    public static void main(String[] args) throws IOException {
        Path root = Path.of(System.getProperty("orbit.root", "."));
        int port = Integer.parseInt(System.getenv().getOrDefault("ORBIT_JAVA_PORT", "8081"));
        DataStore store = new DataStore(root.resolve("data/samples/crm_accounts.csv"),
                root.resolve("data/samples/erp_suppliers.csv"));
        new IntegrationServer(store).start(port);
    }

    public void start(int port) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/", this::handle);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();
        log("INFO", "server_started", Map.of("port", port, "accounts", store.accountCount(),
                "suppliers", store.supplierCount()));
    }

    public void stop() { if (server != null) server.stop(0); }

    static void log(String level, String msg, Map<String, Object> ctx) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ts", Instant.now().toString());
        m.put("level", level);
        m.put("logger", "orbit.java.integration");
        m.put("msg", msg);
        m.putAll(ctx);
        System.out.println(Json.write(m));
    }

    private void handle(HttpExchange ex) throws IOException {
        long t0 = System.nanoTime();
        String method = ex.getRequestMethod();
        String path = ex.getRequestURI().getPath();
        int status;
        try {
            status = route(ex, method, path);
        } catch (DataStore.ValidationException ve) {
            status = send(ex, 422, null, ve.errors.stream().map(e -> err("VALIDATION_ERROR", e)).toList());
        } catch (MethodNotAllowed mna) {
            status = send(ex, 405, null, List.of(err("METHOD_NOT_ALLOWED", mna.getMessage())));
        } catch (IllegalArgumentException iae) {
            status = send(ex, 400, null, List.of(err("BAD_REQUEST", iae.getMessage())));
        } catch (Exception e) {
            log("ERROR", "unhandled_error", Map.of("path", path, "error_type", e.getClass().getSimpleName()));
            status = send(ex, 500, null, List.of(err("INTERNAL_ERROR", "internal error; see server logs")));
        }
        log("INFO", "request", Map.of("method", method, "path", path, "status", status,
                "duration_ms", Math.round((System.nanoTime() - t0) / 1e4) / 100.0));
    }

    private int route(HttpExchange ex, String method, String path) throws IOException {
        Map<String, String> q = query(ex.getRequestURI().getRawQuery());
        if (path.equals("/health")) {
            requireMethod(method, "GET");
            Map<String, Object> d = new LinkedHashMap<>();
            d.put("status", "ok");
            d.put("service", "orbit-java-integration");
            d.put("java_version", System.getProperty("java.version"));
            d.put("started_at", startedAt.toString());
            d.put("crm_accounts_loaded", store.accountCount());
            d.put("erp_suppliers_loaded", store.supplierCount());
            d.put("purchase_orders", store.purchaseOrderCount());
            return send(ex, 200, d, List.of());
        }
        if (path.equals("/api/crm/accounts")) {
            requireMethod(method, "GET");
            String region = q.get("region_id");
            if (region != null && !region.matches("R0[1-9]")) throw new IllegalArgumentException("invalid region_id");
            int limit = parseLimit(q.getOrDefault("limit", "50"));
            return send(ex, 200, store.accounts(region, limit), List.of());
        }
        if (path.startsWith("/api/crm/accounts/")) {
            requireMethod(method, "GET");
            Map<String, String> a = store.account(path.substring("/api/crm/accounts/".length()));
            if (a == null) return send(ex, 404, null, List.of(err("NOT_FOUND", "account not found")));
            return send(ex, 200, a, List.of());
        }
        if (path.equals("/api/erp/suppliers")) {
            requireMethod(method, "GET");
            return send(ex, 200, store.suppliers(), List.of());
        }
        if (path.equals("/api/erp/purchase-orders")) {
            if (method.equals("GET")) return send(ex, 200, store.purchaseOrders(), List.of());
            requireMethod(method, "POST");
            String ct = ex.getRequestHeaders().getFirst("Content-Type");
            if (ct == null || !ct.toLowerCase().startsWith("application/json")) {
                return send(ex, 415, null, List.of(err("UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json")));
            }
            Map<String, Object> po = store.createPurchaseOrder(Json.parseObject(readBody(ex)));
            log("INFO", "purchase_order_created", Map.of("po_id", po.get("po_id"), "supplier_id", po.get("supplier_id")));
            return send(ex, 201, po, List.of());
        }
        return send(ex, 404, null, List.of(err("NOT_FOUND", "no route for " + path)));
    }

    private static void requireMethod(String actual, String expected) {
        if (!actual.equals(expected)) throw new MethodNotAllowed(expected);
    }

    static int parseLimit(String s) {
        int l;
        try { l = Integer.parseInt(s); } catch (NumberFormatException e) { throw new IllegalArgumentException("limit must be an integer"); }
        if (l < 1 || l > 500) throw new IllegalArgumentException("limit must be within [1, 500]");
        return l;
    }

    private static String readBody(HttpExchange ex) throws IOException {
        try (InputStream in = ex.getRequestBody()) {
            byte[] b = in.readNBytes(MAX_BODY + 1);
            if (b.length > MAX_BODY) throw new IllegalArgumentException("request body too large");
            return new String(b, StandardCharsets.UTF_8);
        }
    }

    static Map<String, String> query(String raw) {
        Map<String, String> m = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) return m;
        for (String kv : raw.split("&")) {
            int i = kv.indexOf('=');
            String k = URLDecoder.decode(i < 0 ? kv : kv.substring(0, i), StandardCharsets.UTF_8);
            String v = i < 0 ? "" : URLDecoder.decode(kv.substring(i + 1), StandardCharsets.UTF_8);
            m.put(k, v);
        }
        return m;
    }

    private static Map<String, Object> err(String code, String message) {
        Map<String, Object> e = new LinkedHashMap<>();
        e.put("code", code);
        e.put("message", message);
        return e;
    }

    private int send(HttpExchange ex, int status, Object data, List<Map<String, Object>> errors) throws IOException {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("service", "orbit-java-integration");
        meta.put("generated_at", Instant.now().toString());
        meta.put("request_id", UUID.randomUUID().toString().substring(0, 12));
        if (data instanceof List<?> l) meta.put("count", l.size());
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("success", errors.isEmpty());
        body.put("data", data);
        body.put("metadata", meta);
        body.put("errors", errors);
        byte[] bytes = Json.write(body).getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = ex.getResponseBody()) { os.write(bytes); }
        return status;
    }

    static final class MethodNotAllowed extends IllegalArgumentException {
        MethodNotAllowed(String expected) { super("method not allowed; use " + expected); }
    }
}
