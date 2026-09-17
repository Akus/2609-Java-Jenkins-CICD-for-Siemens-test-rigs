package com.example.lab.rigsim;

import java.io.IOException;
import java.time.Duration;

/**
 * Entry point. Configuration via environment:
 *   RIG_ID          (default rig-local-01)
 *   RIG_LAB         (default local)
 *   RIG_PORT        (default 8080)
 *   FAIL_RATE       probability [0..1] of a random fault per command/flash (default 0.02)
 *   FLASH_SECONDS   how long a flash takes (default 8)
 */
public final class RigSimulator {

    public static void main(String[] args) throws IOException {
        String id = env("RIG_ID", "rig-local-01");
        String lab = env("RIG_LAB", "local");
        int port = Integer.parseInt(env("RIG_PORT", "8080"));
        double failRate = Double.parseDouble(env("FAIL_RATE", "0.02"));
        Duration flash = Duration.ofSeconds(Long.parseLong(env("FLASH_SECONDS", "8")));

        RigBoard board = new RigBoard(id, lab, failRate, flash);
        HttpApi api = new HttpApi(board, port);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            api.stop();
            board.shutdown();
        }));
        api.start();
        System.out.printf("[%s] rig simulator up on :%d (lab=%s failRate=%.2f flash=%ds)%n",
            id, port, lab, failRate, flash.getSeconds());
    }

    private static String env(String key, String def) {
        String v = System.getenv(key);
        return v == null || v.isBlank() ? def : v;
    }
}
