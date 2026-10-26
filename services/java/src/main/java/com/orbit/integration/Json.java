package com.orbit.integration;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Minimal JSON support: writes maps/lists/scalars and parses flat objects (string, number, boolean, null). */
public final class Json {
    private Json() {}

    public static String write(Object v) {
        StringBuilder sb = new StringBuilder();
        write(sb, v);
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static void write(StringBuilder sb, Object v) {
        if (v == null) {
            sb.append("null");
        } else if (v instanceof String s) {
            sb.append('"');
            for (char c : s.toCharArray()) {
                switch (c) {
                    case '"' -> sb.append("\\\"");
                    case '\\' -> sb.append("\\\\");
                    case '\n' -> sb.append("\\n");
                    case '\r' -> sb.append("\\r");
                    case '\t' -> sb.append("\\t");
                    default -> {
                        if (c < 0x20) sb.append(String.format("\\u%04x", (int) c)); else sb.append(c);
                    }
                }
            }
            sb.append('"');
        } else if (v instanceof Number || v instanceof Boolean) {
            sb.append(v);
        } else if (v instanceof Map<?, ?> m) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) sb.append(',');
                first = false;
                write(sb, String.valueOf(e.getKey()));
                sb.append(':');
                write(sb, e.getValue());
            }
            sb.append('}');
        } else if (v instanceof List<?> l) {
            sb.append('[');
            for (int i = 0; i < l.size(); i++) {
                if (i > 0) sb.append(',');
                write(sb, l.get(i));
            }
            sb.append(']');
        } else {
            write(sb, v.toString());
        }
    }

    /** Parses a flat JSON object. Nested objects/arrays are rejected with IllegalArgumentException. */
    public static Map<String, Object> parseObject(String text) {
        Parser p = new Parser(text.trim());
        Map<String, Object> out = p.object();
        p.ws();
        if (p.i != p.s.length()) throw new IllegalArgumentException("trailing characters after JSON object");
        return out;
    }

    private static final class Parser {
        final String s;
        int i;

        Parser(String s) { this.s = s; }

        void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }

        char peek() {
            if (i >= s.length()) throw new IllegalArgumentException("unexpected end of JSON");
            return s.charAt(i);
        }

        void expect(char c) {
            ws();
            if (peek() != c) throw new IllegalArgumentException("expected '" + c + "' at position " + i);
            i++;
        }

        Map<String, Object> object() {
            Map<String, Object> m = new LinkedHashMap<>();
            expect('{');
            ws();
            if (peek() == '}') { i++; return m; }
            while (true) {
                ws();
                String k = string();
                expect(':');
                ws();
                m.put(k, value());
                ws();
                char c = peek();
                i++;
                if (c == '}') return m;
                if (c != ',') throw new IllegalArgumentException("expected ',' or '}' at position " + (i - 1));
            }
        }

        Object value() {
            char c = peek();
            if (c == '"') return string();
            if (c == '{' || c == '[') throw new IllegalArgumentException("nested values are not supported");
            if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
            if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
            if (s.startsWith("null", i)) { i += 4; return null; }
            int st = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            if (st == i) throw new IllegalArgumentException("invalid value at position " + st);
            try {
                return Double.parseDouble(s.substring(st, i));
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException("invalid number at position " + st);
            }
        }

        String string() {
            if (peek() != '"') throw new IllegalArgumentException("expected string at position " + i);
            i++;
            StringBuilder sb = new StringBuilder();
            while (true) {
                char c = peek();
                i++;
                if (c == '"') return sb.toString();
                if (c == '\\') {
                    char e = peek();
                    i++;
                    switch (e) {
                        case 'n' -> sb.append('\n');
                        case 't' -> sb.append('\t');
                        case 'r' -> sb.append('\r');
                        case 'u' -> {
                            sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                            i += 4;
                        }
                        default -> sb.append(e);
                    }
                } else {
                    sb.append(c);
                }
            }
        }
    }
}
