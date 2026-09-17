package com.example.lab.hil;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EmergencyBrakeIT extends RigTestBase {

    /** The example from the design doc, verbatim in spirit. */
    @Test
    void testEmergencyBrakeSignal() {
        rig.sendCommand("SIMULATE_BRAKE_TRIGGER");
        assertEquals("BRAKE_ENGAGED", rig.pollStatus(Duration.ofSeconds(5)));
    }

    @Test
    void selfTestPasses() {
        assertEquals("SELF_TEST_OK", rig.sendCommand("SELF_TEST"));
    }
}
