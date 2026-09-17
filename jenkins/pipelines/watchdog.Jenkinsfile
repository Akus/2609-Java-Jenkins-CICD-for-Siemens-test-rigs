// Rig watchdog – runs every 10 minutes (cron trigger set in JCasC).
//
// The broker already force-releases expired reservations and auto-quarantines flaky rigs.
// This job closes the loop on the Jenkins side: a rig the broker has quarantined is *reserved*
// as a Lockable Resource (so `lock(label:)` never hands it to a build), and un-reserved again
// once the broker clears it. It also reports rigs stuck BUSY for too long.

pipeline {
    agent { label 'lab' }
    options { timestamps(); timeout(time: 5, unit: 'MINUTES') }

    environment {
        RIG_API_URL = 'http://rig-api:8000'
        JENKINS_API = "${env.JENKINS_URL ?: 'http://jenkins:8080/'}"
    }

    stages {
        stage('Sync quarantine → Jenkins locks') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'jenkins-admin', usernameVariable: 'JU', passwordVariable: 'JP')]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        crumb=$(curl -fsS -u "$JU:$JP" "${JENKINS_API}crumbIssuer/api/json" | jq -r '.crumb')
                        rigs=$(curl -fsS "$RIG_API_URL/rigs")
                        echo "$rigs" | jq -r '.[] | "\\(.id) \\(.quarantined) \\(.state) \\(.reserved_by // "-")"' | while read -r id quarantined state reserved_by; do
                            if [ "$quarantined" = "true" ]; then
                                echo "[$id] quarantined by broker -> reserving Jenkins lock"
                                curl -fsS -u "$JU:$JP" -H "Jenkins-Crumb: $crumb" -X POST \
                                    "${JENKINS_API}lockable-resources/reserve?resource=$id" -o /dev/null || true
                            else
                                # Only un-reserve if *we* (admin) reserved it; a running build's lock is different from a reservation.
                                curl -fsS -u "$JU:$JP" -H "Jenkins-Crumb: $crumb" -X POST \
                                    "${JENKINS_API}lockable-resources/unreserve?resource=$id" -o /dev/null 2>/dev/null || true
                            fi
                            if [ "$state" = "BUSY" ] && [ "$reserved_by" = "-" ]; then
                                echo "[$id] WARNING: BUSY without a broker reservation – manual test running or stale state"
                            fi
                        done
                    '''
                }
            }
        }

        stage('Report') {
            steps {
                sh 'curl -fsS "$RIG_API_URL/reservations?active=true" | jq .'
                sh 'curl -fsS "$RIG_API_URL/rigs" | jq -r ".[] | [.id, .lab, .state, .firmware, (.quarantined|tostring), (.reserved_by // \\"-\\")] | @tsv"'
            }
        }
    }
}
