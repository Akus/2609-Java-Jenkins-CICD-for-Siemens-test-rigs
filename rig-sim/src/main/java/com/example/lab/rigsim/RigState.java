package com.example.lab.rigsim;

/** Lifecycle states of a rig board as reported to the broker and dashboards. */
public enum RigState {
    /** Powered on, no test running, ready to accept commands or a flash. */
    IDLE,
    /** Executing a command / test sequence. */
    BUSY,
    /** Firmware image is being written; board is unreachable for commands. */
    FLASHING,
    /** Board has faulted (bad flash, hardware fault, injected fault). Needs reset. */
    FAILING
}
