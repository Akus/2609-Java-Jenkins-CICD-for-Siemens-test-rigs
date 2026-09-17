package com.example.lab.rigsim;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.*;

class RigBoardTest {

    private RigBoard board;

    private RigBoard reliable() {
        board = new RigBoard("rig-test-01", "test", 0.0, Duration.ofMillis(50), new Random(1));
        return board;
    }

    private RigBoard alwaysFaulty() {
        board = new RigBoard("rig-test-02", "test", 1.0, Duration.ofMillis(50), new Random(1));
        return board;
    }

    @AfterEach
    void tearDown() {
        if (board != null) board.shutdown();
    }

    @Test
    void bootsIdleWithFactoryFirmware() {
        RigBoard b = reliable();
        assertEquals(RigState.IDLE, b.state());
        assertEquals("0.0.0-factory", b.firmware());
    }

    @Test
    void brakeTriggerEngagesBrakeAndReturnsToIdle() throws Exception {
        RigBoard b = reliable();
        assertEquals(RigBoard.BRAKE_ENGAGED, b.command(RigBoard.BRAKE_TRIGGER));
        assertEquals(RigState.BUSY, b.state());
        waitFor(() -> b.state() == RigState.IDLE, 3000);
        assertEquals(1, b.commandsTotal());
    }

    @Test
    void rejectsCommandWhileBusy() {
        RigBoard b = reliable();
        b.command("PING");
        assertThrows(IllegalStateException.class, () -> b.command("PING"));
    }

    @Test
    void flashCompletesAndUpdatesFirmware() throws Exception {
        RigBoard b = reliable();
        b.flash("1.2.3", 1024);
        assertEquals(RigState.FLASHING, b.state());
        waitFor(() -> b.state() == RigState.IDLE, 3000);
        assertEquals("1.2.3", b.firmware());
        assertEquals(1, b.flashOk());
        assertEquals(0, b.flashFailed());
    }

    @Test
    void flashRequiresVersionAndImage() {
        RigBoard b = reliable();
        assertThrows(IllegalArgumentException.class, () -> b.flash("", 10));
        assertThrows(IllegalArgumentException.class, () -> b.flash("1.0.0", 0));
        assertEquals(RigState.IDLE, b.state());
    }

    @Test
    void faultyFlashLeavesBoardFailingAndKeepsOldFirmware() throws Exception {
        RigBoard b = alwaysFaulty();
        b.flash("9.9.9", 1024);
        waitFor(() -> b.state() == RigState.FAILING, 3000);
        assertEquals("0.0.0-factory", b.firmware());
        assertEquals(1, b.flashFailed());
        assertFalse(b.lastError().isBlank());
    }

    @Test
    void faultyCommandReturnsErrorAndFails() {
        RigBoard b = alwaysFaulty();
        assertEquals("ERROR", b.command(RigBoard.BRAKE_TRIGGER));
        assertEquals(RigState.FAILING, b.state());
    }

    @Test
    void resetRecoversFromFailing() {
        RigBoard b = reliable();
        b.injectFault("test");
        assertEquals(RigState.FAILING, b.state());
        assertThrows(IllegalStateException.class, () -> b.command("PING"));
        b.reset();
        assertEquals(RigState.IDLE, b.state());
        assertEquals("PONG", b.command("PING"));
    }

    @Test
    void metricsExposeExactlyOneActiveState() {
        RigBoard b = reliable();
        String m = Metrics.render(b);
        assertTrue(m.contains("rig_state{rig=\"rig-test-01\",lab=\"test\",state=\"idle\"} 1"));
        assertTrue(m.contains("state=\"busy\"} 0"));
        assertTrue(m.contains("rig_info{rig=\"rig-test-01\",lab=\"test\",firmware=\"0.0.0-factory\"} 1"));
    }

    @Test
    void jsonExtractorHandlesSimpleObjects() {
        assertEquals("PING", HttpApi.extractString("{\"cmd\":\"PING\"}", "cmd"));
        assertEquals("PING", HttpApi.extractString("{ \"cmd\" : \"PING\" }", "cmd"));
        assertNull(HttpApi.extractString("{\"other\":\"x\"}", "cmd"));
        assertNull(HttpApi.extractString(null, "cmd"));
    }

    private static void waitFor(java.util.function.BooleanSupplier cond, long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (!cond.getAsBoolean()) {
            if (System.currentTimeMillis() > deadline) fail("condition not met within " + timeoutMs + "ms");
            Thread.sleep(20);
        }
    }
}
