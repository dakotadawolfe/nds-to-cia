#pragma once
#include <dirent.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include "layout.h"

typedef struct __attribute__((packed)) { char magic[8]; uint64_t title; } DsRequest;
typedef int (*DsRequestVisitor)(const char *base, uint64_t title, void *context);

static int ds_hex_name(const char *name, unsigned length) {
    if (strlen(name) != length) return 0;
    for (unsigned i = 0; i < length; i++)
        if (!((name[i] >= '0' && name[i] <= '9') || (name[i] >= 'a' && name[i] <= 'f') ||
              (name[i] >= 'A' && name[i] <= 'F'))) return 0;
    return 1;
}

/* Only fixed-depth title directories and our exact request record are considered. */
static int ds_visit_titles(const char *path, unsigned depth, DsRequestVisitor visit, void *context) {
    DIR *dir = opendir(path);
    if (!dir) return 0;
    int result = 1;
    struct dirent *entry;
    unsigned seen = 0;
    while (result && (entry = readdir(dir))) {
        if (++seen > 16384) { result = 0; break; }
        if (!ds_hex_name(entry->d_name, depth < 2 ? 32 : 8)) continue;
        char child[256];
        int n = snprintf(child, sizeof(child), "%s/%s%s", path, entry->d_name,
                         depth == 1 ? "/title/00040000" : depth == 2 ? DS_DATA_SUFFIX : "");
        if (n < 0 || n >= (int)sizeof(child)) { result = 0; break; }
        struct stat st;
        if (stat(child, &st) || !S_ISDIR(st.st_mode)) continue;
        if (depth < 2) result = ds_visit_titles(child, depth+1, visit, context);
        else {
            char request_path[288];
            snprintf(request_path, sizeof(request_path), "%s/" DS_REQUEST_FILE, child);
            FILE *file = fopen(request_path, "rb");
            if (!file) continue;
            DsRequest request;
            int valid = fread(&request, sizeof(request), 1, file) == 1 && fgetc(file) == EOF && !ferror(file);
            fclose(file);
            unsigned low = 0;
            if (valid && !memcmp(request.magic, "DCSREQ02", 8) && sscanf(entry->d_name, "%x", &low) == 1 &&
                request.title == (0x0004000000000000ULL | low)) result = visit(child, request.title, context);
        }
    }
    if (closedir(dir)) result = 0;
    return result;
}
