package com.example.lab.rigsim;

/** Renders the board state in Prometheus text exposition format (no client library needed). */
final class Metrics {

    private Metrics() {}

    static String render(RigBoard b) {
        String labels = "rig=\"" + b.id() + "\",lab=\"" + b.lab() + "\"";
        StringBuilder sb = new StringBuilder(1024);

        sb.append("# HELP rig_state 1 for the current state of the rig, 0 otherwise.\n");
        sb.append("# TYPE rig_state gauge\n");
        for (RigState s : RigState.values()) {
            sb.append("rig_state{").append(labels).append(",state=\"").append(s.name().toLowerCase())
              .append("\"} ").append(b.state() == s ? 1 : 0).append('\n');
        }

        sb.append("# HELP rig_info Static info about the rig.\n");
        sb.append("# TYPE rig_info gauge\n");
        sb.append("rig_info{").append(labels).append(",firmware=\"").append(b.firmware()).append("\"} 1\n");

        gauge(sb, "rig_uptime_seconds", "Seconds since the board booted.", labels, b.uptimeSeconds());
        gauge(sb, "rig_temperature_celsius", "Board temperature sensor.", labels, b.temperatureCelsius());
        counter(sb, "rig_commands_total", "Commands executed.", labels, b.commandsTotal());
        counter(sb, "rig_faults_total", "Faults (random or injected).", labels, b.faultsTotal());

        sb.append("# HELP rig_flash_total Firmware flash attempts by result.\n");
        sb.append("# TYPE rig_flash_total counter\n");
        sb.append("rig_flash_total{").append(labels).append(",result=\"ok\"} ").append(b.flashOk()).append('\n');
        sb.append("rig_flash_total{").append(labels).append(",result=\"failed\"} ").append(b.flashFailed()).append('\n');
        return sb.toString();
    }

    private static void gauge(StringBuilder sb, String name, String help, String labels, double v) {
        sb.append("# HELP ").append(name).append(' ').append(help).append('\n');
        sb.append("# TYPE ").append(name).append(" gauge\n");
        sb.append(name).append('{').append(labels).append("} ").append(v).append('\n');
    }

    private static void counter(StringBuilder sb, String name, String help, String labels, long v) {
        sb.append("# HELP ").append(name).append(' ').append(help).append('\n');
        sb.append("# TYPE ").append(name).append(" counter\n");
        sb.append(name).append('{').append(labels).append("} ").append(v).append('\n');
    }
}
