/* 配网实现：SoftAP + 表单页 → NVS；STA 连接。 */
#include "wifi_prov.h"

#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "prov";
#define kNvsNs "fridgegu"
static EventGroupHandle_t s_wifi_events;
#define kBitConnected BIT0

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "STA 断开，重连");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_wifi_events, kBitConnected);
    }
}

esp_err_t prov_load(fridgegu_config_t *cfg, bool *missing) {
    memset(cfg, 0, sizeof(*cfg));
    nvs_handle_t h;
    esp_err_t err = nvs_open(kNvsNs, NVS_READONLY, &h);
    if (err != ESP_OK) {
        *missing = true;
        return ESP_OK;
    }
    size_t len = sizeof(cfg->ssid);
    err = nvs_get_str(h, "ssid", cfg->ssid, &len);
    len = sizeof(cfg->pass);
    nvs_get_str(h, "pass", cfg->pass, &len);
    len = sizeof(cfg->server);
    nvs_get_str(h, "server", cfg->server, &len);
    nvs_close(h);
    *missing = (cfg->ssid[0] == '\0');
    return err == ESP_OK || err == ESP_ERR_NVS_NOT_FOUND ? ESP_OK : err;
}

esp_err_t prov_save(const fridgegu_config_t *cfg) {
    nvs_handle_t h;
    esp_err_t err = nvs_open(kNvsNs, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    nvs_set_str(h, "ssid", cfg->ssid);
    nvs_set_str(h, "pass", cfg->pass);
    nvs_set_str(h, "server", cfg->server);
    err = nvs_commit(h);
    nvs_close(h);
    return err;
}

static const char *kFormPage =
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>冰箱菇 配网</title></head>"
    "<body style='font-family:sans-serif;max-width:420px;margin:40px auto'>"
    "<h2>🍄 冰箱菇 配网</h2>"
    "<p>填写家里 Wi-Fi 和电脑上的后端地址：</p>"
    "<form action='/save' method='get'>"
    "<p>Wi-Fi 名称<br><input name='ssid' style='width:100%'></p>"
    "<p>Wi-Fi 密码<br><input name='pass' type='password' style='width:100%'></p>"
    "<p>后端地址<br><input name='server' placeholder='http://192.168.1.10:8000' style='width:100%'></p>"
    "<p><button style='width:100%;padding:12px;background:#E85513;color:#fff;border:0;border-radius:8px'>保存并重启</button></p>"
    "</form></body></html>";

static esp_err_t page_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    return httpd_resp_send(req, kFormPage, HTTPD_RESP_USE_STRLEN);
}

static size_t url_decode(char *s) {
    /* 原地 %XX 解码 + '+' -> 空格；返回解码后长度 */
    char *w = s;
    for (char *r = s; *r; ) {
        if (*r == '%' && r[1] && r[2]) {
            char hex[3] = {r[1], r[2], 0};
            *w++ = (char)strtol(hex, NULL, 16);
            r += 3;
        } else if (*r == '+') {
            *w++ = ' ';
            r++;
        } else {
            *w++ = *r++;
        }
    }
    *w = '\0';
    return (size_t)(w - s);
}

static esp_err_t save_handler(httpd_req_t *req) {
    fridgegu_config_t cfg = {0};
    char buf[384] = {0};
    size_t qlen = httpd_req_get_url_query_len(req) + 1;
    if (qlen > sizeof(buf)) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "query too long");
    httpd_req_get_url_query_str(req, buf, qlen);
    char val[160];
    if (httpd_query_key_value(buf, "ssid", val, sizeof(val)) == ESP_OK) {
        url_decode(val);
        strlcpy(cfg.ssid, val, sizeof(cfg.ssid));
    }
    if (httpd_query_key_value(buf, "pass", val, sizeof(val)) == ESP_OK) {
        url_decode(val);
        strlcpy(cfg.pass, val, sizeof(cfg.pass));
    }
    if (httpd_query_key_value(buf, "server", val, sizeof(val)) == ESP_OK) {
        url_decode(val);
        strlcpy(cfg.server, val, sizeof(cfg.server));
    }
    if (cfg.ssid[0] == '\0') return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "ssid required");
    prov_save(&cfg);
    ESP_LOGI(TAG, "配置已保存: ssid=%s server=%s", cfg.ssid, cfg.server);
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_send(req, "<h3>已保存，重启中…</h3>", HTTPD_RESP_USE_STRLEN);
    vTaskDelay(pdMS_TO_TICKS(800));
    esp_restart();
    return ESP_OK;
}

esp_err_t prov_start_softap(void) {
    uint8_t mac[6];
    esp_efuse_mac_get_default(mac);
    char ssid[33];
    snprintf(ssid, sizeof(ssid), "fridgegu-%02X%02X", mac[4], mac[5]);

    /* AP 网络接口 + DHCP 服务器：缺了它热点能被扫到但手机连不上（拿不到 IP） */
    if (esp_netif_create_default_wifi_ap() == NULL) {
        ESP_LOGE(TAG, "创建 AP netif 失败");
        return ESP_FAIL;
    }

    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wcfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    wifi_config_t ap_cfg = {0};
    strlcpy((char *)ap_cfg.ap.ssid, ssid, sizeof(ap_cfg.ap.ssid));
    ap_cfg.ap.ssid_len = strlen(ssid);
    ap_cfg.ap.channel = 6;
    ap_cfg.ap.max_connection = 2;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "SoftAP 已开启: %s（浏览器访问 http://192.168.4.1）", ssid);

    httpd_handle_t server = NULL;
    httpd_config_t scfg = HTTPD_DEFAULT_CONFIG();
    ESP_ERROR_CHECK(httpd_start(&server, &scfg));
    httpd_uri_t u_page = {.uri = "/", .method = HTTP_GET, .handler = page_handler};
    httpd_uri_t u_save = {.uri = "/save", .method = HTTP_GET, .handler = save_handler};
    httpd_register_uri_handler(server, &u_page);
    httpd_register_uri_handler(server, &u_save);
    return ESP_OK;
}

esp_err_t prov_connect_sta(const fridgegu_config_t *cfg, int timeout_ms) {
    s_wifi_events = xEventGroupCreate();
    /* STA 网络接口 + DHCP 客户端：缺了它 L2 连上后拿不到 IP，永远等不到 GOT_IP */
    if (esp_netif_create_default_wifi_sta() == NULL) {
        ESP_LOGE(TAG, "创建 STA netif 失败");
        return ESP_FAIL;
    }
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL));

    wifi_init_config_t wcfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wcfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    wifi_config_t sta_cfg = {0};
    strlcpy((char *)sta_cfg.sta.ssid, cfg->ssid, sizeof(sta_cfg.sta.ssid));
    strlcpy((char *)sta_cfg.sta.password, cfg->pass, sizeof(sta_cfg.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(s_wifi_events, kBitConnected, pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(timeout_ms));
    if (bits & kBitConnected) {
        ESP_LOGI(TAG, "Wi-Fi 已连接: %s", cfg->ssid);
        return ESP_OK;
    }
    ESP_LOGW(TAG, "Wi-Fi 连接超时");
    return ESP_ERR_TIMEOUT;
}
