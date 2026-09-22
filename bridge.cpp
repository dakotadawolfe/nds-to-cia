/* Based on YANBF's GPL-2.0-or-later DS launch component. */
#include <nds.h>
#include <fat.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdarg.h>
#include "nds_loader_arm9.h"
#include "requests.h"

static unsigned requests;
static char selected[256];
static void log_stage(const char *base, const char *format, ...) {
    char path[288];
    snprintf(path, sizeof(path), "%s/" DS_LOG_FILE, base);
    FILE *file = fopen(path, "a");
    if (!file) return;
    va_list args;
    va_start(args, format);
    vfprintf(file, format, args);
    va_end(args);
    fclose(file);
}
static int select_request(const char *base, uint64_t title, void *context) {
    (void)title; (void)context;
    requests++;
    snprintf(selected, sizeof(selected), "%s", base);
    log_stage(base, "Bridge 1.0.0: request found, DSi mode=%d\n", isDSiMode());
    return 1;
}
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    videoSetMode(0); videoSetModeSub(0);
    bool mounted = false;
    for (unsigned attempt = 0; attempt < 5 && !mounted; attempt++) {
        mounted = fatInitDefault();
        if (!mounted) swiWaitForVBlank();
    }
    int scanned = mounted && ds_visit_titles("sd:/Nintendo 3DS", 0, select_request, NULL);
    if (selected[0]) log_stage(selected, "Bridge scan=%d requests=%u\n", scanned, requests);
    if (scanned && requests == 1) {
        char game[288], runtime[288], request[288];
        snprintf(game, sizeof(game), "%s/" DS_GAME_FILE, selected);
        snprintf(runtime, sizeof(runtime), "%s/" DS_FORWARDER_FILE, selected);
        snprintf(request, sizeof(request), "%s/" DS_REQUEST_FILE, selected);
        if (remove(request) == 0) {
            const char *args[] = {runtime, game};
            log_stage(selected, "Bridge: request consumed, starting forwarder\n");
            int result = runNdsFile(runtime, 2, args);
            log_stage(selected, "Bridge: forwarder returned=%d errno=%d\n", result, errno);
        } else {
            log_stage(selected, "Bridge: request removal failed errno=%d\n", errno);
        }
    }
    fifoSendValue32(FIFO_USER_01, 1);
    while (1) swiWaitForVBlank();
}
