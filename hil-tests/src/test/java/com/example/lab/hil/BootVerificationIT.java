package com.example.lab.hil;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class BootVerificationIT extends RigTestBase {

    @Test
    void rigReportsIdleAfterBoot() {
        assertEquals("IDLE", rig.state());
    }

    @Test
    void statusContainsIdentity() {
        String status = rig.status();
        assertNotNull(RigClient.field(status, "id"), "status must include rig id");
        assertNotNull(RigClient.field(status, "lab"), "status must include lab");
        assertNotNull(RigClient.field(status, "firmware"), "status must include firmware");
    }

    @Test
    void pingRoundTrip() {
        assertEquals("PONG", rig.sendCommand("PING"));
    }
}
