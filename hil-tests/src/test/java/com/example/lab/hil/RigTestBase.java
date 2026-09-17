package com.example.lab.hil;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertTrue;

/** Shared setup: target rig from system properties, wait until it is IDLE before each test. */
abstract class RigTestBase {

    static String host;
    static int port;
    static RigClient rig;

    @BeforeAll
    static void connect() {
        host = System.getProperty("rig.host", "localhost");
        port = Integer.parseInt(System.getProperty("rig.port", "8101"));
        rig = new RigClient(host, port);
    }

    @BeforeEach
    void rigMustBeIdle() {
        assertTrue(rig.waitForReady(Duration.ofSeconds(30)),
            "rig " + host + ":" + port + " did not become IDLE – state=" + safeState());
    }

    private static String safeState() {
        try {
            return rig.state();
        } catch (RuntimeException e) {
            return "unreachable (" + e.getMessage() + ")";
        }
    }
}
