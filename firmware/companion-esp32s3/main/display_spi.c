/*
 * ILI9341 320x240 SPI display.
 *
 * Panel driver choice: this uses esp_lcd's SPI *panel IO* layer
 * (esp_lcd_new_panel_io_spi) plus a local ILI9341 command sequence, NOT
 * esp_lcd_new_panel_ili9341(). Reason: IDF 6.1 core ships only the ST7789 and
 * SSD1306 panel drivers in components/esp_lcd — the ILI9341 driver lives in the
 * separate `espressif/esp_lcd_ili9341` managed component, which would mean a
 * component-registry fetch. Since all this app needs from a panel driver is
 * "init, set window, push pixels", the init sequence is inlined here and the
 * DMA / DC-line plumbing is still esp_lcd's. Nothing is hand-rolled on the SPI
 * side and there is no new dependency.
 *
 * Rendering strategy: no framebuffer. Everything is drawn through one
 * DMA-capable band buffer of 320 x BAND_ROWS pixels and blitted a band at a
 * time. The status screen is all text, so per-line bands are a natural fit, and
 * it keeps ~20 KB of internal RAM in play instead of a 150 KB framebuffer (the
 * board has PSRAM, but a PSRAM framebuffer would add a DMA-source constraint for
 * no benefit to a text readout).
 *
 * Fail-soft: init errors log once and leave the task running with s_panel_ok
 * false, so nothing here can block boot or take Wi-Fi/UDP/telemetry down with
 * it. Note this board routes no MISO (PINMAP.md lists SDI only), so the panel ID
 * cannot be read back — "the panel does not respond" is therefore not detectable
 * from the host side. Only host-side failures (bus init, IO alloc, buffer alloc)
 * are caught. A dead or unwired panel presents as a blank screen and a normal
 * log, which is the best this wiring can do.
 *
 * TODO(kogane): XPT2046 touch on the shared SPI bus; report events back to base.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "display_spi.h"
#include "display_font.h"
#include "kogane_msg.h"
#include "servo_ledc.h"
#include "telemetry.h"
#include "wifi_udp.h"

static const char *TAG = "display_spi";

#define LCD_H_RES   320
#define LCD_V_RES   240
#define LCD_HOST    SPI2_HOST

/* 32 rows covers the tallest thing drawn (the scale-4 title, 8*4 = 32 px). */
#define BAND_ROWS   32
#define BAND_PIXELS (LCD_H_RES * BAND_ROWS)
#define BAND_BYTES  (BAND_PIXELS * 2)

/* ---- ILI9341 commands used here ---- */
#define ILI_NOP     0x00
#define ILI_SWRESET 0x01
#define ILI_SLPOUT  0x11
#define ILI_DISPON  0x29
#define ILI_CASET   0x2A
#define ILI_RASET   0x2B
#define ILI_RAMWR   0x2C
#define ILI_MADCTL  0x36
#define ILI_PIXFMT  0x3A

/* Logical RGB565 colours (byte-swapped at write time, see wire565()). */
#define C_BG     0x0841   /* near-black blue-grey */
#define C_WHITE  0xFFFF
#define C_AMBER  0xFD20
#define C_CYAN   0x07FF
#define C_GREEN  0x07E0
#define C_RED    0xF800
#define C_GREY   0x8410

/*
 * ILI9341 in 16-bit/pixel mode clocks the high byte of each RGB565 word first,
 * and esp_lcd_panel_io_tx_color sends the buffer in memory order, so every pixel
 * is stored byte-swapped. Doing it here rather than at blit time keeps the blit
 * a straight DMA of whatever is in the band buffer.
 */
static inline uint16_t wire565(uint16_t c) { return (uint16_t)((c >> 8) | (c << 8)); }

static esp_lcd_panel_io_handle_t s_io;
static uint16_t *s_band;            /* DMA-capable, BAND_PIXELS entries */
static bool s_panel_ok;

/* ---- low-level panel access ---- */

static inline void lcd_cmd(uint8_t cmd, const uint8_t *data, size_t len)
{
    esp_lcd_panel_io_tx_param(s_io, cmd, data, len);
}

static void lcd_blit(int x, int y, int w, int h, const uint16_t *px)
{
    if (!s_panel_ok || w <= 0 || h <= 0) return;
    uint8_t ca[4] = { (uint8_t)(x >> 8), (uint8_t)x,
                      (uint8_t)((x + w - 1) >> 8), (uint8_t)(x + w - 1) };
    uint8_t ra[4] = { (uint8_t)(y >> 8), (uint8_t)y,
                      (uint8_t)((y + h - 1) >> 8), (uint8_t)(y + h - 1) };
    lcd_cmd(ILI_CASET, ca, 4);
    lcd_cmd(ILI_RASET, ra, 4);
    esp_lcd_panel_io_tx_color(s_io, ILI_RAMWR, px, (size_t)w * h * 2);
    /* tx_color is queued, not synchronous, and the caller is about to overwrite
     * the band buffer. Any tx_param drains every in-flight colour transaction
     * first, so a NOP here is the cheapest way to make this call blocking and
     * the band buffer safe to reuse on return. */
    lcd_cmd(ILI_NOP, NULL, 0);
}

/* ---- band-buffer drawing ---- */

static void band_fill(uint16_t colour, int rows)
{
    uint16_t w = wire565(colour);
    size_t n = (size_t)LCD_H_RES * rows;
    for (size_t i = 0; i < n; ++i) s_band[i] = w;
}

/* Render `s` into the band at pixel column x0, scaled `scale`x from the 5x7
 * glyphs. Clips at the right edge; does not wrap. */
static void band_text(int x0, int scale, uint16_t fg, const char *s)
{
    uint16_t w = wire565(fg);
    for (const char *p = s; *p; ++p) {
        unsigned char ch = (unsigned char)*p;
        if (ch < KGN_FONT_FIRST || ch > KGN_FONT_LAST) ch = '?';
        const uint8_t *g = kgn_font5x7[ch - KGN_FONT_FIRST];
        for (int col = 0; col < KGN_FONT_W; ++col) {
            int gx = x0 + col * scale;
            if (gx >= LCD_H_RES) return;
            for (int row = 0; row < KGN_FONT_CELL_H; ++row) {
                if (!(g[col] & (1u << row))) continue;
                for (int sy = 0; sy < scale; ++sy) {
                    uint16_t *line = s_band + (size_t)(row * scale + sy) * LCD_H_RES;
                    for (int sx = 0; sx < scale; ++sx) {
                        int px = gx + sx;
                        if (px < LCD_H_RES) line[px] = w;
                    }
                }
            }
        }
        x0 += KGN_FONT_CELL_W * scale;
    }
}

/* Draw one full-width text line with a solid background. rows = 8*scale. */
static void draw_text_line(int x0, int y, int scale, uint16_t fg, uint16_t bg,
                           const char *s)
{
    if (!s_panel_ok) return;
    if (scale < 1) scale = 1;
    if (scale > 4) scale = 4;
    int rows = KGN_FONT_CELL_H * scale;
    if (y < 0 || y >= LCD_V_RES) return;
    if (y + rows > LCD_V_RES) rows = LCD_V_RES - y;
    band_fill(bg, rows);
    band_text(x0, scale, fg, s);
    lcd_blit(0, y, LCD_H_RES, rows, s_band);
}

static void draw_rect_fill(int y, int h, uint16_t colour)
{
    if (!s_panel_ok) return;
    while (h > 0) {
        int rows = h > BAND_ROWS ? BAND_ROWS : h;
        band_fill(colour, rows);
        lcd_blit(0, y, LCD_H_RES, rows, s_band);
        y += rows;
        h -= rows;
    }
}

/* ---- ILI9341 bring-up ---- */

/* {cmd, nargs, args...}, nargs 0x80 in the length slot means "then delay 120 ms".
 * Values are the vendor-recommended sequence for a 2.8" ILI9341 module; they are
 * power/gamma trims, not geometry, so they are not board specific. */
static const uint8_t s_ili_init[] = {
    0xCF, 3, 0x00, 0xC1, 0x30,
    0xED, 4, 0x64, 0x03, 0x12, 0x81,
    0xE8, 3, 0x85, 0x00, 0x78,
    0xCB, 5, 0x39, 0x2C, 0x00, 0x34, 0x02,
    0xF7, 1, 0x20,
    0xEA, 2, 0x00, 0x00,
    0xC0, 1, 0x23,              /* PWCTR1  Vreg1out */
    0xC1, 1, 0x10,              /* PWCTR2  VGH/VGL  */
    0xC5, 2, 0x3E, 0x28,        /* VMCTR1  VCOM     */
    0xC7, 1, 0x86,              /* VMCTR2           */
    /*
     * MADCTL 0x68 = MV | MX | BGR: MV swaps the row/column scan so the panel's
     * native 240x320 portrait becomes 320x240 landscape, MX flips X so the
     * origin lands top-left for the ribbon orientation on these modules, and BGR
     * matches the panel's subpixel order (without it red and blue swap).
     * If the image comes up mirrored or upside down on the real module, this
     * single byte is the thing to change: try 0x28, 0xA8 or 0xE8.
     */
    ILI_MADCTL, 1, 0x68,
    ILI_PIXFMT, 1, 0x55,        /* 16 bit/pixel RGB565 */
    0xB1, 2, 0x00, 0x18,        /* FRMCTR1 ~79 Hz */
    0xB6, 3, 0x08, 0x82, 0x27,  /* DFUNCTR */
    0xF2, 1, 0x00,              /* disable 3-gamma */
    0x26, 1, 0x01,              /* gamma curve 1 */
    0xE0, 15, 0x0F,0x31,0x2B,0x0C,0x0E,0x08,0x4E,0xF1,
              0x37,0x07,0x10,0x03,0x0E,0x09,0x00,
    0xE1, 15, 0x00,0x0E,0x14,0x03,0x11,0x07,0x31,0xC1,
              0x48,0x08,0x0F,0x0C,0x31,0x36,0x0F,
    ILI_SLPOUT, 0x80,
    ILI_DISPON, 0x80,
    0x00,                        /* terminator */
};

/*
 * THERE IS NO FIRMWARE-CONTROLLABLE PANEL RESET ON THIS BOARD.
 *
 * The LCD connector's reset is J4 pad 11, which sits on the board-wide `RESET`
 * net — shared with SW1 pad 2, C25, and the STM32F722's NRST. No ESP32 GPIO
 * drives that net, so the panel is reset by power-on and by pressing SW1, and by
 * nothing this code can do. Pressing SW1 therefore resets the LCD and the STM32
 * together, and also resets us, so the sequence is never observed from here.
 *
 * An earlier revision pulsed GPIO46 here and called it the panel reset. GPIO46
 * (net PMDN) goes to camera FPC1 pad 8 and nowhere near J4 — it is the OV2640's
 * PWDN. Driving it was not merely a no-op for the display: PWDN is active high,
 * so leaving it HIGH held the camera in power-down and the sensor could never
 * answer SCCB. GPIO46 now belongs to camera_dvp.c alone, as CONFIG_KGN_CAM_PWDN.
 *
 * What is still needed here: the ILI9341 wants ~120 ms after its reset is
 * released before it will accept commands. Since the release happened at
 * power-on, the delay is just a settle before the SWRESET in lcd_init(), and it
 * is kept. A panel that is somehow still in reset is indistinguishable from a
 * working one anyway — this board routes no MISO, so nothing can be read back.
 */
static void lcd_prepare(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << CONFIG_KGN_LCD_BL),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&io);

    /* Backlight off during init so a garbage first frame is never visible. */
#if CONFIG_KGN_LCD_BL_ACTIVE_LOW
    gpio_set_level(CONFIG_KGN_LCD_BL, 1);
#else
    gpio_set_level(CONFIG_KGN_LCD_BL, 0);
#endif

    vTaskDelay(pdMS_TO_TICKS(120));   /* ILI9341 needs 120 ms after reset release */
}

static void lcd_backlight_on(void)
{
#if CONFIG_KGN_LCD_BL_ACTIVE_LOW
    gpio_set_level(CONFIG_KGN_LCD_BL, 0);
#else
    gpio_set_level(CONFIG_KGN_LCD_BL, 1);
#endif
}

static esp_err_t lcd_init(void)
{
    s_band = heap_caps_malloc(BAND_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_8BIT);
    if (!s_band) return ESP_ERR_NO_MEM;

    spi_bus_config_t bus = {
        .mosi_io_num = CONFIG_KGN_LCD_MOSI,
        .miso_io_num = -1,                 /* no MISO net on this PCB */
        .sclk_io_num = CONFIG_KGN_LCD_SCK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = BAND_BYTES,
    };
    /* On any failure below, give the band buffer back: 20 KB of internal RAM is
     * worth more to the rest of the system than to a display that is now off. */
    esp_err_t err = spi_bus_initialize(LCD_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) { free(s_band); s_band = NULL; return err; }

    esp_lcd_panel_io_spi_config_t io = {
        .cs_gpio_num = CONFIG_KGN_LCD_CS,
        .dc_gpio_num = CONFIG_KGN_LCD_DC,
        .spi_mode = 0,
        .pclk_hz = CONFIG_KGN_LCD_SPI_HZ,
        .trans_queue_depth = 2,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_HOST, &io, &s_io);
    if (err != ESP_OK) {
        spi_bus_free(LCD_HOST);
        free(s_band);
        s_band = NULL;
        return err;
    }

    lcd_prepare();
    s_panel_ok = true;               /* blits are permitted from here on */

    lcd_cmd(ILI_SWRESET, NULL, 0);
    vTaskDelay(pdMS_TO_TICKS(150));

    for (const uint8_t *p = s_ili_init; *p;) {
        uint8_t cmd = *p++;
        uint8_t n = *p++;
        if (n & 0x80) { lcd_cmd(cmd, NULL, 0); vTaskDelay(pdMS_TO_TICKS(120)); }
        else          { lcd_cmd(cmd, p, n); p += n; }
    }
    return ESP_OK;
}

/* ---- status screen ---- */

#define ROW_Y_IP    56
#define ROW_Y_RSSI  78
#define ROW_Y_UP    100
#define ROW_Y_MODE  122
#define ROW_Y_SCRN  144
#define ROW_Y_TX    166
#define ROW_SCALE   2

static void draw_status_chrome(void)
{
    draw_rect_fill(0, LCD_V_RES, C_BG);
    /* Title at scale 4: 6 chars * 6 px cell * 4 = 144 px wide, centred. */
    draw_text_line((LCD_H_RES - 6 * KGN_FONT_CELL_W * 4) / 2, 8, 4,
                   C_AMBER, C_BG, "KOGANE");
    draw_rect_fill(46, 2, C_AMBER);
    draw_text_line(4, 200, 1, C_GREY, C_BG,
                   "kgn v1  udp 5005  ili9341 320x240  companion esp32-s3");
}

static void draw_status_values(void)
{
    char line[48];
    char ip[16];

    bool up = wifi_udp_get_ip_str(ip, sizeof(ip));
    snprintf(line, sizeof(line), "IP   %s", up ? ip : "---.---.---.---");
    draw_text_line(4, ROW_Y_IP, ROW_SCALE, up ? C_WHITE : C_RED, C_BG, line);

    int rssi;
    if (wifi_udp_get_rssi(&rssi))
        snprintf(line, sizeof(line), "RSSI %d dBm  Q %u", rssi,
                 (unsigned)kgn_rssi_to_link_q(rssi));
    else
        snprintf(line, sizeof(line), "RSSI --  no assoc");
    draw_text_line(4, ROW_Y_RSSI, ROW_SCALE, C_CYAN, C_BG, line);

    uint32_t s = (uint32_t)(esp_timer_get_time() / 1000000);
    snprintf(line, sizeof(line), "UP   %lu:%02lu:%02lu",
             (unsigned long)(s / 3600), (unsigned long)((s / 60) % 60),
             (unsigned long)(s % 60));
    draw_text_line(4, ROW_Y_UP, ROW_SCALE, C_WHITE, C_BG, line);

    snprintf(line, sizeof(line), "MODE %s", telemetry_mode_name(telemetry_get_mode()));
    draw_text_line(4, ROW_Y_MODE, ROW_SCALE, C_GREEN, C_BG, line);

    snprintf(line, sizeof(line), "SCRN %s %d deg",
             servo_screen_is_deployed() ? "DEPLOYED" : "RETRACTED",
             servo_target_deg());
    draw_text_line(4, ROW_Y_SCRN, ROW_SCALE, C_WHITE, C_BG, line);

    snprintf(line, sizeof(line), "TX   %lu frames",
             (unsigned long)telemetry_tx_count());
    draw_text_line(4, ROW_Y_TX, ROW_SCALE, C_GREY, C_BG, line);
}

/* ---- SCREEN_FRAME (0x30) ingest ---- */

/* MTU 1500 - IP/UDP 28 - KGN header 14 - crc 2 leaves 1456 usable payload bytes;
 * round down to a value that can never overrun the band buffer either. */
#define DISP_CHUNK_MAX  1456
#define DISP_Q_DEPTH    4
/* Hand the panel back to the local status screen if the base stops streaming. */
#define DISP_REMOTE_TIMEOUT_MS 5000

typedef struct { uint16_t len; uint8_t data[]; } disp_chunk_t;

static QueueHandle_t s_q;
static uint32_t s_dropped;
static bool     s_remote;           /* base owns the panel */
static uint32_t s_remote_last_ms;

bool display_submit_screen_frame(const uint8_t *payload, uint16_t len)
{
    if (!s_q || !payload) return false;
    if (len < sizeof(kgn_screen_hdr_t) || len > DISP_CHUNK_MAX) { s_dropped++; return false; }

    /* Copy: the caller's buffer is the UDP rx buffer and is reused immediately.
     * malloc on the rx path is not free, but the alternative (a static pool) buys
     * little at a chunk rate the panel can actually keep up with, and the queue
     * depth bounds how many can be outstanding. */
    disp_chunk_t *c = malloc(sizeof(*c) + len);
    if (!c) { s_dropped++; return false; }
    c->len = len;
    memcpy(c->data, payload, len);

    /* Zero timeout: this runs on kgn_udp and must never block the rx loop. */
    if (xQueueSend(s_q, &c, 0) != pdPASS) { free(c); s_dropped++; return false; }
    return true;
}

static void handle_rgb565(const uint8_t *body, uint16_t body_len)
{
    if (body_len < sizeof(kgn_screen_tile_t)) { s_dropped++; return; }
    kgn_screen_tile_t t;
    memcpy(&t, body, sizeof(t));            /* unaligned in the rx copy */
    const uint8_t *px = body + sizeof(t);
    uint32_t want = (uint32_t)t.w * t.h;

    if (!t.w || !t.h || t.x + t.w > LCD_H_RES || t.y + t.h > LCD_V_RES ||
        want > BAND_PIXELS || body_len - sizeof(t) < want * 2) {
        s_dropped++;
        return;
    }
    /* Payload is RGB565 little-endian (PROTOCOL.md); the panel wants big-endian,
     * so swap on the way into the band buffer. This also fixes the alignment: px
     * may be odd-addressed inside the chunk copy. */
    for (uint32_t i = 0; i < want; ++i)
        s_band[i] = (uint16_t)(px[i * 2] << 8 | px[i * 2 + 1]);
    lcd_blit(t.x, t.y, t.w, t.h, s_band);
}

static void handle_text(const uint8_t *body, uint16_t body_len)
{
    if (body_len < sizeof(kgn_screen_text_t)) { s_dropped++; return; }
    kgn_screen_text_t th;
    memcpy(&th, body, sizeof(th));
    if (th.row >= KGN_SF_TEXT_ROWS) { s_dropped++; return; }

    int scale = th.scale;
    if (scale < 1) scale = 1;
    /* A text row is KGN_SF_TEXT_ROW_PX (24) tall, so scale 3 is the largest that
     * fits inside one row without spilling into the next. */
    if (scale > KGN_SF_TEXT_ROW_PX / KGN_FONT_CELL_H) scale = KGN_SF_TEXT_ROW_PX / KGN_FONT_CELL_H;

    uint16_t n = body_len - sizeof(th);
    if (n > KGN_SF_TEXT_MAX) n = KGN_SF_TEXT_MAX;
    char text[KGN_SF_TEXT_MAX + 1];
    memcpy(text, body + sizeof(th), n);
    text[n] = '\0';

    draw_text_line(0, th.row * KGN_SF_TEXT_ROW_PX, scale, th.fg, th.bg, text);
}

static void handle_chunk(const disp_chunk_t *c)
{
    kgn_screen_hdr_t h;
    memcpy(&h, c->data, sizeof(h));
    const uint8_t *body = c->data + sizeof(h);
    uint16_t body_len = c->len - sizeof(h);

    if (h.flags & KGN_SF_F_STATUS) {
        s_remote = false;
        draw_status_chrome();
        return;
    }
    s_remote = true;
    s_remote_last_ms = (uint32_t)(esp_timer_get_time() / 1000);
    if (h.flags & KGN_SF_F_FIRST) draw_rect_fill(0, LCD_V_RES, 0x0000);

    switch (h.fmt) {
    case KGN_SF_FMT_RGB565: handle_rgb565(body, body_len); break;
    case KGN_SF_FMT_TEXT:   handle_text(body, body_len);   break;
    default: s_dropped++; break;
    }
}

/* ---- task ---- */

static void display_task(void *arg)
{
    esp_err_t err = lcd_init();
    if (err != ESP_OK) {
        /* Logged exactly once. Everything else in the system keeps running. */
        ESP_LOGE(TAG, "ILI9341 init failed (%s) — display disabled, "
                      "wifi/udp/telemetry unaffected", esp_err_to_name(err));
        s_panel_ok = false;
        /* Still drain the queue: otherwise SCREEN_FRAME chunks leak on a board
         * with no panel attached. */
        while (1) {
            disp_chunk_t *c;
            if (xQueueReceive(s_q, &c, portMAX_DELAY) == pdPASS) free(c);
        }
    }

    draw_status_chrome();
    draw_status_values();
    lcd_backlight_on();
    /* No RST in this log line on purpose: the panel reset is not ours to drive.
     * See lcd_prepare(). */
    ESP_LOGI(TAG, "ILI9341 up: %dx%d, %d MHz, CS=%d SCK=%d MOSI=%d DC=%d BL=%d "
                  "RST=board (shared RESET net, not a GPIO)",
             LCD_H_RES, LCD_V_RES, CONFIG_KGN_LCD_SPI_HZ / 1000000,
             CONFIG_KGN_LCD_CS, CONFIG_KGN_LCD_SCK, CONFIG_KGN_LCD_MOSI,
             CONFIG_KGN_LCD_DC, CONFIG_KGN_LCD_BL);

    uint32_t last_drop_log = 0;
    while (1) {
        /* Poll faster while the base owns the panel so the timeout is responsive. */
        TickType_t wait = pdMS_TO_TICKS(s_remote ? 250 : CONFIG_KGN_LCD_STATUS_MS);
        disp_chunk_t *c;
        if (xQueueReceive(s_q, &c, wait) == pdPASS) {
            handle_chunk(c);
            free(c);
            continue;
        }

        uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
        if (s_remote) {
            if ((uint32_t)(now - s_remote_last_ms) > DISP_REMOTE_TIMEOUT_MS) {
                ESP_LOGI(TAG, "SCREEN_FRAME stream idle, back to status screen");
                s_remote = false;
                draw_status_chrome();
            } else {
                continue;
            }
        }
        draw_status_values();

        if (s_dropped && (uint32_t)(now - last_drop_log) > 5000) {
            last_drop_log = now;
            ESP_LOGW(TAG, "%lu screen chunks dropped (malformed / queue full)",
                     (unsigned long)s_dropped);
            s_dropped = 0;
        }
    }
}

void display_spi_start(void)
{
    s_q = xQueueCreate(DISP_Q_DEPTH, sizeof(disp_chunk_t *));
    if (!s_q) {
        ESP_LOGE(TAG, "queue alloc failed — display disabled");
        return;
    }
    /* Priority 3: the lowest of the Kogane tasks. The panel is a readout; it must
     * never win the CPU against kgn_udp (6), telemetry (5) or the servo (4).
     * Stack 4096: snprintf with %d/%s plus the init path, no recursion. */
    if (xTaskCreate(display_task, "kgn_disp", 4096, NULL, 3, NULL) != pdPASS) {
        ESP_LOGE(TAG, "xTaskCreate(kgn_disp) failed — display disabled");
        vQueueDelete(s_q);
        s_q = NULL;
    }
}
