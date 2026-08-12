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
    )
}

fun main(args: Array<String>) {
    runApplication<ApiApplication>(*args)
}
