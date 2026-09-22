#include "runtime_paths.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

static char root[192];
static struct { const char *device, *suffix; char *path; } paths[192];
static unsigned count;

void ds_log_stage(const char *format, ...) {
    if (!root[0]) return;
    char path[256];
    snprintf(path, sizeof(path), "sd:%s/00000006.bin", root);
    FILE *file = fopen(path, "a");
    if (!file) return;
    va_list args;
    va_start(args, format);
    vfprintf(file, format, args);
    va_end(args);
    fclose(file);
}

int ds_storage_init(const char *executable) {
    if (!executable || count) return 0;
    const char *start = strchr(executable, ':');
    start = start ? start + 1 : executable;
    const char *last = strrchr(start, '/');
    if (!last || last - start >= (int)sizeof(root) || strstr(start, "..") ||
        strncmp(start, "/Nintendo 3DS/", 14)) return 0;
    size_t length = last - start;
    const char ending[] = "/data/00000000";
    if (length < sizeof(ending)-1 || memcmp(last-(sizeof(ending)-1), ending, sizeof(ending)-1)) return 0;
    memcpy(root, start, length);
    root[length] = 0;
    return 1;
}

const char *ds_path(const char *device, const char *suffix) {
    if (!root[0]) abort();
    for (unsigned i = 0; i < count; i++)
        if (!strcmp(paths[i].device, device) && !strcmp(paths[i].suffix, suffix)) return paths[i].path;
    if (count == sizeof(paths)/sizeof(paths[0])) abort();
    size_t size = strlen(device) + strlen(root) + strlen(suffix) + 1;
    if (size > 512) abort();
    char *path = (char*)malloc(size);
    if (!path) abort();
    snprintf(path, size, "%s%s%s", device, root, suffix);
    paths[count].device = device;
    paths[count].suffix = suffix;
    paths[count++].path = path;
    return path;
}
