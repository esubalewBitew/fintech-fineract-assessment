# Build customized Apache Fineract 1.16.1 with assessment patches.
# FOR TESTING / ASSESSMENT ONLY — NOT FOR PRODUCTION.

FROM eclipse-temurin:25-jdk AS build
WORKDIR /src

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG FINERACT_TAG=1.16.1
RUN git clone --depth 1 --branch "${FINERACT_TAG}" https://github.com/apache/fineract.git .

COPY patches /patches
RUN git config user.email "assessment@local" \
    && git config user.name "assessment" \
    && git am /patches/*.patch

# Integration tests are not run inside the image build.
ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.jvmargs=-Xmx3g"
RUN ./gradlew :fineract-provider:bootJar -x test -x spotlessCheck -x checkstyleMain -x checkstyleTest

FROM eclipse-temurin:25-jre
WORKDIR /app
COPY --from=build /src/fineract-provider/build/libs/fineract-provider-*.jar /app/fineract.jar
EXPOSE 8080 8443
USER 1000:1000
ENTRYPOINT ["java", \
  "-Duser.home=/tmp", \
  "-Dfile.encoding=UTF-8", \
  "-Duser.timezone=UTC", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "/app/fineract.jar"]
