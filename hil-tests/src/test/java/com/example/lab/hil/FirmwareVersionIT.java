package com.example.lab.hil;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Traceability: the rig must run exactly the firmware this pipeline flashed. */
class FirmwareVersionIT extends RigTestBase {

    @Test
    void firmwareIsNotFactoryImage() {
        assertNotEquals("0.0.0-factory", rig.firmware(), "rig still runs the factory image – flash did not happen");
    }

    @Test
    void firmwareMatchesExpectedVersion() {
        String expected = System.getProperty("expected.firmware", "");
        assumeTrue(!expected.isBlank(), "-Dexpected.firmware not set, skipping exact match");
        assertEquals(expected, rig.firmware());
    }
}
