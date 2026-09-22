#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>

#define DS_RAM_DUMP_PATH "ff62061c/054778e7.bin"
#define DS_OVERLAY_PATH "ff62061c/757d8f91.bin"
#define DS_RAM_DUMP_SIZE (32u * 1024u * 1024u)
#define DS_OVERLAY_SIZE (10u * 1024u * 1024u)

/* Extend in sequential blocks before entering DS mode. Existing bytes are
   preserved, including a partial allocation left by an interrupted launch. */
static bool ds_ensure_workfile(const char *path, uint32_t minimum,
                               void *buffer, size_t capacity) {
    if (!buffer || !capacity) return false;
    struct stat st;
    uint64_t length = 0;
    if (!stat(path, &st)) {
        if (!S_ISREG(st.st_mode) || st.st_size < 0) return false;
        length = (uint64_t)st.st_size;
        if (length >= minimum) return true;
    } else if (errno != ENOENT) return false;

    FILE *file = fopen(path, "ab");
    if (!file) return false;
    memset(buffer, 0, capacity);
    bool okay = true;
    while (length < minimum) {
        size_t chunk = minimum - length;
        if (chunk > capacity) chunk = capacity;
        if (fwrite(buffer, 1, chunk, file) != chunk) { okay = false; break; }
        length += chunk;
    }
    if (fflush(file)) okay = false;
    if (fclose(file)) okay = false;
    return okay && !stat(path, &st) && S_ISREG(st.st_mode) &&
           st.st_size >= 0 && (uint64_t)st.st_size >= minimum;
}
