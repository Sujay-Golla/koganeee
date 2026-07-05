idf_component_register(
    SRCS
        "main.c"
        "wifi_udp.c"
        "link_fc.c"
        "audio_i2s.c"
        "display_spi.c"
        "camera_dvp.c"
        "servo_ledc.c"
    INCLUDE_DIRS "."
    REQUIRES
        nvs_flash
        esp_wifi
        esp_netif
        esp_event
        driver
        lwip
)
