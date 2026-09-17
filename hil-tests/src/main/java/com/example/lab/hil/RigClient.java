package com.example.lab.hil;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Rig-communication library used by the HIL tests (and reusable by tooling).
 * Talks to the rig's HTTP control API; a real one might wrap serial/TCP/MQTT instead.
 */
public final class RigClient {

    private final URI base;
    private final HttpClient http;

    public RigClient(String host) {
        this(host, 8080);
    }

    public RigClient(String host, int port) {
        this.base = URI.create("http://" + host + ":" + port);
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    }

    /** Raw status JSON as returned by GET /status. */
    public String status() {
        return get("/status");
    }

    public String state() {
        return field(status(), "state");
    }

    public String firmware() {
        return field(status(), "firmware");
    }

    /** Sends a command and returns the immediate result string ("BRAKE_ENGAGED", ...). */
    public String sendCommand(String cmd) {
        HttpRequest req = HttpRequest.newBuilder(base.resolve("/command"))
            .timeout(Duration.ofSeconds(5))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("{\"cmd\":\"" + cmd + "\"}"))
            .build();
        HttpResponse<String> resp = send(req);
        if (resp.statusCode() == 409) {
            throw new IllegalStateException("rig busy: " + resp.body());
        }
        return field(resp.body(), "result");
    }

    /**
     * Poll until the rig reports the last command's result, or until timeout.
     * Mirrors the {@code rig.pollStatus(Duration)} call in the design doc.
     */
    public String pollStatus(Duration timeout) {
        Instant deadline = Instant.now().plus(timeout);
        String last = "";
        while (Instant.now().isBefore(deadline)) {
            last = field(status(), "last_result");
            if (last != null && !last.isBlank()) {
                return last;
            }
            sleep(200);
        }
        return last;
    }

    /** Block until state == IDLE (boot finished / flash finished). */
    public boolean waitForReady(Duration timeout) {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            try {
                if ("IDLE".equals(state())) return true;
            } catch (RuntimeException ignored) {
                // rig may be rebooting – keep polling
            }
            sleep(500);
        }
        return false;
    }

    // ------------------------------------------------------------ internals

    private String get(String path) {
        HttpRequest req = HttpRequest.newBuilder(base.resolve(path)).timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<String> resp = send(req);
        if (resp.statusCode() / 100 != 2) {
            throw new IllegalStateException("GET " + path + " -> " + resp.statusCode() + ": " + resp.body());
        }
        return resp.body();
    }

    private HttpResponse<String> send(HttpRequest req) {
        try {
            return http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new IllegalStateException("rig unreachable at " + base + ": " + e.getMessage(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", e);
        }
    }

    private static final Pattern FIELD = Pattern.compile("\"(\\w+)\"\\s*:\\s*\"([^\"]*)\"");

    static String field(String json, String key) {
        if (json == null) return null;
        Matcher m = FIELD.matcher(json);
        while (m.find()) {
            if (m.group(1).equals(key)) return m.group(2);
        }
        return null;
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
