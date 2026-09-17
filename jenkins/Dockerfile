FROM jenkins/jenkins:lts-jdk17

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl jq git \
 && rm -rf /var/lib/apt/lists/* \
 # The pipeline job clones the bind-mounted repo (file:///repo) which is owned by another uid.
 && git config --system --add safe.directory '*' \
 && git config --system protocol.file.allow always
USER jenkins

# Pre-bake plugins so first boot needs no internet round-trips through the UI.
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
ENV CASC_JENKINS_CONFIG=/var/jenkins_home/casc
