idf_component_register(
    SRCS "app_main.c" "platform/board_pins.c"
    INCLUDE_DIRS "." "platform"
    PRIV_REQUIRES driver
)
