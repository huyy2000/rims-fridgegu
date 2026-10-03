#pragma once
/* 配网模块：SoftAP "fridgegu-setup" + 内置表单页 → NVS 保存 → 重启连 STA。
 * NVS 命名空间 "fridgegu"：ssid / pass / server。
 * 沿 ADR-5 的精神（不依赖手机 App，浏览器即可），MVP 用 SoftAP 而非 BLE。
 */
#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char ssid[33];
    char pass[64];
    char server[128];   /* 例如 http://192.168.1.10:8000 */
} fridgegu_config_t;

/* 从 NVS 读取配置；missing 置 true 表示 SSID 尚未配过。 */
esp_err_t prov_load(fridgegu_config_t *cfg, bool *missing);

/* 保存配置到 NVS。 */
esp_err_t prov_save(const fridgegu_config_t *cfg);

/* 启动 SoftAP 配网（阻塞，直到保存后重启）。 */
esp_err_t prov_start_softap(void);

/* 以 NVS 配置连 STA；timeout_ms 内未连上返回 ESP_ERR_TIMEOUT。 */
esp_err_t prov_connect_sta(const fridgegu_config_t *cfg, int timeout_ms);

#ifdef __cplusplus
}
#endif
