// HIL pipeline for the test-rig lab.
//
//   Commit → Build (Java) → Unit Tests → Package/Artifact
//     → Reserve Rig → Flash/Deploy → Verify Boot → HIL Integration Tests
//     → Report → Release Rig (always)
//
// Rig contention is handled twice on purpose, to show both approaches from the design notes:
//   1. Jenkins Lockable Resources: lock(label: LAB) blocks until a rig with that label is free.
//   2. The rig broker API (rig-api): reserve/release with a TTL, so a watchdog can free the rig
//      even if Jenkins itself dies mid-run. The broker is also what non-Jenkins tooling talks to.

pipeline {
    agent { label 'lab' }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30'))
        // Concurrent builds are allowed on purpose: start 3 Vienna builds and watch the third
        // queue on the lock until a rig frees up.
    }

    parameters {
        choice(name: 'LAB', choices: ['vienna', 'munich'], description: 'Which lab to reserve a rig in')
        string(name: 'FIRMWARE_VERSION', defaultValue: '', description: 'Firmware version to flash; empty = 1.0.<build number>')
        booleanParam(name: 'QUARANTINE_ON_FAILURE', defaultValue: true, description: 'Quarantine the rig via the broker if HIL tests fail and the rig is not IDLE afterwards')
    }

    environment {
        RIG_API_URL = 'http://rig-api:8000'
        OWNER       = "${env.JOB_NAME}#${env.BUILD_NUMBER}"
        FW_VERSION  = "${params.FIRMWARE_VERSION ?: '1.0.' + env.BUILD_NUMBER}"
        MAVEN_OPTS  = '-Dmaven.repo.local=/home/jenkins/.m2/repository -Djava.awt.headless=true'
        MAVEN_ARGS  = '-B -ntp'
    }

    stages {
        stage('Build') {
            steps {
                // The repo may be committed from Windows, where git cannot store the exec bit.
                sh 'chmod +x scripts/*.sh'
                sh 'mvn $MAVEN_ARGS -f rig-sim/pom.xml clean compile'
            }
        }

        stage('Unit Tests') {
            steps {
                sh 'mvn $MAVEN_ARGS -f rig-sim/pom.xml test'
            }
            post {
                always {
                    junit 'rig-sim/target/surefire-reports/*.xml'
                }
            }
        }

        stage('Package') {
            steps {
                sh 'mvn $MAVEN_ARGS -f rig-sim/pom.xml -DskipTests package'
                // The jar plays the role of the firmware image. Version + checksum travel with it.
                sh '''
                    mkdir -p artifacts
                    cp rig-sim/target/rig-sim.jar artifacts/firmware-${FW_VERSION}.bin
                    sha256sum artifacts/firmware-${FW_VERSION}.bin > artifacts/firmware-${FW_VERSION}.bin.sha256
                '''
                archiveArtifacts artifacts: 'artifacts/*', fingerprint: true
            }
        }

        stage('Reserve Rig') {
            steps {
                script {
                    // Jenkins-side lock: pick any free rig labelled with the requested lab.
                    lock(label: params.LAB, quantity: 1, variable: 'RIG') {
                        env.RIG_ID = env.RIG
                        echo "Locked Jenkins resource ${env.RIG_ID}"
                        // Broker-side reservation: TTL guards against a dead controller holding the rig.
                        sh 'scripts/rig-cli.sh reserve "$RIG_ID" --owner "$OWNER" --ttl 1500'
                        env.RIG_HOST = sh(script: 'scripts/rig-cli.sh host "$RIG_ID"', returnStdout: true).trim()
                        echo "Rig ${env.RIG_ID} reserved for ${env.OWNER} (host ${env.RIG_HOST})"
                        runOnRig()
                    }
                }
            }
        }

        stage('Report') {
            steps {
                script {
                    def ts = sh(script: 'date -u -Iseconds', returnStdout: true).trim()
                    def summary = [
                        "Firmware version : ${env.FW_VERSION}",
                        "Rig              : ${env.RIG_ID} (${params.LAB})",
                        "Build            : ${env.BUILD_URL}",
                        "Timestamp        : ${ts}",
                        "Result           : ${currentBuild.currentResult}",
                    ].join('\n') + '\n'
                    writeFile file: 'artifacts/hil-report.txt', text: summary
                    echo summary
                    archiveArtifacts artifacts: 'artifacts/hil-report.txt'
                }
            }
        }
    }

    post {
        always {
            script {
                // Belt and braces: the lock block already ended, but make sure the broker side is free too.
                if (env.RIG_ID) {
                    sh 'scripts/rig-cli.sh release "$RIG_ID" --owner "$OWNER" || true'
                }
            }
            cleanWs(deleteDirs: true, notFailBuild: true)
        }
    }
}

// Everything that must happen while the lock is held lives here, so a failure in any step
// still runs the release in post{} and the lock block's own cleanup.
def runOnRig() {
    stage('Flash Firmware') {
        retry(2) {
            sh 'scripts/flash-tool.sh --rig "$RIG_ID" --image artifacts/firmware-${FW_VERSION}.bin --version "$FW_VERSION" --timeout 120'
        }
    }

    stage('Verify Boot') {
        sh 'scripts/rig-cli.sh wait-for-ready "$RIG_ID" --timeout 120'
        sh 'scripts/rig-cli.sh status "$RIG_ID"'
    }

    stage('HIL Tests') {
        try {
            sh """
                mvn \$MAVEN_ARGS -f hil-tests/pom.xml verify -Prig-integration \
                    -Drig.host=${env.RIG_HOST} -Drig.port=8080 \
                    -Dexpected.firmware=${env.FW_VERSION}
            """
        } catch (err) {
            echo "HIL tests failed on ${env.RIG_ID}: ${err}"
            // Distinguish "code is broken" (rig still IDLE → just a red build) from "rig is broken"
            // (rig FAILING/UNREACHABLE → take it out of the pool so the next build gets a healthy one).
            env.RIG_STATE = sh(script: 'scripts/rig-cli.sh state "$RIG_ID"', returnStdout: true).trim()
            if (params.QUARANTINE_ON_FAILURE && env.RIG_STATE != 'IDLE') {
                sh 'scripts/rig-cli.sh quarantine "$RIG_ID" --reason "HIL failure in $OWNER, rig state $RIG_STATE"'
                unstable("Rig ${env.RIG_ID} quarantined – hardware suspected")
            }
            throw err
        } finally {
            junit allowEmptyResults: true, testResults: 'hil-tests/target/failsafe-reports/*.xml'
        }
    }
}
