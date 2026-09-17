package com.example.lab.rigsim;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

/**
 * Minimal HTTP control surface of the rig. JSON is hand-rolled to keep the image dependency-free.
 *
 * GET  /health    liveness
 * GET  /status    full status JSON
 * POST /command   {"cmd":"SIMULATE_BRAKE_TRIGGER"}  -> {"result":"BRAKE_ENGAGED"}
 * POST /flash     raw image bytes, header X-Firmware-Version
 * POST /fault     chaos: force FAILING
 * POST /reset     back to IDLE
 * GET  /metrics   Prometheus text format
 */
final class HttpApi {

    private final RigBoard board;
    private final HttpServer server;

    HttpApi(RigBoard board, int port) throws IOException {
        this.board = board;
        this.server = HttpServer.create(new InetSocketAddress(port), 0);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.createContext("/health", ex -> respond(ex, 200, "application/json", "{\"status\":\"ok\"}"));
        server.createContext("/status", this::status);
        server.createContext("/command", this::command);
        server.createContext("/flash", this::flash);
        server.createContext("/fault", this::fault);
        server.createContext("/reset", this::reset);
        server.createContext("/metrics", ex -> respond(ex, 200, "text/plain; version=0.0.4", Metrics.render(board)));
        server.createContext("/", ex -> respond(ex, 404, "application/json", "{\"error\":\"not found\"}"));
    }

    void start() {
        server.start();
    }

    void stop() {
        server.stop(0);
    }

    // ------------------------------------------------------------ handlers

    private void status(HttpExchange ex) throws IOException {
        respond(ex, 200, "application/json", statusJson());
    }

    String statusJson() {
        return "{"
            + "\"id\":" + q(board.id())
            + ",\"lab\":" + q(board.lab())
            + ",\"state\":" + q(board.state().name())
            + ",\"firmware\":" + q(board.firmware())
            + ",\"uptime_s\":" + board.uptimeSeconds()
            + ",\"temperature_c\":" + board.temperatureCelsius()
            + ",\"last_command\":" + q(board.lastCommand())
            + ",\"last_result\":" + q(board.lastResult())
            + ",\"last_error\":" + q(board.lastError())
            + "}";
    }

    private void command(HttpExchange ex) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) { methodNotAllowed(ex); return; }
        String body = readBody(ex);
        String cmd = extractString(body, "cmd");
        if (cmd == null) {
            respond(ex, 400, "application/json", "{\"error\":\"missing cmd\"}");
            return;
        }
        try {
            String result = board.command(cmd);
            int code = "ERROR".equals(result) ? 500 : 200;
            respond(ex, code, "application/json", "{\"result\":" + q(result) + ",\"state\":" + q(board.state().name()) + "}");
        } catch (IllegalStateException e) {
            respond(ex, 409, "application/json", "{\"error\":" + q(e.getMessage()) + "}");
        }
    }

    private void flash(HttpExchange ex) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) { methodNotAllowed(ex); return; }
        String version = ex.getRequestHeaders().getFirst("X-Firmware-Version");
        long bytes = drain(ex.getRequestBody());
        try {
            board.flash(version, bytes);
            respond(ex, 202, "application/json",
                "{\"accepted\":true,\"version\":" + q(version) + ",\"bytes\":" + bytes + ",\"state\":\"FLASHING\"}");
        } catch (IllegalStateException e) {
            respond(ex, 409, "application/json", "{\"error\":" + q(e.getMessage()) + "}");
        } catch (IllegalArgumentException e) {
            respond(ex, 400, "application/json", "{\"error\":" + q(e.getMessage()) + "}");
        }
    }

    private void fault(HttpExchange ex) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) { methodNotAllowed(ex); return; }
        String reason = extractString(readBody(ex), "reason");
        board.injectFault(reason);
        respond(ex, 200, "application/json", "{\"state\":\"FAILING\"}");
    }

    private void reset(HttpExchange ex) throws IOException {
        if (!"POST".equals(ex.getRequestMethod())) { methodNotAllowed(ex); return; }
        board.reset();
        respond(ex, 200, "application/json", "{\"state\":\"IDLE\"}");
    }

    // ------------------------------------------------------------- helpers

    private static void methodNotAllowed(HttpExchange ex) throws IOException {
        respond(ex, 405, "application/json", "{\"error\":\"method not allowed\"}");
    }

    private static void respond(HttpExchange ex, int code, String contentType, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", contentType);
        ex.sendResponseHeaders(code, bytes.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static String readBody(HttpExchange ex) throws IOException {
        try (InputStream in = ex.getRequestBody()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static long drain(InputStream in) throws IOException {
        long total = 0;
        byte[] buf = new byte[8192];
        int n;
        try (in) {
            while ((n = in.read(buf)) > 0) {
                total += n;
            }
        }
        return total;
    }

    /** Tiny extractor for {"key":"value"} – enough for the two fields we accept. */
    static String extractString(String json, String key) {
        if (json == null) return null;
        String needle = "\"" + key + "\"";
        int i = json.indexOf(needle);
        if (i < 0) return null;
        int colon = json.indexOf(':', i + needle.length());
        if (colon < 0) return null;
        int open = json.indexOf('"', colon + 1);
        if (open < 0) return null;
        int close = json.indexOf('"', open + 1);
        if (close < 0) return null;
        return json.substring(open + 1, close);
    }

    private static String q(String s) {
        if (s == null) return "null";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
