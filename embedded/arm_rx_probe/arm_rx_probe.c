/* Bounded ARM local-IIO RX snapshots. No RF attributes or TX calls are written. */
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
#include <limits.h>

#define API(X) \
 X(iio_library_get_version) X(iio_create_context_from_uri) X(iio_context_destroy) \
 X(iio_context_set_timeout) X(iio_context_find_device) X(iio_device_find_channel) \
 X(iio_device_get_channels_count) X(iio_device_get_channel) X(iio_channel_disable) \
 X(iio_channel_enable) X(iio_channel_is_scan_element) X(iio_channel_is_output) \
 X(iio_channel_get_data_format) X(iio_device_get_sample_size) X(iio_device_create_buffer) \
 X(iio_buffer_refill) X(iio_buffer_destroy) X(iio_buffer_first) X(iio_buffer_end) \
 X(iio_buffer_step) X(iio_channel_convert) X(iio_channel_attr_read) X(iio_device_debug_attr_read)
#define DECLARE(n) static __typeof__(&n) fn_##n;
API(DECLARE)

static double seconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) { perror("clock_gettime"); exit(2); }
    return (double)t.tv_sec+(double)t.tv_nsec*1e-9;
}
static int read_attr(FILE *f,struct iio_channel *channel,const char *name,const char *key) {
    char value[256];
    ssize_t n=fn_iio_channel_attr_read(channel,name,value,sizeof value-1);
    if (n<0 || n>=(ssize_t)sizeof value) return -1;
    value[n]='\0';fprintf(f,"%s=%s\n",key,value);return 0;
}
static int config(FILE *f,struct iio_device *phy,struct iio_device *adc) {
    struct iio_channel *p=fn_iio_device_find_channel(phy,"voltage0",false);
    struct iio_channel *lo=fn_iio_device_find_channel(phy,"altvoltage0",true);
    struct iio_channel *a=fn_iio_device_find_channel(adc,"voltage0",false);
    if (!p || !lo || !a) return -1;
    if (read_attr(f,p,"sampling_frequency","phy_sampling_frequency") ||
        read_attr(f,p,"rf_bandwidth","rf_bandwidth") ||
        read_attr(f,p,"gain_control_mode","gain_control_mode") ||
        read_attr(f,p,"hardwaregain","hardwaregain") ||
        read_attr(f,lo,"frequency","rx_lo") ||
        read_attr(f,a,"sampling_frequency","adc_sampling_frequency")) return -1;
    const char *keys[]={"bist_prbs","bist_tone","loopback"};
    for (int j=0;j<3;j++) {
        char value[256];ssize_t n=fn_iio_device_debug_attr_read(phy,keys[j],value,sizeof value-1);
        if (n<0 || n>=(ssize_t)sizeof value) return -1;
        value[n]='\0';fprintf(f,"%s=%s\n",keys[j],value);
        /* Refuse test-pattern/loopback modes instead of silently claiming real input. */
        if (strspn(value,"0 \n\r\t")!=strlen(value)) return -1;
    }
    return ferror(f)?-1:0;
}
static FILE *new_file(const char *dir,const char *name) {
    char path[512];
    if (snprintf(path,sizeof path,"%s/%s",dir,name)>=(int)sizeof path) return NULL;
    /* C11 exclusive-create is provided by the target glibc. */
    return fopen(path,"wbx");
}
static int session(struct iio_context *ctx,struct iio_device *phy,struct iio_device *adc,
                   const char *dir,int number,size_t samples,int blocks) {
    int status=1;struct iio_buffer *buffer=NULL;FILE *raw=NULL,*meta=NULL,*cfg=NULL;
    struct iio_channel *channels[2];char name[80];
    channels[0]=fn_iio_device_find_channel(adc,"voltage0",false);
    channels[1]=fn_iio_device_find_channel(adc,"voltage1",false);
    if (!channels[0] || !channels[1]) goto done;
    for (unsigned int j=0;j<fn_iio_device_get_channels_count(adc);j++)
        fn_iio_channel_disable(fn_iio_device_get_channel(adc,j));
    for (int j=0;j<2;j++) {
        const struct iio_data_format *fmt=fn_iio_channel_get_data_format(channels[j]);
        if (!fn_iio_channel_is_scan_element(channels[j]) || fn_iio_channel_is_output(channels[j]) ||
            fmt->length!=16 || !fmt->is_signed || fmt->repeat!=1 || fmt->with_scale || fmt->bits>16 || !fmt->bits) goto done;
        fn_iio_channel_enable(channels[j]);
    }
    snprintf(name,sizeof name,"session-%d.before.txt",number);cfg=new_file(dir,name);
    if (!cfg || config(cfg,phy,adc)) goto done;
    if (fclose(cfg)) { cfg=NULL;goto done; }cfg=NULL;
    if (fn_iio_device_get_sample_size(adc)!=4) goto done;
    snprintf(name,sizeof name,"session-%d.iq",number);raw=new_file(dir,name);
    snprintf(name,sizeof name,"session-%d.json",number);meta=new_file(dir,name);
    if (!raw || !meta) goto done;
    buffer=fn_iio_device_create_buffer(adc,samples,false);
    if (!buffer) { perror("create RX buffer");goto done; }
    fprintf(meta,"{\"session\":%d,\"block_samples\":%zu,\"block_limit\":%d,\"format\":[",number,samples,blocks);
    for (int j=0;j<2;j++) {
        const struct iio_data_format *f=fn_iio_channel_get_data_format(channels[j]);
        fprintf(meta,"%s{\"channel\":\"voltage%d\",\"length\":%u,\"bits\":%u,\"shift\":%u,\"signed\":%s,\"be\":%s,\"fully_defined\":%s,\"repeat\":%u}",j?",":"",j,f->length,f->bits,f->shift,f->is_signed?"true":"false",f->is_be?"true":"false",f->is_fully_defined?"true":"false",f->repeat);
    }
    fprintf(meta,"],\"hardware_gaps\":\"unknown\",\"RF_input\":\"unknown\",\"RF_writes\":false,\"blocks\":[");
    double start=seconds();
    for (int b=0;b<blocks;b++) {
        double before=seconds();ssize_t bytes=fn_iio_buffer_refill(buffer);double after=seconds();
        if (bytes<0) { fprintf(stderr,"refill=%zd\n",bytes);goto done; }
        ptrdiff_t step=fn_iio_buffer_step(buffer);
        char *first[2]={fn_iio_buffer_first(buffer,channels[0]),fn_iio_buffer_first(buffer,channels[1])};
        char *end=fn_iio_buffer_end(buffer);
        if (step!=4 || bytes!=(ssize_t)(samples*4)) goto done;
        int minimum=INT_MAX,maximum=INT_MIN;int64_t sum=0;
        for (size_t n=0;n<samples;n++) {
            int16_t pair[2];unsigned char disk[4];
            for (int j=0;j<2;j++) {
                char *src=first[j]+n*step;
                if (src+2>end) goto done;
                fn_iio_channel_convert(channels[j],&pair[j],src);
                int v=pair[j];if (v<minimum)minimum=v;if(v>maximum)maximum=v;
                sum+=(int64_t)v*v;
                uint16_t u=(uint16_t)pair[j];disk[2*j]=(unsigned char)u;disk[2*j+1]=(unsigned char)(u>>8);
            }
            if (fwrite(disk,1,4,raw)!=4) goto done;
        }
        fprintf(meta,"%s{\"index\":%d,\"refill_bytes\":%zd,\"refill_ms\":%.9g,\"host_start_s\":%.9g,\"host_done_s\":%.9g,\"sum_I2_Q2\":%lld,\"mean_I2_Q2\":%.12g,\"minimum\":%d,\"maximum\":%d}",b?",":"",b,bytes,(after-before)*1000,before-start,after-start,(long long)sum,(double)sum/samples,minimum,maximum);
    }
    fn_iio_buffer_destroy(buffer);buffer=NULL;
    snprintf(name,sizeof name,"session-%d.after.txt",number);cfg=new_file(dir,name);
    if (!cfg || config(cfg,phy,adc)) goto done;
    if (fclose(cfg)) {cfg=NULL;goto done;}cfg=NULL;
    struct rusage usage;if(getrusage(RUSAGE_SELF,&usage))goto done;
    fprintf(meta,"],\"elapsed_s\":%.9g,\"maxrss_kib\":%ld,\"buffer_released\":true}\n",seconds()-start,usage.ru_maxrss);
    if(ferror(raw)||ferror(meta))goto done;
    status=0;
done:
    if(buffer)fn_iio_buffer_destroy(buffer);
    if(raw && fclose(raw))status=1;
    if(meta && fclose(meta))status=1;
    if(cfg)fclose(cfg);
    for(unsigned int j=0;j<fn_iio_device_get_channels_count(adc);j++)fn_iio_channel_disable(fn_iio_device_get_channel(adc,j));
    (void)ctx;
    return status;
}
int main(int argc,char **argv) {
    struct iio_context *ctx=NULL;int status=1;
    if(argc!=2){fprintf(stderr,"usage: arm-rx-probe existing-new-output-directory\n");return 2;}
    void *library=dlopen("libiio.so.0",RTLD_NOW|RTLD_LOCAL);
    if(!library){fprintf(stderr,"%s\n",dlerror());return 2;}
#define LOAD(n) {void *sym=dlsym(library,#n);if(!sym){fprintf(stderr,"missing %s\n",#n);goto done;} _Static_assert(sizeof fn_##n==sizeof sym,"function pointer width"); memcpy(&fn_##n,&sym,sizeof sym);}
    API(LOAD)
    unsigned int major,minor;char tag[8];fn_iio_library_get_version(&major,&minor,tag);
    printf("libiio=%u.%u\n",major,minor);
    if(major!=0 || minor!=24){fprintf(stderr,"Expected validated libiio 0.24\n");goto done;}
    ctx=fn_iio_create_context_from_uri("local:");if(!ctx){perror("local IIO context");goto done;}
    if(fn_iio_context_set_timeout(ctx,3000))goto done;
    struct iio_device *phy=fn_iio_context_find_device(ctx,"ad9361-phy"),*adc=fn_iio_context_find_device(ctx,"cf-ad9361-lpc");
    if(!phy || !adc)goto done;
    if(session(ctx,phy,adc,argv[1],1,4096,8))goto done;
    printf("ARM_RX_SESSION_PASS session=1 blocks=8 samples=32768\n");
    if(session(ctx,phy,adc,argv[1],2,1024,4))goto done;
    printf("ARM_RX_SESSION_PASS session=2 blocks=4 samples=4096\n");
    status=0;
done:
    if(ctx)fn_iio_context_destroy(ctx);
    dlclose(library);
    printf("ARM_RX_CONTEXT_RELEASED status=%d\n",status);
    return status;
}
