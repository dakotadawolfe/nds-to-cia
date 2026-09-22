/* DS Clean SD launcher. Runtime files belong only to this application's directory. */
#include <3ds.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
#include "layout.h"
#include "requests.h"
#include "silent.h"
#include "workfiles.h"

static char base[256];
#define BRIDGE_ID DS_BRIDGE_ID
#define COPY_SIZE (64 * 1024)
#define MAX_FILES 16

typedef struct __attribute__((packed)) {
    char magic[8];
    char game[64];
    uint32_t count;
} Package;
typedef struct __attribute__((packed)) {
    char name[128];
    uint64_t size;
    uint32_t crc;
    uint32_t flags;
} Entry;
static unsigned char buffer[COPY_SIZE];
static FILE *logfile;

static uint32_t crc_step(uint32_t crc, const void *data, size_t size) {
    static uint32_t table[256];
    static bool ready;
    if (!ready) {
        for (unsigned i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int b = 0; b < 8; b++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1)));
            table[i] = c;
        }
        ready = true;
    }
    const unsigned char *p = data;
    while (size--) crc = table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return crc;
}
static bool safe_name(const char *name, size_t capacity) {
    if (!memchr(name, 0, capacity) || !name[0] || name[0] == '/' || strstr(name, "..")) return false;
    for (const char *p = name; *p; p++) {
        if (!( (*p >= 'a' && *p <= 'z') || (*p >= '0' && *p <= '9') ||
               *p == '/' || *p == '.' || *p == '-' || *p == '_' )) return false;
    }
    return true;
}
static bool parents(const char *path) {
    char copy[512];
    if (strlen(path) >= sizeof(copy)) return false;
    strcpy(copy, path);
    for (char *p = copy + 6; *p; p++) {
        if (*p != '/') continue;
        *p = 0;
        int rc = mkdir(copy, 0777);
        *p = '/';
        if (rc && errno != EEXIST) return false;
    }
    return true;
}
static bool matches(const char *path, const Entry *entry) {
    struct stat st;
    if (stat(path, &st) || (uint64_t)st.st_size != entry->size) return false;
    FILE *file = fopen(path, "rb");
    if (!file) return false;
    uint32_t crc = ~0u;
    size_t n;
    while ((n = fread(buffer, 1, sizeof(buffer), file))) crc = crc_step(crc, buffer, n);
    bool okay = !ferror(file) && (crc ^ ~0u) == entry->crc;
    if (fclose(file)) okay = false;
    return okay;
}
static bool extract_entry(unsigned index, const Entry *entry) {
    char source[64], target[512], temporary[528];
    snprintf(source, sizeof(source), "romfs:/files/%02u.bin", index);
    snprintf(target, sizeof(target), "%s/%s", base, entry->name);
    snprintf(temporary, sizeof(temporary), "%s.part", target);
    if (entry->flags & 1) {
        struct stat st;
        if (!stat(target, &st)) return true; /* Mutable settings are never replaced. */
    } else if (matches(target, entry)) return true;
    if (!parents(target)) return false;
    FILE *input = fopen(source, "rb");
    if (!input) return false;
    FILE *output = fopen(temporary, "wb");
    if (!output) { fclose(input); return false; }
    uint64_t written = 0;
    uint32_t crc = ~0u;
    size_t n;
    bool okay = true;
    ds_silent_printf("Installing %s\n", entry->name);
    while ((n = fread(buffer, 1, sizeof(buffer), input))) {
        if (written + n > entry->size || fwrite(buffer, 1, n, output) != n) { okay = false; break; }
        crc = crc_step(crc, buffer, n);
        written += n;
    }
    okay = okay && !ferror(input) && written == entry->size && (crc ^ ~0u) == entry->crc;
    if (fclose(input)) okay = false;
    if (fclose(output)) okay = false;
    if (okay) okay = matches(temporary, entry);
    if (okay) {
        /* Replacement starts only after the staged file has passed readback. */
        if (remove(target) && errno != ENOENT) okay = false;
        if (okay && rename(temporary, target)) okay = false;
    }
    if (!okay) remove(temporary);
    if (logfile) { fprintf(logfile, "%s: %s\n", entry->name, okay ? "verified" : "failed"); fflush(logfile); }
    return okay;
}
static Result require_bridge(void) {
    AM_TitleEntry installed;
    u64 tid = BRIDGE_ID;
    return AM_GetTitleInfo(MEDIATYPE_NAND, 1, &tid, &installed);
}
static bool prepare_workfiles(void) {
    const char *names[] = {DS_RAM_DUMP_PATH, DS_OVERLAY_PATH};
    const uint32_t sizes[] = {DS_RAM_DUMP_SIZE, DS_OVERLAY_SIZE};
    for (unsigned i = 0; i < 2; i++) {
        char path[512];
        snprintf(path, sizeof(path), "%s/%s", base, names[i]);
        if (logfile) { fprintf(logfile, "Preparing %s: %lu bytes\n", names[i], (unsigned long)sizes[i]); fflush(logfile); }
        bool okay = parents(path) && ds_ensure_workfile(path, sizes[i], buffer, sizeof(buffer));
        if (logfile) { fprintf(logfile, "Work file: %s\n", okay ? "ready" : "failed"); fflush(logfile); }
        if (!okay) return false;
    }
    return true;
}
static int clear_request(const char *directory, uint64_t title, void *context) {
    (void)title; (void)context;
    char path[288];
    snprintf(path, sizeof(path), "%s/" DS_REQUEST_FILE, directory);
    return remove(path) == 0;
}
static bool locate_storage(u64 *title) {
    u8 raw[512] = {0};
    if (R_FAILED(APT_GetProgramID(title)) || (*title >> 32) != 0x00040000 ||
        R_FAILED(FSUSER_GetSdmcCtrRootPath(raw, sizeof(raw)))) return false;
    char root[192] = {0};
    unsigned stride = raw[1] == 0 ? 2 : 1;
    for (unsigned i = 0; i < sizeof(root)-1; i++) {
        if (stride == 2 && raw[i*2+1]) return false;
        root[i] = raw[i*stride];
        if (!root[i]) break;
    }
    size_t len = strlen(root);
    while (len && root[len-1] == '/') root[--len] = 0;
    if (len != 79 || strncmp(root, "/Nintendo 3DS/", 14) || root[46] != '/') return false;
    root[46] = 0;
    bool valid = ds_hex_name(root+14, 32) && ds_hex_name(root+47, 32);
    root[46] = '/';
    if (!valid) return false;
    snprintf(base, sizeof(base), "sdmc:%s/title/00040000/%08lx", root, (u32)*title);
    char content[288];
    snprintf(content, sizeof(content), "%s/content", base);
    struct stat st;
    if (stat(content, &st) || !S_ISDIR(st.st_mode)) return false;
    strncat(base, DS_DATA_SUFFIX, sizeof(base)-strlen(base)-1);
    return true;
}
static bool write_request(u64 title) {
    if (!ds_visit_titles("sdmc:/Nintendo 3DS", 0, clear_request, NULL)) return false;
    char target[288], temporary[288];
    snprintf(target, sizeof(target), "%s/" DS_REQUEST_FILE, base);
    snprintf(temporary, sizeof(temporary), "%s/00000007.tmp", base);
    DsRequest request;
    memcpy(request.magic, "DCSREQ02", 8);
    request.title = title;
    FILE *file = fopen(temporary, "wb");
    if (!file) return false;
    bool okay = fwrite(&request, sizeof(request), 1, file) == 1;
    if (fclose(file)) okay = false;
    return okay && rename(temporary, target) == 0;
}
static void blank_screens(void) {
    for (int frame = 0; frame < 2; frame++) {
        memset(gfxGetFramebuffer(GFX_TOP, GFX_LEFT, NULL, NULL), 0, 400*240*3);
        memset(gfxGetFramebuffer(GFX_BOTTOM, GFX_LEFT, NULL, NULL), 0, 320*240*3);
        gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
    }
}
int main(void) {
    gfxInitDefault();
    blank_screens();
    u64 title = 0;
    bool romfs_ready = false, am_ready = false;
    if (!locate_storage(&title)) { gfxExit(); return 1; }
    char logpath[288];
    snprintf(logpath, sizeof(logpath), "%s/" DS_LOG_FILE, base);
    if (!parents(logpath)) { gfxExit(); return 1; }
    logfile = fopen(logpath, "w");
    if (logfile) { fprintf(logfile, "Launcher 1.0.0 entered: %016llX\n", title); fflush(logfile); }
    Result rc = romfsInit();
    if (logfile) { fprintf(logfile, "romfsInit: %08lX\n", rc); fflush(logfile); }
    if (R_FAILED(rc)) goto done;
    romfs_ready = true;
    rc = amInit();
    if (logfile) { fprintf(logfile, "amInit: %08lX\n", rc); fflush(logfile); }
    if (R_FAILED(rc)) goto done;
    am_ready = true;
    rc = require_bridge();
    if (logfile) { fprintf(logfile, "Bridge %016llX: %08lX\n", BRIDGE_ID, rc); fflush(logfile); }
    if (R_FAILED(rc)) goto done;
    Package package;
    Entry entries[MAX_FILES];
    FILE *manifest = fopen("romfs:/package.manifest", "rb");
    bool okay = manifest && fread(&package, sizeof(package), 1, manifest) == 1;
    okay = okay && !memcmp(package.magic, "DCSDPK02", 8) && package.count > 0 && package.count <= MAX_FILES;
    okay = okay && safe_name(package.game, sizeof(package.game)) && !strcmp(package.game, DS_GAME_FILE);
    if (okay) okay = fread(entries, sizeof(Entry), package.count, manifest) == package.count && fgetc(manifest) == EOF;
    if (manifest) fclose(manifest);
    if (okay) {
        bool game_found = false, runtime_found = false;
        for (unsigned i = 0; i < package.count; i++) {
            okay = okay && safe_name(entries[i].name, sizeof(entries[i].name)) && entries[i].size <= (512ULL << 20) && !(entries[i].flags & ~1u);
            if (!okay) break;
            if (!strcmp(entries[i].name, package.game)) game_found = true;
            if (!strcmp(entries[i].name, DS_FORWARDER_FILE)) runtime_found = true;
            for (unsigned j = 0; j < i; j++) if (!strcmp(entries[i].name, entries[j].name)) okay = false;
        }
        okay = okay && game_found && runtime_found;
    }
    if (!okay) { ds_silent_printf("Invalid game package. Nothing installed.\n"); goto done; }
    ds_silent_printf("NDS to CIA 1.0\n\nChecking game and runtime files...\n");
    for (unsigned i = 0; i < package.count; i++) {
        if (!extract_entry(i, &entries[i])) { ds_silent_printf("Installation failed: %s\nCheck SD free space and install.log.\n", entries[i].name); goto done; }
    }
    if (!prepare_workfiles() || !write_request(title)) goto done;
    if (logfile) { fprintf(logfile, "Launching %s\n", package.game); fflush(logfile); }
    /* Let aptExit perform the jump after services and graphics are released.
       A direct jump here followed by normal exit also closes the application. */
    aptSetChainloader(BRIDGE_ID, MEDIATYPE_NAND);
    if (logfile) { fprintf(logfile, "DS chainload scheduled\n"); fflush(logfile); }
done:
    if (logfile) fclose(logfile);
    if (am_ready) amExit();
    if (romfs_ready) romfsExit();
    gfxExit();
    return 0;
}
