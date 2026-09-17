package com.example.lab.rigsim;

import java.time.Duration;
import java.time.Instant;
import java.util.Random;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * The simulated board: a small state machine with a random fault injector.
 * No HTTP here – this class is what the unit tests exercise.
 */
public final class RigBoard {

    public static final String BRAKE_TRIGGER = "SIMULATE_BRAKE_TRIGGER";
    public static final String BRAKE_ENGAGED = "BRAKE_ENGAGED";

    private final String id;
    private final String lab;
    private final double failRate;
    private final Duration flashDuration;
    private final Random random;
    private final ScheduledExecutorService scheduler;
    private final Instant bootedAt = Instant.now();

    private volatile RigState state = RigState.IDLE;
    private volatile String firmware = "0.0.0-factory";
    private volatile String lastCommand = "";
    private volatile String lastResult = "";
    private volatile String lastError = "";
    private volatile long pendingFirmwareBytes = 0;

    private final AtomicLong commandsTotal = new AtomicLong();
    private final AtomicLong flashOk = new AtomicLong();
    private final AtomicLong flashFailed = new AtomicLong();
    private final AtomicLong faultsTotal = new AtomicLong();

    public RigBoard(String id, String lab, double failRate, Duration flashDuration) {
        this(id, lab, failRate, flashDuration, new Random());
    }

    /** Seeded constructor for deterministic tests. */
    public RigBoard(String id, String lab, double failRate, Duration flashDuration, Random random) {
        this.id = id;
        this.lab = lab;
        this.failRate = failRate;
        this.flashDuration = flashDuration;
        this.random = random;
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "rig-" + id + "-worker");
            t.setDaemon(true);
            return t;
        });
    }

    // ------------------------------------------------------------ commands

    /**
     * Execute a command. Returns the result string the HIL tests poll for.
     * The board goes BUSY for a short while and then back to IDLE (or FAILING on a random fault).
     */
    public synchronized String command(String cmd) {
        if (state != RigState.IDLE) {
            throw new IllegalStateException("rig " + id + " is " + state + ", cannot accept command");
        }
        commandsTotal.incrementAndGet();
        lastCommand = cmd;
        state = RigState.BUSY;
        if (random.nextDouble() < failRate) {
            fail("random fault while executing " + cmd);
            return "ERROR";
        }
        String result;
        switch (cmd) {
            case BRAKE_TRIGGER -> result = BRAKE_ENGAGED;
            case "SELF_TEST" -> result = "SELF_TEST_OK";
            case "PING" -> result = "PONG";
            default -> result = "UNKNOWN_COMMAND";
        }
        lastResult = result;
        // Simulate execution time: hold BUSY for ~1 s, then return to IDLE.
        scheduler.schedule(this::finishCommand, 1, TimeUnit.SECONDS);
        return result;
    }

    private synchronized void finishCommand() {
        if (state == RigState.BUSY) {
            state = RigState.IDLE;
        }
    }

    // --------------------------------------------------------------- flash

    /** Start an asynchronous firmware flash. Board goes FLASHING, then IDLE or FAILING. */
    public synchronized void flash(String version, long imageBytes) {
        if (state != RigState.IDLE) {
            throw new IllegalStateException("rig " + id + " is " + state + ", cannot flash");
        }
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("firmware version header missing");
        }
        if (imageBytes <= 0) {
            throw new IllegalArgumentException("empty firmware image");
        }
        state = RigState.FLASHING;
        pendingFirmwareBytes = imageBytes;
        lastCommand = "FLASH " + version;
        scheduler.schedule(() -> completeFlash(version), flashDuration.toMillis(), TimeUnit.MILLISECONDS);
    }

    synchronized void completeFlash(String version) {
        if (state != RigState.FLASHING) {
            return;
        }
        if (random.nextDouble() < failRate) {
            flashFailed.incrementAndGet();
            fail("flash verification failed for " + version);
            return;
        }
        firmware = version;
        flashOk.incrementAndGet();
        lastResult = "FLASH_OK";
        state = RigState.IDLE;
    }

    // --------------------------------------------------------------- faults

    /** Chaos hook: force the board into FAILING. */
    public synchronized void injectFault(String reason) {
        fail(reason == null || reason.isBlank() ? "fault injected via API" : reason);
    }

    private void fail(String reason) {
        faultsTotal.incrementAndGet();
        lastError = reason;
        lastResult = "ERROR";
        state = RigState.FAILING;
    }

    /** Remote reset – what an operator / watchdog would do at 2am. */
    public synchronized void reset() {
        state = RigState.IDLE;
        lastError = "";
        lastResult = "RESET_OK";
    }

    // -------------------------------------------------------------- getters

    public String id() { return id; }
    public String lab() { return lab; }
    public RigState state() { return state; }
    public String firmware() { return firmware; }
    public String lastCommand() { return lastCommand; }
    public String lastResult() { return lastResult; }
    public String lastError() { return lastError; }
    public long pendingFirmwareBytes() { return pendingFirmwareBytes; }
    public long uptimeSeconds() { return Duration.between(bootedAt, Instant.now()).getSeconds(); }
    public long commandsTotal() { return commandsTotal.get(); }
    public long flashOk() { return flashOk.get(); }
    public long flashFailed() { return flashFailed.get(); }
    public long faultsTotal() { return faultsTotal.get(); }

    /** Fake sensor: warmer when busy/flashing, hot when failing. */
    public double temperatureCelsius() {
        double base = switch (state) {
            case IDLE -> 38.0;
            case BUSY -> 47.0;
            case FLASHING -> 52.0;
            case FAILING -> 71.0;
        };
        return Math.round((base + random.nextGaussian() * 1.5) * 10.0) / 10.0;
    }

    public void shutdown() {
        scheduler.shutdownNow();
    }
}
