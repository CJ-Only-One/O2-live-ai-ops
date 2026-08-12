package com.o2.api

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

@SpringBootApplication
class ApiApplication

@RestController
class HelloController {
    @GetMapping("/")
    fun hello(): Map<String, String> = mapOf(
        "service" to "o2-api",
        "message" to "hello",
        // PR 경로와 브랜치 보호 아래에서의 배포를 확인하려고 넣은 값이다.
        "via" to "pull-request",
    )
}

fun main(args: Array<String>) {
    runApplication<ApiApplication>(*args)
}
