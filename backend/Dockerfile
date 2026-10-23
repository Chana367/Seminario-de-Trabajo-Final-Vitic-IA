FROM maven:3.9.11-eclipse-temurin-21-alpine AS build
WORKDIR /workspace
COPY pom.xml .
RUN mvn -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -q clean package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S vitialert && adduser -S vitialert -G vitialert
WORKDIR /app
COPY --from=build /workspace/target/vitialert-backend-*.jar app.jar
USER vitialert
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]
