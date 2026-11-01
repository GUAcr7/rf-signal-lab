/* Bounded sparse RX1 diagnostic. Raw prefix samples only, NOT a complete stream.
 * Capture loop performs no filesystem writes or per-sample IIO conversion.
 * No RF attribute writes or TX functions are linked through the dynamic API.
 */
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>

#define BLOCK_FRAMES 65536u
#define PREFIX_FRAMES 8192u
#define STRIDE 8u
#define KEPT (PREFIX_FRAMES/STRIDE)
#define MAX_BLOCKS 512u
#define API(X) \
 X(iio_library_get_version) X(iio_create_context_from_uri) X(iio_context_destroy) \
 X(iio_context_set_timeout) X(iio_context_find_device) X(iio_device_find_channel) \
 X(iio_device_get_channels_count) X(iio_device_get_channel) X(iio_channel_disable) \
 X(iio_channel_enable) X(iio_channel_is_scan_element) X(iio_channel_is_output) \
 X(iio_channel_get_data_format) X(iio_device_get_sample_size) X(iio_device_create_buffer) \
 X(iio_buffer_refill) X(iio_buffer_destroy) X(iio_buffer_first) X(iio_buffer_end) \
 X(iio_buffer_step) X(iio_channel_attr_read) X(iio_device_debug_attr_read)
#define DECLARE(n) static __typeof__(&n) fn_##n;
API(DECLARE)

struct stamp { double start,refill,extracted; };
static double now(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)){perror("clock");exit(2);}
    return t.tv_sec+t.tv_nsec*1e-9;
}
static FILE *new_file(const char *dir,const char *name) {
    char path[512];
    if(snprintf(path,sizeof path,"%s/%s",dir,name)>=(int)sizeof path)return NULL;
    return fopen(path,"wbx");
}
static int attr(FILE *log,struct iio_channel *channel,const char *name,const char *key,const char *expected) {
    char value[256];
    ssize_t n=fn_iio_channel_attr_read(channel,name,value,sizeof value-1);
    if(n<0 || n>=(ssize_t)sizeof value)return -1;
    value[n]=0;value[strcspn(value,"\r\n")]=0;
    fprintf(log,"%s=%s\n",key,value);
    if(strcmp(value,expected)){fprintf(stderr,"config mismatch %s=%s\n",key,value);return -1;}
    return 0;
}
static int config(const char *dir,const char *name,struct iio_device *phy) {
    FILE *log=new_file(dir,name);if(!log)return -1;
    struct iio_channel *rx=fn_iio_device_find_channel(phy,"voltage0",false);
    struct iio_channel *lo=fn_iio_device_find_channel(phy,"altvoltage0",true);
    int status=-1;
    if(!rx || !lo)goto done;
    if(attr(log,rx,"sampling_frequency","sample_rate_hz","30720000") ||
       attr(log,rx,"rf_bandwidth","rf_bandwidth_hz","18000000") ||
       attr(log,rx,"gain_control_mode","gain_mode","manual") ||
       attr(log,rx,"hardwaregain","gain_db","0.000000 dB") ||
       attr(log,rx,"rf_port_select","rx_port","A_BALANCED") ||
       attr(log,lo,"frequency","rx_lo_hz","2450000000"))goto done;
    const char *keys[]={"bist_prbs","bist_tone","loopback"};
    for(int j=0;j<3;j++) {
        char value[256];ssize_t n=fn_iio_device_debug_attr_read(phy,keys[j],value,sizeof value-1);
        if(n<0 || n>=(ssize_t)sizeof value)goto done;
        value[n]=0;fprintf(log,"%s=%s\n",keys[j],value);
        if(strspn(value,"0 \r\n\t")!=strlen(value))goto done;
    }
    status=ferror(log)?-1:0;
done:
    if(fclose(log))status=-1;
    return status;
}
int main(int argc,char **argv) {
    struct iio_context *ctx=NULL;struct iio_device *adc=NULL;
    struct iio_buffer *buffer=NULL;void *lib=NULL;
    unsigned char *saved=NULL;struct stamp *stamps=NULL;FILE *raw=NULL,*meta=NULL;
    int status=1;unsigned int completed=0;
    if(argc!=3){fprintf(stderr,"usage: arm-rx-diagnostic NEW_DIRECTORY BLOCKS_16_TO_512\n");return 2;}
    char *tail=NULL;errno=0;unsigned long count=strtoul(argv[2],&tail,10);
    if(errno || !tail || *tail || count<16 || count>MAX_BLOCKS){fprintf(stderr,"invalid block count\n");return 2;}
    lib=dlopen("libiio.so.0",RTLD_NOW|RTLD_LOCAL);
    if(!lib){fprintf(stderr,"%s\n",dlerror());goto done;}
#define LOAD(n) {void *sym=dlsym(lib,#n);if(!sym){fprintf(stderr,"missing %s\n",#n);goto done;} _Static_assert(sizeof fn_##n==sizeof sym,"function pointer width");memcpy(&fn_##n,&sym,sizeof sym);}
    API(LOAD)
    unsigned int major,minor;char tag[8];fn_iio_library_get_version(&major,&minor,tag);
    printf("libiio=%u.%u\n",major,minor);
    /* The current TLZ receiver reports 0.20. Reject an unreviewed ABI. */
    if(major!=0 || minor!=20){fprintf(stderr,"expected receiver libiio 0.20\n");goto done;}
    ctx=fn_iio_create_context_from_uri("local:");if(!ctx)goto done;
    if(fn_iio_context_set_timeout(ctx,3000))goto done;
    struct iio_device *phy=fn_iio_context_find_device(ctx,"ad9361-phy");
    adc=fn_iio_context_find_device(ctx,"cf-ad9361-lpc");
    if(!phy || !adc || config(argv[1],"before.txt",phy))goto done;
    for(unsigned int i=0;i<fn_iio_device_get_channels_count(adc);i++)
        fn_iio_channel_disable(fn_iio_device_get_channel(adc,i));
    struct iio_channel *channels[2];
    for(int j=0;j<2;j++) {
        channels[j]=fn_iio_device_find_channel(adc,j?"voltage1":"voltage0",false);
        if(!channels[j])goto done;
        const struct iio_data_format *f=fn_iio_channel_get_data_format(channels[j]);
        if(!f || !fn_iio_channel_is_scan_element(channels[j]) || fn_iio_channel_is_output(channels[j]) ||
           f->length!=16 || f->bits!=12 || f->shift || !f->is_signed || f->is_be || f->with_scale || f->repeat!=1) {
            fprintf(stderr,"unreviewed scan format\n");goto done;
        }
        fn_iio_channel_enable(channels[j]);
    }
    if(fn_iio_device_get_sample_size(adc)!=4)goto done;
    saved=malloc(count*KEPT*4);stamps=calloc(count,sizeof *stamps);
    if(!saved || !stamps)goto done;
    /* Prefault the small destination, rather than incur first-touch faults in capture. */
    memset(saved,0,count*KEPT*4);
    buffer=fn_iio_device_create_buffer(adc,BLOCK_FRAMES,false);
    if(!buffer){perror("create buffer");goto done;}
    const double begin=now();
    for(unsigned int b=0;b<count;b++) {
        stamps[b].start=now()-begin;
        if(stamps[b].start>15){fprintf(stderr,"diagnostic deadline reached\n");goto done;}
        ssize_t bytes=fn_iio_buffer_refill(buffer);
        stamps[b].refill=now()-begin;
        unsigned char *first=fn_iio_buffer_first(buffer,channels[0]);
        unsigned char *q=fn_iio_buffer_first(buffer,channels[1]);
        unsigned char *end=fn_iio_buffer_end(buffer);
        if(bytes!=(ssize_t)(BLOCK_FRAMES*4) || fn_iio_buffer_step(buffer)!=4 || !first || !q || !end || q!=first+2 || end-first!=(ptrdiff_t)(BLOCK_FRAMES*4)) {
            fprintf(stderr,"refill/layout mismatch bytes=%zd\n",bytes);goto done;
        }
        for(unsigned int k=0;k<KEPT;k++) {
            unsigned char *destination=saved+(b*KEPT+k)*4;
            const unsigned char *source=first+k*STRIDE*4;
            /* Explicitly sign extend the valuable 12 bits. The other source
             * bits are undefined by the format and are not signal data. */
            for(unsigned int j=0;j<2;j++) {
                int value=(source[j*2]|((unsigned int)source[j*2+1]<<8))&4095;
                if(value>=2048)value-=4096;
                uint16_t packed=(uint16_t)value;
                destination[j*2]=(unsigned char)packed;
                destination[j*2+1]=(unsigned char)(packed>>8);
            }
        }
        stamps[b].extracted=now()-begin;completed++;
    }
    const double acquisition_s=now()-begin;
    fn_iio_buffer_destroy(buffer);buffer=NULL;
    if(config(argv[1],"after.txt",phy))goto done;
    const double write_begin=now();
    raw=new_file(argv[1],"prefixes.bin");if(!raw)goto done;
    if(fwrite(saved,4,count*KEPT,raw)!=count*KEPT)goto done;
    if(fclose(raw)){raw=NULL;goto done;}raw=NULL;
    meta=new_file(argv[1],"metadata.json");if(!meta)goto done;
    struct rusage usage;if(getrusage(RUSAGE_SELF,&usage))goto done;
    fprintf(meta,"{\"schema\":\"rfsig.sparse_rx_diagnostic.v1\",\"blocks\":%lu,\"dma_frames\":%u,\"prefix_raw_frames\":%u,\"stride\":%u,\"kept_frames_per_block\":%u,\"channels\":2,\"source_format\":\"le:S12/16>>0\",\"storage\":\"LE_s16_IQ_12bit_sign_extended\",\"sample_rate_hz\":30720000,\"complete_stream_saved\":false,\"lossless_proven\":false,\"RF_attributes_written\":false,\"kernel_queue_count_modified\":false,\"buffer_released\":true,\"acquisition_s\":%.9g,\"post_capture_save_s\":%.9g,\"maxrss_kib\":%ld,\"timestamps\":[",count,BLOCK_FRAMES,PREFIX_FRAMES,STRIDE,KEPT,acquisition_s,now()-write_begin,usage.ru_maxrss);
    for(unsigned int b=0;b<count;b++)
        fprintf(meta,"%s{\"block\":%u,\"refill_start_s\":%.9g,\"refill_end_s\":%.9g,\"prefix_saved_s\":%.9g}",b?",":"",b,stamps[b].start,stamps[b].refill,stamps[b].extracted);
    fprintf(meta,"]}\n");
    if(fclose(meta)){meta=NULL;goto done;}meta=NULL;
    status=0;
    printf("SPARSE_RX_PASS blocks=%lu drained_frames=%lu kept_frames=%lu acquisition_s=%.6f\n",count,count*BLOCK_FRAMES,count*KEPT,acquisition_s);
done:
    if(buffer)fn_iio_buffer_destroy(buffer);
    if(raw)fclose(raw);
    if(meta)fclose(meta);
    if(adc)for(unsigned int i=0;i<fn_iio_device_get_channels_count(adc);i++)fn_iio_channel_disable(fn_iio_device_get_channel(adc,i));
    if(ctx)fn_iio_context_destroy(ctx);
    if(lib)dlclose(lib);
    free(saved);free(stamps);
    printf("SPARSE_RX_RELEASED completed=%u status=%d\n",completed,status);
    return status;
}
