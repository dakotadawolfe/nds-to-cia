#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <sys/stat.h>

/* Prepared cards carry trusted package contents. Detect missing/truncated files
   without reading the full game again on every launch. */
static bool ds_has_expected_size(const char *path, uint64_t size) {
    struct stat st;
    return !stat(path, &st) && S_ISREG(st.st_mode) && st.st_size >= 0 &&
           (uint64_t)st.st_size == size;
}
