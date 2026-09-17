# ---- build: compile + run unit tests ----------------------------------------
FROM maven:3.9.8-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B package

# ---- runtime ----------------------------------------------------------------
FROM eclipse-temurin:17-jre-jammy
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/target/rig-sim.jar /app/rig-sim.jar
ENV RIG_PORT=8080
EXPOSE 8080
USER 65534
ENTRYPOINT ["java", "-XX:+UseSerialGC", "-Xmx64m", "-jar", "/app/rig-sim.jar"]
