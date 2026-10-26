package com.orbit.integration;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Simulated CRM and ERP systems backed by the sample CSV exports produced by the pipeline
 * (data/samples/crm_accounts.csv, data/samples/erp_suppliers.csv). Purchase orders are held in memory.
 */
public final class DataStore {
    private final Map<String, Map<String, String>> accounts = new LinkedHashMap<>();
    private final Map<String, Map<String, String>> suppliers = new LinkedHashMap<>();
    private final List<Map<String, Object>> purchaseOrders = new CopyOnWriteArrayList<>();
    private final AtomicInteger poSeq = new AtomicInteger(0);

    public DataStore(Path accountsCsv, Path suppliersCsv) throws IOException {
        load(accountsCsv, "customer_id", accounts);
        load(suppliersCsv, "supplier_id", suppliers);
    }

    static List<String> splitCsv(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean q = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (q) {
                if (c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') { cur.append('"'); i++; }
                else if (c == '"') q = false;
                else cur.append(c);
            } else if (c == '"') q = true;
            else if (c == ',') { out.add(cur.toString()); cur.setLength(0); }
            else cur.append(c);
        }
        out.add(cur.toString());
        return out;
    }

    private static void load(Path csv, String key, Map<String, Map<String, String>> into) throws IOException {
        List<String> lines = Files.readAllLines(csv, StandardCharsets.UTF_8);
        if (lines.isEmpty()) throw new IOException("empty file: " + csv);
        List<String> header = splitCsv(lines.get(0));
        if (!header.contains(key)) throw new IOException("missing key column " + key + " in " + csv);
        for (String line : lines.subList(1, lines.size())) {
            if (line.isBlank()) continue;
            List<String> vals = splitCsv(line);
            Map<String, String> row = new LinkedHashMap<>();
            for (int i = 0; i < header.size(); i++) row.put(header.get(i), i < vals.size() ? vals.get(i) : "");
            into.put(row.get(key), row);
        }
    }

    public int accountCount() { return accounts.size(); }
    public int supplierCount() { return suppliers.size(); }
    public int purchaseOrderCount() { return purchaseOrders.size(); }

    public List<Map<String, String>> accounts(String regionId, int limit) {
        return accounts.values().stream().filter(a -> regionId == null || regionId.equals(a.get("region_id")))
                .limit(limit).toList();
    }

    public Map<String, String> account(String id) { return accounts.get(id); }

    public List<Map<String, String>> suppliers() { return List.copyOf(suppliers.values()); }

    public List<Map<String, Object>> purchaseOrders() { return Collections.unmodifiableList(purchaseOrders); }

    /** Validates and stores a purchase order; returns the stored record. */
    public Map<String, Object> createPurchaseOrder(Map<String, Object> body) {
        List<String> errors = validate(body);
        if (!errors.isEmpty()) throw new ValidationException(errors);
        double qty = ((Number) body.get("quantity")).doubleValue();
        double price = ((Number) body.get("unit_price")).doubleValue();
        Map<String, Object> po = new LinkedHashMap<>();
        po.put("po_id", String.format("PO%06d", poSeq.incrementAndGet()));
        po.put("supplier_id", body.get("supplier_id"));
        po.put("sku", body.get("sku"));
        po.put("quantity", (long) qty);
        po.put("unit_price", price);
        po.put("total", Math.round(qty * price * 100.0) / 100.0);
        po.put("status", "SUBMITTED");
        po.put("created_at", Instant.now().toString());
        purchaseOrders.add(po);
        return po;
    }

    List<String> validate(Map<String, Object> b) {
        List<String> e = new ArrayList<>();
        Object sid = b.get("supplier_id");
        if (!(sid instanceof String s) || s.isBlank()) e.add("supplier_id is required");
        else if (!suppliers.containsKey(s)) e.add("supplier_id does not exist");
        Object sku = b.get("sku");
        if (!(sku instanceof String k) || !k.matches("[A-Za-z0-9-]{1,32}")) e.add("sku must be 1-32 alphanumeric characters");
        Object q = b.get("quantity");
        if (!(q instanceof Number n) || n.doubleValue() <= 0 || n.doubleValue() != Math.floor(n.doubleValue())
                || n.doubleValue() > 1_000_000) e.add("quantity must be a positive integer up to 1000000");
        Object p = b.get("unit_price");
        if (!(p instanceof Number n) || n.doubleValue() <= 0 || n.doubleValue() > 1_000_000) e.add("unit_price must be > 0 and <= 1000000");
        for (String k : b.keySet()) {
            if (!List.of("supplier_id", "sku", "quantity", "unit_price").contains(k)) e.add("unknown field: " + k);
        }
        return e;
    }

    public static final class ValidationException extends RuntimeException {
        public final List<String> errors;

        public ValidationException(List<String> errors) {
            super(String.join("; ", errors));
            this.errors = errors;
        }
    }
}
