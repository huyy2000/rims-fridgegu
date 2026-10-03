/* 云端客户端实现：esp_http_client + PSRAM 缓冲 + multipart 手工拼装。 */
#include "cloud_client.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"

static const char *TAG = "cloud";

static uint8_t *s_http_buf = NULL;
#define kHttpBufSize (320 * 1024)  /* TTS WAV 上限 ~10s，足够 */

static esp_err_t ensure_buf(void) {
    if (s_http_buf == NULL) {
        s_http_buf = heap_caps_malloc(kHttpBufSize, MALLOC_CAP_SPIRAM);
        if (!s_http_buf) return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

static size_t url_encode(const char *src, char *dst, size_t dstlen) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 4 < dstlen; i++) {
        unsigned char c = (unsigned char)src[i];
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
            dst[j++] = (char)c;
        } else {
            snprintf(dst + j, 4, "%%%02X", c);
            j += 3;
        }
    }
    dst[j] = '\0';
    return j;
}

esp_err_t cloud_get_tts(const char *server, const char *text,
                        const uint8_t **buf, size_t *len) {
    esp_err_t err = ensure_buf();
    if (err != ESP_OK) return err;

    char enc[256];
    url_encode(text, enc, sizeof(enc));
    char url[320];
    snprintf(url, sizeof(url), "%s/api/v1/recordings/tts?text=%s", server, enc);
    ESP_LOGI(TAG, "GET %s", url);

    esp_http_client_config_t cfg = {.url = url, .timeout_ms = 30000};
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_FAIL;
    err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        esp_http_client_cleanup(client);
        return err;
    }
    int status = esp_http_client_fetch_headers(client);
    size_t total = 0;
    int read_len;
    while ((read_len = esp_http_client_read(client, (char *)s_http_buf + total,
                                            kHttpBufSize - total)) > 0) {
        total += read_len;
        if (total >= kHttpBufSize) break;
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    int code = status;
    ESP_LOGI(TAG, "TTS 下载: %u bytes", (unsigned)total);
    if (total == 0 || (code >= 400 && code < 600 && code != 0)) {
        ESP_LOGE(TAG, "TTS 下载失败 status=%d", code);
        return ESP_FAIL;
    }
    *buf = s_http_buf;
    *len = total;
    return ESP_OK;
}

esp_err_t cloud_upload_recording(const char *server, const uint8_t *wav_header,
                                 size_t header_len, const uint8_t *pcm,
                                 size_t pcm_len, const char *zone,
                                 char *reply_out, size_t reply_len, bool *speak_out) {
    esp_err_t err = ensure_buf();
    if (err != ESP_OK) return err;

    const char *boundary = "fridgegu1234567890";
    char head[512], tail[192];
    int head_len = snprintf(head, sizeof(head),
                            "--%s\r\n"
                            "Content-Disposition: form-data; name=\"audio\"; filename=\"record.wav\"\r\n"
                            "Content-Type: audio/wav\r\n\r\n",
                            boundary);
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat-truncation"  /* boundary 固定 18 字节，实际不会截断 */
    int tail_len = snprintf(tail, sizeof(tail),
                            "\r\n--%s\r\n"
                            "Content-Disposition: form-data; name=\"user_id\"\r\n\r\ndemo\r\n"
                            "--%s\r\n"
                            "Content-Disposition: form-data; name=\"channel\"\r\n\r\ndevice\r\n"
                            "--%s--\r\n",
                            boundary, boundary, boundary);
#pragma GCC diagnostic pop
    size_t body_len = head_len + header_len + pcm_len + tail_len;
    if (body_len > kHttpBufSize) {
        ESP_LOGE(TAG, "录音体太大: %u", (unsigned)body_len);
        return ESP_ERR_NO_MEM;
    }
    memcpy(s_http_buf, head, head_len);
    memcpy(s_http_buf + head_len, wav_header, header_len);
    memcpy(s_http_buf + head_len + header_len, pcm, pcm_len);
    memcpy(s_http_buf + head_len + header_len + pcm_len, tail, tail_len);

    char url[192];
    snprintf(url, sizeof(url), "%s/api/v1/recordings", server);
    char ctype[96];
    snprintf(ctype, sizeof(ctype), "multipart/form-data; boundary=%s", boundary);
    ESP_LOGI(TAG, "POST %s (%u bytes)", url, (unsigned)body_len);

    esp_http_client_config_t cfg = {.url = url, .timeout_ms = 30000};
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return ESP_FAIL;
    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", ctype);
    err = esp_http_client_open(client, body_len);
    if (err != ESP_OK) {
        esp_http_client_cleanup(client);
        return err;
    }
    int w = esp_http_client_write(client, (const char *)s_http_buf, body_len);
    if (w < 0 || (size_t)w != body_len) {
        ESP_LOGE(TAG, "上传写失败 w=%d", w);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }
    esp_http_client_fetch_headers(client);
    int read_len;
    size_t total = 0;
    while ((read_len = esp_http_client_read(client, (char *)s_http_buf + total,
                                            kHttpBufSize - 1 - total)) > 0) {
        total += read_len;
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    s_http_buf[total] = '\0';
    ESP_LOGI(TAG, "上传响应: %.*s", (int)(total > 200 ? 200 : total), (char *)s_http_buf);

    cJSON *root = cJSON_Parse((const char *)s_http_buf);
    if (speak_out) *speak_out = false;
    if (reply_out && reply_len > 0) {
        if (speak_out) {
            cJSON *sp = cJSON_GetObjectItem(root, "speak");
            *speak_out = cJSON_IsBool(sp) ? cJSON_IsTrue(sp) : false;
        }
        reply_out[0] = '\0';
        if (root) {
            cJSON *reply = cJSON_GetObjectItem(root, "reply");
            if (cJSON_IsString(reply)) {
                strlcpy(reply_out, reply->valuestring, reply_len);
            }
        }
    }
    cJSON_Delete(root);
    return ESP_OK;
}
