#define main panel_program_main
#include "arm_panel.c"
#undef main
#include <assert.h>
int main(void) {
 struct fb_fix_screeninfo f={0}; struct fb_var_screeninfo v={0}; size_t start=0,len=0;
 f.type=FB_TYPE_PACKED_PIXELS; f.visual=FB_VISUAL_TRUECOLOR; f.line_length=3200; f.smem_len=3200*480;
 v.xres=800;v.yres=480;v.xres_virtual=800;v.yres_virtual=480;v.bits_per_pixel=32;
 v.red.offset=16;v.red.length=8;v.green.offset=8;v.green.length=8;v.blue.length=8;
 assert(framebuffer_geometry(&f,&v,&start,&len)==0 && start==0 && len==3200*480);
 v.transp.offset=24;v.transp.length=8;assert(framebuffer_geometry(&f,&v,&start,&len)==0);
 v.xres_virtual=804;v.yres_virtual=482;v.xoffset=2;v.yoffset=1;f.line_length=3216;f.smem_len=3216*482;
 assert(framebuffer_geometry(&f,&v,&start,&len)==0 && start==3224 && len==3224+479*3216+3200);
 uint32_t *memory=malloc(f.smem_len);assert(memory);for(size_t i=0;i<f.smem_len/4;i++)memory[i]=0x12345678;
 fb=memory+start/4;fb_stride_words=f.line_length/4;fill(0x87654321);put(-1,0,0);put(800,0,0);
 assert(memory[0]==0x12345678 && memory[start/4]==0x87654321 && memory[start/4+800]==0x12345678);
 assert(memory[start/4+479*fb_stride_words+799]==0x87654321);free(memory);
 f.smem_len=(unsigned int)len-1;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);f.smem_len=3216*482;
 v.red.offset=0;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.red.offset=16;
 f.line_length=3199;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);f.line_length=3216;
 v.xoffset=5;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.xoffset=2;
 v.yoffset=3;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.yoffset=1;
 v.bits_per_pixel=16;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.bits_per_pixel=32;
 v.red.msb_right=1;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.red.msb_right=0;
 v.vmode=FB_VMODE_YWRAP;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.vmode=0;
 puts("P35_PANEL_GEOMETRY_PASS");return 0;
}
