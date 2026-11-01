/* Test-only libiio ABI surface and deterministic word-pattern producer. */
#include "iio.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct iio_context {int dummy;};
struct iio_device {int kind;};
struct iio_channel {int index;};
struct iio_buffer {unsigned char *data;size_t size;unsigned int block;};
static struct iio_context ctx;
static struct iio_device phy={1},adc={2};
static struct iio_channel channels[4]={{0},{1},{2},{3}},lo={9};
static unsigned int enabled, destroyed;
static int fault(const char *name){const char *f=getenv("P27_MOCK_FAULT");return f && !strcmp(f,name);}
void iio_library_get_version(unsigned int *a,unsigned int *b,char tag[8]){*a=0;*b=fault("version")?21:20;memcpy(tag,"mock\0\0\0",8);}
struct iio_context *iio_create_context_from_uri(const char *uri){return strcmp(uri,"local:")?NULL:&ctx;}
void iio_context_destroy(struct iio_context *c){(void)c;const char *p=getenv("P27_MOCK_LOG");if(p){FILE *f=fopen(p,"w");if(f){fprintf(f,"destroyed=%u enabled=%u\n",destroyed,enabled);fclose(f);}}}
int iio_context_set_timeout(struct iio_context *c,unsigned int t){(void)c;(void)t;return 0;}
struct iio_device *iio_context_find_device(const struct iio_context *c,const char *n){(void)c;return !strcmp(n,"ad9361-phy")?&phy:!strcmp(n,"cf-ad9361-lpc")?&adc:NULL;}
struct iio_channel *iio_device_find_channel(const struct iio_device *d,const char *n,bool out){(void)d;if(out)return !strcmp(n,"altvoltage0")?&lo:NULL;if(!strcmp(n,"voltage0"))return &channels[0];if(!strcmp(n,"voltage1"))return &channels[1];return NULL;}
unsigned int iio_device_get_channels_count(const struct iio_device *d){(void)d;return 4;}
struct iio_channel *iio_device_get_channel(const struct iio_device *d,unsigned int i){(void)d;return i<4?&channels[i]:NULL;}
void iio_channel_disable(struct iio_channel *c){enabled&=~(1u<<c->index);}
void iio_channel_enable(struct iio_channel *c){enabled|=1u<<c->index;}
bool iio_channel_is_scan_element(const struct iio_channel *c){return c->index<4;}
bool iio_channel_is_output(const struct iio_channel *c){return c->index==9;}
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *c){(void)c;static struct iio_data_format f={.length=16,.bits=12,.shift=0,.is_signed=true,.repeat=1};f.bits=fault("format")?16:12;return &f;}
ssize_t iio_device_get_sample_size(const struct iio_device *d){(void)d;return enabled==3?4:-1;}
struct iio_buffer *iio_device_create_buffer(const struct iio_device *d,size_t frames,bool cyclic){(void)d;if(cyclic)return NULL;struct iio_buffer *b=calloc(1,sizeof *b);if(b){b->size=frames*4;b->data=malloc(b->size);if(!b->data){free(b);return NULL;}}return b;}
ssize_t iio_buffer_refill(struct iio_buffer *b){if(fault("refill") && b->block==3)return -5;for(size_t n=0;n<b->size/4;n++){uint16_t i=(uint16_t)((b->block*97+n)%4096),q=(uint16_t)(4095-i);b->data[n*4]=i;b->data[n*4+1]=i>>8;b->data[n*4+2]=q;b->data[n*4+3]=q>>8;}b->block++;return b->size;}
void iio_buffer_destroy(struct iio_buffer *b){destroyed++;free(b->data);free(b);}
void *iio_buffer_first(const struct iio_buffer *b,const struct iio_channel *c){return b->data+c->index*2;}
void *iio_buffer_end(const struct iio_buffer *b){return b->data+b->size;}
ptrdiff_t iio_buffer_step(const struct iio_buffer *b){(void)b;return fault("step")?8:4;}
ssize_t iio_channel_attr_read(const struct iio_channel *c,const char *a,char *dest,size_t size){(void)c;const char *s=!strcmp(a,"sampling_frequency")?"30720000":!strcmp(a,"rf_bandwidth")?"18000000":!strcmp(a,"gain_control_mode")?"manual":!strcmp(a,"hardwaregain")?"0.000000 dB":!strcmp(a,"rf_port_select")?"A_BALANCED":!strcmp(a,"frequency")?"2450000000":"bad";if(fault("config") && !strcmp(a,"gain_control_mode"))s="slow_attack";return snprintf(dest,size,"%s",s);}
ssize_t iio_device_debug_attr_read(const struct iio_device *d,const char *a,char *dest,size_t size){(void)d;(void)a;return snprintf(dest,size,"%s",fault("bist")?"1":"0");}
