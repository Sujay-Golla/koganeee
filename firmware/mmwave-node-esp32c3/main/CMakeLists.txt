idf_component_register(
    SRCS "main.c" "ld2450.c" "wifi_udp.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_netif esp_event driver lwip
)
