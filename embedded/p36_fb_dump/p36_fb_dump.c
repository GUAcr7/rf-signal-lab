/* Read-only framebuffer snapshot. No RF, PL, overlay or console operations. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define PANEL_W 800u
#define PANEL_H 480u
#define RAW_BYTES (PANEL_W * PANEL_H * 4u)

/* Same geometry contract as the corrected P35 panel; tests reuse its cases. */
static int framebuffer_geometry(const struct fb_fix_screeninfo *fix,
        const struct fb_var_screeninfo *var, size_t *start, size_t *length)
{
    uint16_t endian = 1;
    if (*(const unsigned char *)&endian != 1 || fix->type != FB_TYPE_PACKED_PIXELS ||
        fix->visual != FB_VISUAL_TRUECOLOR || var->xres != PANEL_W ||
        var->yres != PANEL_H || var->bits_per_pixel != 32 || var->grayscale ||
        var->nonstd || var->rotate || var->vmode ||
        var->red.offset != 16 || var->red.length != 8 || var->red.msb_right ||
        var->green.offset != 8 || var->green.length != 8 || var->green.msb_right ||
        var->blue.offset || var->blue.length != 8 || var->blue.msb_right ||
        (var->transp.length && (var->transp.length != 8 || var->transp.offset != 24 || var->transp.msb_right)) ||
        !fix->line_length || (fix->line_length % 4) ||
        (uint64_t)var->xoffset + PANEL_W > var->xres_virtual ||
        (uint64_t)var->yoffset + PANEL_H > var->yres_virtual ||
        ((uint64_t)var->xoffset + PANEL_W) * 4 > fix->line_length)
        return -1;
    uint64_t first = (uint64_t)var->yoffset * fix->line_length + (uint64_t)var->xoffset * 4;
    uint64_t end = first + (PANEL_H - 1u) * (uint64_t)fix->line_length + PANEL_W * 4u;
    if (end > fix->smem_len || end > SIZE_MAX || first > SIZE_MAX)
        return -1;
    *start = (size_t)first;
    *length = (size_t)end;
    return 0;
}

/* Only one existing, nonsymlink RAM directory and the new basename fb.raw. */
static int valid_output(const char *path)
{
    if (!path || strlen(path) >= 128 || strncmp(path, "/tmp/p35-", 9))
        return 0;
    const char *slash = strchr(path + 9, '/');
    if (!slash || slash == path + 9 || strcmp(slash, "/fb.raw"))
        return 0;
    for (const char *p = path + 9; p < slash; p++) {
        unsigned char c = (unsigned char)*p;
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-'))
            return 0;
    }
    return 1;
}

static int write_all(int fd, const unsigned char *data, size_t bytes)
{
    while (bytes) {
        ssize_t n = write(fd, data, bytes);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            return -1;
        data += (size_t)n;
        bytes -= (size_t)n;
    }
    return 0;
}

static void bitfield(const char *name, const struct fb_bitfield *field)
{
    printf("\"%s\":{\"offset\":%u,\"length\":%u,\"msb_right\":%u}",
           name, field->offset, field->length, field->msb_right);
}

int main(int argc, char **argv)
{
    if (argc != 2 || !valid_output(argv[1])) {
        fprintf(stderr, "usage: p36-fb-dump /tmp/p35-<safe-directory>/fb.raw (must not exist)\n");
        return 2;
    }
    int result = 3, framebuffer = -1, directory = -1, output = -1;
    void *map = MAP_FAILED;
    size_t start = 0, length = 0;
    struct fb_fix_screeninfo fix = {0}, final_fix = {0};
    struct fb_var_screeninfo var = {0}, final_var = {0};
    char parent[128];
    const char *slash = strrchr(argv[1], '/');
    size_t parent_length = (size_t)(slash - argv[1]);
    memcpy(parent, argv[1], parent_length);
    parent[parent_length] = '\0';

    framebuffer = open("/dev/fb0", O_RDONLY | O_CLOEXEC);
    if (framebuffer < 0) { perror("open framebuffer read-only"); goto done; }
    if (ioctl(framebuffer, FBIOGET_FSCREENINFO, &fix) ||
        ioctl(framebuffer, FBIOGET_VSCREENINFO, &var)) {
        perror("framebuffer read-only ioctl"); goto done;
    }
    if (framebuffer_geometry(&fix, &var, &start, &length)) {
        fprintf(stderr, "unsupported framebuffer geometry/format/extent\n"); goto done;
    }
    map = mmap(NULL, length, PROT_READ, MAP_SHARED, framebuffer, 0);
    if (map == MAP_FAILED) { perror("mmap framebuffer read-only"); goto done; }
    directory = open(parent, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (directory < 0) { perror("open RAM output directory without symlink"); goto done; }
    output = openat(directory, "fb.raw", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (output < 0) { perror("create new fb.raw without overwriting"); goto done; }
    for (size_t y = 0; y < PANEL_H; y++) {
        const unsigned char *row = (const unsigned char *)map + start + y * fix.line_length;
        if (write_all(output, row, PANEL_W * 4u)) {
            perror("write snapshot row; partial output preserved"); goto done;
        }
    }
    if (fsync(output)) { perror("sync output; output preserved"); goto done; }
    if (close(output)) { output = -1; perror("close output"); goto done; }
    output = -1;
    if (ioctl(framebuffer, FBIOGET_FSCREENINFO, &final_fix) ||
        ioctl(framebuffer, FBIOGET_VSCREENINFO, &final_var)) {
        perror("final framebuffer ioctl; output preserved"); goto done;
    }
    /* A changed pan/mode invalidates a single-layout interpretation. Even an
     * unchanged mode does not prove atomic pixels while another app draws. */
    if (memcmp(&fix, &final_fix, sizeof fix) || memcmp(&var, &final_var, sizeof var)) {
        fprintf(stderr, "framebuffer geometry changed during snapshot; output unaccepted\n");
        goto done;
    }
    printf("{\"schema\":\"rfsig.p36_fb_snapshot.v1\",\"status\":\"visible_bytes_saved\","
           "\"output\":\"%s\",\"bytes\":%u,\"visible\":[%u,%u],\"virtual\":[%u,%u],"
           "\"bpp\":%u,\"stride_bytes\":%u,\"xoffset\":%u,\"yoffset\":%u,"
           "\"smem_len\":%u,\"mapped_bytes\":%zu,\"visible_start_bytes\":%zu,"
           "\"output_stride_bytes\":%u,\"storage\":\"little_endian_BGRA_or_BGRX\",",
           argv[1], RAW_BYTES, var.xres, var.yres, var.xres_virtual, var.yres_virtual,
           var.bits_per_pixel, fix.line_length, var.xoffset, var.yoffset,
           fix.smem_len, length, start, PANEL_W * 4u);
    bitfield("red", &var.red); printf(",");
    bitfield("green", &var.green); printf(",");
    bitfield("blue", &var.blue); printf(",");
    bitfield("transparency", &var.transp);
    printf(",\"geometry_unchanged\":true,\"framebuffer_opened_read_only\":true,"
           "\"framebuffer_written\":false,\"atomic_snapshot\":false,"
           "\"scanout_or_physical_display_verified\":false}\n");
    result = 0;
done:
    if (output >= 0) close(output);
    if (directory >= 0) close(directory);
    if (map != MAP_FAILED) munmap(map, length);
    if (framebuffer >= 0) close(framebuffer);
    return result;
}
