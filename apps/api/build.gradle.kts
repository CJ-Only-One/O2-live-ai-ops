// 서비스마다 독립된 Gradle 빌드를 둔다.
// 루트에서 묶는 멀티프로젝트로 하면 서비스 하나만 고쳐도 전체가 엮여서
// "바뀐 서비스만 빌드"가 어려워진다.

plugins {
    kotlin("jvm") version "2.1.20"
    kotlin("plugin.spring") version "2.1.20"
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.o2"
version = "0.0.1-SNAPSHOT"

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    // actuator의 probe 엔드포인트를 쿠버네티스가 그대로 쓴다.
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin {
    compilerOptions { freeCompilerArgs.add("-Xjsr305=strict") }
}

tasks.withType<Test> { useJUnitPlatform() }
