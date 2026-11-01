/* Host-only in-memory libiio 0.24 test double. No device files or sockets.
 * Not an RF simulation and never evidence of physical transmission. */
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct iio_channel { int device,index,output,scan,enabled,raw; char id[32]; };
struct iio_device { int index; unsigned int count; struct iio_channel channels[12]; };
struct iio_context { struct iio_device devices[3]; };
struct iio_buffer {
    unsigned char *bytes;
    size_t count;
    int cancelled;
    pthread_mutex_t mutex;
    pthread_cond_t condition;
};
static pthread_mutex_t log_mutex=PTHREAD_MUTEX_INITIALIZER;
static FILE *log_file;
static int scenario(const char *name) {
    const char *value=getenv("MOCK_IIO_SCENARIO");
    return value && !strcmp(value,name);
}
static void event(const char *name,const char *detail) {
    pthread_mutex_lock(&log_mutex);
    if(!log_file) {
        const char *path=getenv("MOCK_IIO_LOG");
        if(!path) abort();
        log_file=fopen(path,"a");
        if(!log_file) abort();
    }
    /* All names/details below are fixed strings or generated safe channel IDs. */
    fprintf(log_file,"{\"event\":\"%s\",\"detail\":\"%s\"}\n",name,detail?detail:"");
    if(fflush(log_file)) abort();
    pthread_mutex_unlock(&log_mutex);
}
__attribute__((destructor)) static void mock_unloaded(void) {
    if(log_file && fclose(log_file)) abort();
    log_file=NULL;
}
__attribute__((constructor)) static void mock_loaded(void) {
    const char *isolated=getenv("MOCK_IIO_ISOLATED");
    if(!isolated || strcmp(isolated,"1")) abort();
    event("mock_library_loaded","in_memory_only_no_RF");
}
void iio_library_get_version(unsigned int *major,unsigned int *minor,char tag[8]) {
    if(major) *major=0;
    if(minor) *minor=24;
    if(tag) memcpy(tag,"MOCK024",8);
}
static void init_channel(struct iio_channel *ch,int dev,int index,int output,int scan,const char *prefix) {
    ch->device=dev;ch->index=index;ch->output=output;ch->scan=scan;
    ch->raw=dev==1 && !scan?1:0;
    snprintf(ch->id,sizeof ch->id,"%s%d",prefix,index);
}
struct iio_context *iio_create_context_from_uri(const char *uri) {
    event("context_create",uri);
    if(strcmp(uri,"local:")) { errno=EINVAL;return NULL; }
    struct iio_context *ctx=calloc(1,sizeof *ctx);
    if(!ctx) return NULL;
    for(int d=0;d<3;d++) ctx->devices[d].index=d;
    ctx->devices[0].count=6;
    for(int j=0;j<2;j++) {
        init_channel(&ctx->devices[0].channels[j],0,j,0,0,"voltage");
        init_channel(&ctx->devices[0].channels[j+2],0,j,1,0,"voltage");
        init_channel(&ctx->devices[0].channels[j+4],0,j,1,0,"altvoltage");
    }
    ctx->devices[1].count=12;
    ctx->devices[2].count=4;
    for(int j=0;j<4;j++) {
        init_channel(&ctx->devices[1].channels[j],1,j,1,1,"voltage");
        init_channel(&ctx->devices[2].channels[j],2,j,0,1,"voltage");
    }
    for(int j=0;j<8;j++) init_channel(&ctx->devices[1].channels[j+4],1,j,1,0,"altvoltage");
    return ctx;
}
void iio_context_destroy(struct iio_context *ctx) { event("context_destroy","");free(ctx); }
const char *iio_context_get_attr_value(const struct iio_context *ctx,const char *name) {
    (void)ctx;
    if(!strcmp(name,"hw_model")) return scenario("model_mismatch")?"OTHER MOCK":"PUZHI PZSDR P201";
    if(!strcmp(name,"hw_serial")) return scenario("serial_mismatch")?"OTHER-SERIAL":"MOCK-P201-001";
    return NULL;
}
struct iio_device *iio_context_find_device(const struct iio_context *ctx,const char *name) {
    const char *names[]={"ad9361-phy","cf-ad9361-dds-core-lpc","cf-ad9361-lpc"};
    for(int j=0;j<3;j++) if(!strcmp(name,names[j])) return (struct iio_device *)&ctx->devices[j];
    return NULL;
}
int iio_context_set_timeout(struct iio_context *ctx,unsigned int timeout) {
    (void)ctx;char value[32];snprintf(value,sizeof value,"%u",timeout);event("context_timeout",value);return 0;
}
unsigned int iio_device_get_channels_count(const struct iio_device *dev) { return dev->count; }
struct iio_channel *iio_device_get_channel(const struct iio_device *dev,unsigned int index) {
    return index<dev->count?(struct iio_channel *)&dev->channels[index]:NULL;
}
struct iio_channel *iio_device_find_channel(const struct iio_device *dev,const char *id,bool output) {
    for(unsigned int j=0;j<dev->count;j++) {
        const struct iio_channel *ch=&dev->channels[j];
        if(ch->output==(int)output && !strcmp(ch->id,id)) return (struct iio_channel *)ch;
    }
    return NULL;
}
const char *iio_channel_get_id(const struct iio_channel *ch) { return ch->id; }
bool iio_channel_is_output(const struct iio_channel *ch) { return ch->output!=0; }
bool iio_channel_is_scan_element(const struct iio_channel *ch) { return ch->scan!=0; }
bool iio_channel_is_enabled(const struct iio_channel *ch) { return ch->enabled!=0; }
void iio_channel_enable(struct iio_channel *ch) { ch->enabled=1;event("channel_enable",ch->id); }
void iio_channel_disable(struct iio_channel *ch) { ch->enabled=0;event("channel_disable",ch->id); }
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *ch) {
    static const struct iio_data_format tx={.length=16,.bits=16,.shift=0,.is_signed=true,.is_fully_defined=true,.is_be=false,.with_scale=false,.scale=1,.repeat=1};
    static const struct iio_data_format rx={.length=16,.bits=12,.shift=0,.is_signed=true,.is_fully_defined=true,.is_be=false,.with_scale=false,.scale=1,.repeat=1};
    return ch->device==2?&rx:&tx;
}
static ssize_t copy_value(char *dst,size_t capacity,const char *value) {
    size_t count=strlen(value);
    if(count>=capacity) return -ENOSPC;
    memcpy(dst,value,count+1);return (ssize_t)count;
}
ssize_t iio_channel_attr_read(const struct iio_channel *ch,const char *attr,char *dst,size_t capacity) {
    event("attr_read",attr);
    char number[32];const char *value=NULL;
    if(ch->device==1 && !ch->scan) {
        if(!strcmp(attr,"scale")) value=scenario("dds_scale_nonzero")?"0.25":"0";
        else if(!strcmp(attr,"raw")) { snprintf(number,sizeof number,"%d",ch->raw);value=number; }
        else if(!strcmp(attr,"frequency")) value="1000000";
        else if(!strcmp(attr,"phase")) value="0";
    } else if(ch->device==1 && ch->scan && !strcmp(attr,"sampling_frequency")) {
        if(scenario("tx_dma_rate_missing")) return -ENOENT;
        value=scenario("tx_dma_rate_mismatch")?"3840000":"30720000";
    } else if(ch->device==0) {
        if(!strcmp(attr,"sampling_frequency")) value=scenario("rf_mismatch")?"30720001":"30720000";
        else if(!strcmp(attr,"rf_bandwidth")) value="18000000";
        else if(!strcmp(attr,"hardwaregain")) value=ch->output?"-40":"71";
        else if(!strcmp(attr,"rf_port_select")) value=ch->output?(scenario("port_mismatch")?"B":"A"):"A_BALANCED";
        else if(!strcmp(attr,"gain_control_mode")) value="slow_attack";
        else if(!strcmp(attr,"frequency")) value="2400000000";
    }
    return value?copy_value(dst,capacity,value):-ENOENT;
}
ssize_t iio_channel_attr_write(const struct iio_channel *ch,const char *attr,const char *value) {
    if(ch->device!=1 || ch->scan || strcmp(attr,"raw") || strcmp(value,"0")) {
        event("FORBIDDEN_WRITE",attr);return -EPERM;
    }
    event("dds_raw_zero_write",ch->id);
    if(scenario("dds_write_fail") && ch->index==3) { event("dds_raw_zero_failed",ch->id);return -EIO; }
    ((struct iio_channel *)ch)->raw=0;
    return 1;
}
ssize_t iio_device_debug_attr_read(const struct iio_device *dev,const char *attr,char *dst,size_t cap) {
    (void)dev;event("debug_attr_read",attr);return copy_value(dst,cap,"0");
}
ssize_t iio_device_get_sample_size(const struct iio_device *dev) { (void)dev;return 4; }
struct iio_buffer *iio_device_create_buffer(const struct iio_device *dev,size_t count,bool cyclic) {
    event("buffer_create",cyclic?"cyclic":"noncyclic");
    if(dev->index!=1 || !cyclic || scenario("create_fail")) { errno=EIO;return NULL; }
    if(!dev->channels[0].enabled || !dev->channels[1].enabled) { errno=EINVAL;return NULL; }
    struct iio_buffer *buffer=calloc(1,sizeof *buffer);
    if(!buffer) return NULL;
    buffer->count=count;buffer->bytes=calloc(count,4);
    if(!buffer->bytes) { free(buffer);return NULL; }
    if(pthread_mutex_init(&buffer->mutex,NULL) || pthread_cond_init(&buffer->condition,NULL)) abort();
    return buffer;
}
ptrdiff_t iio_buffer_step(const struct iio_buffer *buffer) { (void)buffer;return scenario("step_fail")?2:4; }
void *iio_buffer_end(const struct iio_buffer *buffer) { return buffer->bytes+4*buffer->count; }
void *iio_buffer_first(const struct iio_buffer *buffer,const struct iio_channel *ch) {
    if(scenario("first_fail") && ch->index==1) return NULL;
    return buffer->bytes+2*ch->index;
}
void iio_channel_convert_inverse(const struct iio_channel *ch,void *dst,const void *src) {
    (void)ch;memcpy(dst,src,2);
}
ssize_t iio_buffer_push(struct iio_buffer *buffer) {
    event("buffer_push","");
    if(scenario("push_error")) return -EIO;
    if(scenario("push_block")) {
        event("buffer_push_blocking","");pthread_mutex_lock(&buffer->mutex);
        while(!buffer->cancelled) pthread_cond_wait(&buffer->condition,&buffer->mutex);
        pthread_mutex_unlock(&buffer->mutex);event("buffer_push_unblocked_by_cancel","");return -ECANCELED;
    }
    return (ssize_t)(4*buffer->count);
}
void iio_buffer_cancel(struct iio_buffer *buffer) {
    event("buffer_cancel","");pthread_mutex_lock(&buffer->mutex);
    buffer->cancelled=1;pthread_cond_broadcast(&buffer->condition);pthread_mutex_unlock(&buffer->mutex);
}
void iio_buffer_destroy(struct iio_buffer *buffer) {
    event("buffer_destroy","");pthread_cond_destroy(&buffer->condition);pthread_mutex_destroy(&buffer->mutex);
    free(buffer->bytes);free(buffer);
}
