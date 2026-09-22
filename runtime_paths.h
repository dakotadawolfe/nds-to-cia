#pragma once
#ifdef __cplusplus
extern "C" {
#endif
int ds_storage_init(const char *executable);
const char *ds_path(const char *device, const char *suffix);
void ds_log_stage(const char *format, ...);
#ifdef __cplusplus
}
#endif
