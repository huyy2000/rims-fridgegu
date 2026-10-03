idf_component_register(
    SRCS "app_main.c" "wifi_prov.c" "cloud_client.c"
         "audio_player.c" "audio_recorder.c" "buttons.c" "status_led.c"
         "platform/board_pins.c"
    INCLUDE_DIRS "." "platform"
    REQUIRES esp_wifi nvs_flash esp_http_server esp_http_client
             esp_driver_i2s esp_driver_gpio esp_driver_rmt json
)
