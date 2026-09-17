# Build agent that sits "next to the rigs": JDK 17 + Maven + Python + curl/jq for the rig scripts.
FROM jenkins/inbound-agent:latest-jdk17

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends maven python3 python3-requests curl jq git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*' \
 && git config --system protocol.file.allow always

COPY entrypoint.sh /usr/local/bin/lab-agent-entrypoint.sh
RUN chmod +x /usr/local/bin/lab-agent-entrypoint.sh

USER jenkins
ENV JENKINS_WEB_SOCKET=true
ENTRYPOINT ["/usr/local/bin/lab-agent-entrypoint.sh"]
