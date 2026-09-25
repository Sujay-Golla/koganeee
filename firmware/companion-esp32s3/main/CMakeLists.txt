idf_component_register(
    SRCS
        "main.c"
        "wifi_udp.c"
        "telemetry.c"
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
        lwip
    PRIV_REQUIRES
        esp_driver_uart
        esp_driver_ledc
        esp_driver_spi  # display_spi.c: SPI2 bus for the ILI9341 panel
        esp_driver_gpio # display_spi.c: backlight line (the panel reset is not a GPIO)
        esp_driver_i2s  # audio_i2s.c: full-duplex STD channel pair (mic + speaker)
        esp_lcd         # display_spi.c: esp_lcd_new_panel_io_spi (SPI panel IO layer)
        esp_timer      # wifi_udp.c: reconnect backoff + rx reject log rate limit
        esp_http_server # camera_dvp.c: MJPEG /stream, /snapshot, / index
        espressif__esp32-camera # camera_dvp.c: OV2640 DVP driver (managed component)
)
