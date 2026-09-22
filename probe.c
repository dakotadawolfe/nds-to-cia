#include <nds.h>
#include <fat.h>
#include <stdio.h>
#include <sys/stat.h>
#include <string.h>
#include "layout.h"

int main(int argc, char **argv) {
    consoleDemoInit();
    iprintf("DS Clean SD - storage probe\n\nDS mode is running.\n");
    if (!fatInitDefault()) {
        iprintf("SD mount failed.\n");
    } else {
        char path[288];
        if (argc < 1 || strlen(argv[0]) >= sizeof(path)) return 1;
        strcpy(path, argv[0]);
        char *last = strrchr(path, '/');
        if (!last) return 1;
        strcpy(last+1, DS_PROBE_FILE);
        unsigned count = 0;
        FILE *file = fopen(path, "r");
        if (file) { fscanf(file, "%u", &count); fclose(file); }
        iprintf("Previous launches: %u\n", count);
        file = fopen(path, "w");
        if (file) {
            bool okay = fprintf(file, "%u\n", count+1) > 0;
            if (fclose(file)) okay = false;
            iprintf(okay ? "Storage write succeeded.\n" : "Storage write failed.\n");
        } else iprintf("Cannot create test save.\n");
        struct stat st;
        iprintf("Root _nds folder: %s\n", stat("sd:/_nds", &st) == 0 ? "already present" : "absent");
    }
    iprintf("\nRelaunch to check persistence.\nUse HOME to return.\n");
    while (1) swiWaitForVBlank();
}
