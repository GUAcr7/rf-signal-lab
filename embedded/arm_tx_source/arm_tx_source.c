/* Prepared finite-duration local-IIO TX source. No automatic transmission.
 * Digital zero and released buffers do not prove RF silence or remove LO leakage.
 * The local software deadline is not a hardware power or RF interlock. */
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <ctype.h>
#ifndef ARM_TX_OFFLINE_ONLY
#include <dlfcn.h>
#endif
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#ifndef ARM_TX_OFFLINE_ONLY
#define API(X) \
 X(iio_library_get_version) X(iio_create_context_from_uri) X(iio_context_destroy) \
 X(iio_context_set_timeout) X(iio_context_find_device) X(iio_context_get_attr_value) \
 X(iio_device_find_channel) X(iio_device_get_channels_count) X(iio_device_get_channel) \
 X(iio_channel_get_id) X(iio_channel_is_enabled) X(iio_channel_enable) X(iio_channel_disable) \
 X(iio_channel_is_scan_element) X(iio_channel_is_output) X(iio_channel_get_data_format) \
 X(iio_channel_attr_read) X(iio_channel_attr_write) X(iio_device_debug_attr_read) \
 X(iio_device_get_sample_size) X(iio_device_create_buffer) X(iio_buffer_push) \
 X(iio_buffer_cancel) X(iio_buffer_destroy) X(iio_buffer_first) X(iio_buffer_end) \
 X(iio_buffer_step) X(iio_channel_convert_inverse)
#define DECLARE(n) static __typeof__(&n) fn_##n;
API(DECLARE)
#endif

enum { MAX_SAMPLES=4194304, DDS_COUNT=32, MIN_DDS_COUNT=8 };
#ifndef ARM_TX_OFFLINE_ONLY
static volatile sig_atomic_t signal_stop=0;
static void handle_stop(int n) { (void)n; signal_stop=1; }
static double now_s(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) return -1.0;
    return (double)t.tv_sec+(double)t.tv_nsec*1e-9;
}
static void pause_short(void) {
    struct timespec t={0,20000000};
    while(nanosleep(&t,&t) && errno==EINTR && !signal_stop) { }
}
#endif

/* Self-contained SHA-256, byte order explicitly defined by FIPS 180-4. */
struct sha256 { uint32_t h[8];unsigned char block[64];size_t used;uint64_t bytes; };
static uint32_t ror(uint32_t x,unsigned n) { return (x>>n)|(x<<(32-n)); }
static void sha_block(struct sha256 *s,const unsigned char *b) {
    static const uint32_t k[64]={
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for(int j=0;j<16;j++) w[j]=((uint32_t)b[4*j]<<24)|((uint32_t)b[4*j+1]<<16)|((uint32_t)b[4*j+2]<<8)|b[4*j+3];
    for(int j=16;j<64;j++) {
        uint32_t x=w[j-15],y=w[j-2];
        w[j]=w[j-16]+(ror(x,7)^ror(x,18)^(x>>3))+w[j-7]+(ror(y,17)^ror(y,19)^(y>>10));
    }
    uint32_t a=s->h[0],c=s->h[2],b0=s->h[1],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for(int j=0;j<64;j++) {
        uint32_t t1=h+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+k[j]+w[j];
        uint32_t t2=(ror(a,2)^ror(a,13)^ror(a,22))+((a&b0)^(a&c)^(b0&c));
        h=g;g=f;f=e;e=d+t1;d=c;c=b0;b0=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b0;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_init(struct sha256 *s) {
    static const uint32_t initial[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    memcpy(s->h,initial,sizeof initial);s->used=0;s->bytes=0;
}
static void sha_update(struct sha256 *s,const unsigned char *bytes,size_t count) {
    s->bytes+=(uint64_t)count;
    for(size_t n=0;n<count;n++) {
        s->block[s->used++]=bytes[n];
        if(s->used==64) { sha_block(s,s->block);s->used=0; }
    }
}
static void sha_finish(struct sha256 *s,char hex[65]) {
    uint64_t bits=s->bytes*8;unsigned char pad=0x80,zero=0,length[8];
    sha_update(s,&pad,1);
    while(s->used!=56) sha_update(s,&zero,1);
    for(int j=0;j<8;j++) length[7-j]=(unsigned char)(bits>>(8*j));
    sha_update(s,length,8);
    for(int j=0;j<8;j++) snprintf(hex+8*j,9,"%08" PRIx32,s->h[j]);
}
static int valid_hash(const char *hash) {
    if(!hash || strlen(hash)!=64) return 0;
    for(int j=0;j<64;j++) if(!isxdigit((unsigned char)hash[j])) return 0;
    return 1;
}
static int hash_equal(const char *actual,const char *expected) {
    if(!valid_hash(expected)) return 0;
    for(int j=0;j<64;j++) if(actual[j]!=tolower((unsigned char)expected[j])) return 0;
    return 1;
}
static int sha_selftest(void) {
    const char *input[]={"","abc","abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"};
    const char *expected[]={"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"};
    for(int j=0;j<3;j++) {
        struct sha256 sha;char hex[65];sha_init(&sha);
        for(size_t n=0;n<strlen(input[j]);n++) sha_update(&sha,(const unsigned char *)input[j]+n,1);
        sha_finish(&sha,hex);if(strcmp(hex,expected[j])) return 2;
    }
    printf("SHA256_SELFTEST_PASS vectors=3\n");return 0;
}
static int uint_arg(const char *s,uint64_t *value) {
    if(!s || !*s) return -1;
    for(const char *p=s;*p;p++) if(!isdigit((unsigned char)*p)) return -1;
    errno=0;char *end=NULL;unsigned long long v=strtoull(s,&end,10);
    if(errno || !end || *end) return -1;
    *value=(uint64_t)v;return 0;
}
static int double_arg(const char *s,double *value) {
    if(!s || !*s || isspace((unsigned char)*s)) return -1;
    errno=0;char *end=NULL;double v=strtod(s,&end);
    if(errno || !end || *end || !isfinite(v)) return -1;
    *value=v;return 0;
}
static int gain_readback_number(const char *s,double *value) {
    if(!s || !*s || isspace((unsigned char)*s)) return -1;
    errno=0;char *end=NULL;double v=strtod(s,&end);
    if(errno || !end || end==s || !isfinite(v)) return -1;
    if(*end) {
        /* The validated P201 sysfs hardwaregain appends " dB". Require
         * whitespace followed by the exact unit, never dBm or arbitrary tails. */
        if(!isspace((unsigned char)*end)) return -1;
        while(isspace((unsigned char)*end)) end++;
        if(strcmp(end,"dB")) return -1;
    }
    *value=v;return 0;
}
static int gain_parse_selftest(void) {
    static const struct { const char *text;double expected; } valid[]={
        {"-10.000000 dB",-10.0},{"71.000000 dB",71.0},{"0.000000 dB",0.0},
        {"-10",-10.0},{"71.000000",71.0},{"-10\tdB",-10.0},
        {"-10  dB",-10.0},{"-8.975e1 dB",-89.75}};
    static const char *invalid[]={""," dB"," -10 dB","-10dB","-10 dBm","-10 db",
        "-10 dB garbage","-10 dB ","-10 ","nan dB","inf dB","-inf dB","1e309 dB","junk"};
    for(size_t n=0;n<sizeof valid/sizeof valid[0];n++) {
        double value;if(gain_readback_number(valid[n].text,&value) || value!=valid[n].expected) return 2;
    }
    for(size_t n=0;n<sizeof invalid/sizeof invalid[0];n++) {
        double value;if(!gain_readback_number(invalid[n],&value)) return 2;
    }
    double value;
    /* Unit acceptance is deliberately not added to the generic RF/CLI parser. */
    if(!double_arg("30720000 dB",&value) || !double_arg("-10 dB",&value) ||
       double_arg("30720000",&value) || value!=30720000.0) return 2;
    printf("GAIN_PARSE_SELFTEST_PASS valid=8 rejected=14 generic_unit_rejected=true\n");return 0;
}
static int valid_uuid(const char *text) {
    if(!text || strlen(text)!=36) return 0;
    int nonzero=0;
    for(int j=0;j<36;j++) {
        if(j==8 || j==13 || j==18 || j==23) { if(text[j]!='-') return 0; }
        else {
            if(!isxdigit((unsigned char)text[j])) return 0;
            if(text[j]!='0') nonzero=1;
        }
    }
    return nonzero;
}
static int identity_selftest(void) {
    const char *valid[]={"011edfe3-e45b-462d-b6dd-72422d640e45","12345678-ABCD-4321-9876-123456789ABC"};
    const char *invalid[]={"","00000000-0000-0000-0000-000000000000","011edfe3-e45b-462d-b6dd-72422d640e4",
        "011edfe3-e45b-462d-b6dd-72422d640e455","011edfe3_e45b-462d-b6dd-72422d640e45",
        "011edfe3-e45b-462d-b6dd-72422d640e4g"," 011edfe3-e45b-462d-b6dd-72422d640e45",
        "011edfe3-e45b-462d-b6dd-72422d640e45\n"};
    for(size_t j=0;j<sizeof valid/sizeof valid[0];j++) if(!valid_uuid(valid[j])) return 2;
    for(size_t j=0;j<sizeof invalid/sizeof invalid[0];j++) if(valid_uuid(invalid[j])) return 2;
    printf("IDENTITY_SELFTEST_PASS valid_uuid=2 rejected_uuid=8 nil_rejected=true\n");return 0;
}
static int read_file(const char *path,size_t count,const char *expected_hash,int16_t **samples) {
    int status=-1;FILE *f=fopen(path,"rb");struct stat st;int16_t *data=NULL;
    if(!f) { perror("input file");return -1; }
    if(fstat(fileno(f),&st) || !S_ISREG(st.st_mode) || st.st_size!=(off_t)(count*4)) goto done;
    data=malloc(count*2*sizeof *data);if(!data) goto done;
    int minimum=INT_MAX,maximum=INT_MIN;int64_t energy=0;struct sha256 sha;sha_init(&sha);
    for(size_t n=0;n<count*2;n++) {
        unsigned char b[2];if(fread(b,1,2,f)!=2) goto done;
        sha_update(&sha,b,2);
        uint16_t u=(uint16_t)b[0]|(uint16_t)((uint16_t)b[1]<<8);
        if(u&15u) { fprintf(stderr,"nonzero discarded low bits at component %zu\n",n);goto done; }
        int v=u<32768u?(int)u:(int)u-65536;
        if(v/16 < -2048 || v/16 > 2047) goto done;
        data[n]=(int16_t)v;energy+=(int64_t)v*v;
        if(v<minimum) minimum=v;
        if(v>maximum) maximum=v;
    }
    if(fgetc(f)!=EOF || ferror(f)) goto done;
    char hex[65];sha_finish(&sha,hex);
    if(expected_hash && !hash_equal(hex,expected_hash)) { fprintf(stderr,"input SHA256 mismatch\n");goto done; }
    printf("INPUT_SHA256=%s\n",hex);
    printf("INPUT_CHECK_PASS samples=%zu format=LE_s16_IQ low_bits_zero=4 min=%d max=%d mean_I2_Q2=%.12g\n",count,minimum,maximum,(double)energy/count);
    *samples=data;data=NULL;status=0;
done:
    free(data);if(fclose(f)) status=-1;
    if(status) fprintf(stderr,"input rejected: exact regular LE16 I/Q file and left-aligned signed12 codes required\n");
    return status;
}
#ifndef ARM_TX_OFFLINE_ONLY
static int guard_identity(const char *serial,char *identity,size_t capacity,const char **kind) {
    if(serial && *serial) {
        if(strlen(serial)>=capacity) return -1;
        memcpy(identity,serial,strlen(serial)+1);*kind="hw_serial";return 0;
    }
    /* This fallback identifies one boot session, not permanent hardware.
     * Fixed local proc path: no environment or caller path override exists. */
    FILE *f=fopen("/proc/sys/kernel/random/boot_id","rb");if(!f) return -1;
    char text[128];size_t size=fread(text,1,sizeof text-1,f);
    int failed=ferror(f) || size==0 || size==sizeof text-1;
    if(fclose(f)) failed=1;
    if(failed) return -1;
    text[size]=0;
    if(size && text[size-1]=='\n') text[--size]=0;
    if(size && text[size-1]=='\r') text[--size]=0;
    if(!valid_uuid(text)) return -1;
    if(snprintf(identity,capacity,"boot-session:%s",text)>=(int)capacity) return -1;
    *kind="boot_session";return 0;
}
static int read_attr(struct iio_channel *ch,const char *name,char *value,size_t cap) {
    ssize_t n=fn_iio_channel_attr_read(ch,name,value,cap-1);
    if(n<0 || (size_t)n>=cap) return -1;
    value[n]=0;
    while(n && isspace((unsigned char)value[n-1])) value[--n]=0;
    return n?0:-1;
}
static void print_value(const char *key,const char *value) {
    printf("%s=",key);
    for(const unsigned char *p=(const unsigned char *)value;*p;p++) putchar(isprint(*p)?*p:' ');
    putchar('\n');
}
static int zero_text(const char *value) {
    int seen=0;
    for(const char *p=value;*p;p++) {
        if(*p=='0') seen=1;
        else if(!isspace((unsigned char)*p)) return -1;
    }
    return seen?0:-1;
}
static int attr_number(struct iio_channel *ch,const char *name,double *value) {
    char s[256];if(read_attr(ch,name,s,sizeof s)) return -1;
    if(!strcmp(name,"hardwaregain")) return gain_readback_number(s,value);
    return double_arg(s,value);
}
static int print_format(struct iio_channel *ch,const char *name,int enforce) {
    const struct iio_data_format *f=fn_iio_channel_get_data_format(ch);
    if(!f) return -1;
    printf("%s format=%s:%c%u/%u>>%u repeat=%u scan=%d output=%d enabled=%d fully_defined=%d scale=%d\n",name,f->is_be?"be":"le",f->is_signed?'s':'u',f->bits,f->length,f->shift,f->repeat,fn_iio_channel_is_scan_element(ch),fn_iio_channel_is_output(ch),fn_iio_channel_is_enabled(ch),f->is_fully_defined,f->with_scale);
    if(enforce && (!fn_iio_channel_is_output(ch) || !fn_iio_channel_is_scan_element(ch) || f->length!=16 || f->bits!=16 || f->shift || f->is_be || !f->is_signed || f->repeat!=1 || f->with_scale)) return -1;
    return 0;
}
static int snapshot(struct iio_device *phy,struct iio_device *dac,struct iio_device *adc,int enforce,
                    struct iio_channel **dds) {
    char key[96],value[256];
    struct iio_channel *dma=fn_iio_device_find_channel(dac,"voltage0",true);
    if(!dma || read_attr(dma,"sampling_frequency",value,sizeof value)) return -1;
    print_value("TX_DMA_sampling_frequency",value);
    printf("TX_SOURCE_RATE_SCOPE=DMA_rate_must_equal_PHY_rate_interpolation_bypass_only\n");
    const char *rx_attrs[]={"sampling_frequency","rf_bandwidth","hardwaregain","rf_port_select","gain_control_mode"};
    const char *tx_attrs[]={"sampling_frequency","rf_bandwidth","hardwaregain","rf_port_select"};
    for(int output=0;output<=1;output++) for(int j=0;j<2;j++) {
        char id[32];snprintf(id,sizeof id,"voltage%d",j);
        struct iio_channel *ch=fn_iio_device_find_channel(phy,id,output!=0);if(!ch) return -1;
        const char **attrs=output?tx_attrs:rx_attrs;int count=output?4:5;
        for(int a=0;a<count;a++) {
            if(read_attr(ch,attrs[a],value,sizeof value)) return -1;
            snprintf(key,sizeof key,"%s%d_%s",output?"tx":"rx",j,attrs[a]);print_value(key,value);
        }
    }
    for(int j=0;j<2;j++) {
        char id[32];snprintf(id,sizeof id,"altvoltage%d",j);
        struct iio_channel *ch=fn_iio_device_find_channel(phy,id,true);
        if(!ch || read_attr(ch,"frequency",value,sizeof value)) return -1;
        print_value(j?"tx_lo":"rx_lo",value);
    }
    const char *tests[]={"bist_prbs","bist_tone","loopback"};
    for(int j=0;j<3;j++) {
        ssize_t n=fn_iio_device_debug_attr_read(phy,tests[j],value,sizeof value-1);
        if(n<0 || n>=(ssize_t)sizeof value) return -1;
        value[n]=0;print_value(tests[j],value);
        if(enforce && zero_text(value)) return -1;
    }
    int found_dds=0;
    for(int j=0;j<DDS_COUNT;j++) {
        char id[32];snprintf(id,sizeof id,"altvoltage%d",j);
        dds[j]=fn_iio_device_find_channel(dac,id,true);
        if(!dds[j]) { if(j<MIN_DDS_COUNT) return -1;continue; }
        found_dds++;
        const char *attrs[]={"frequency","phase","scale","raw"};
        for(int a=0;a<4;a++) {
            if(read_attr(dds[j],attrs[a],value,sizeof value)) return -1;
            snprintf(key,sizeof key,"dds%d_%s",j,attrs[a]);print_value(key,value);
            if(enforce && a==2) {
                double scale;if(double_arg(value,&scale) || scale!=0.0) return -1;
            }
        }
    }
    for(unsigned int j=0;j<fn_iio_device_get_channels_count(dac);j++) {
        struct iio_channel *ch=fn_iio_device_get_channel(dac,j);
        const char *id=fn_iio_channel_get_id(ch);
        if(id && !strncmp(id,"altvoltage",10) && fn_iio_channel_is_output(ch)) {
            uint64_t n;if(uint_arg(id+10,&n) || n>=DDS_COUNT) return -1;
        }
    }
    printf("DDS_CHANNELS_INSPECTED=%d\n",found_dds);
    for(int j=0;j<4;j++) {
        char id[32];snprintf(id,sizeof id,"voltage%d",j);
        struct iio_channel *tx=fn_iio_device_find_channel(dac,id,true);
        struct iio_channel *rx=fn_iio_device_find_channel(adc,id,false);
        if(!tx || !rx) return -1;
        snprintf(key,sizeof key,"TX_%s",id);if(print_format(tx,key,enforce)) return -1;
        snprintf(key,sizeof key,"RX_%s",id);if(print_format(rx,key,0)) return -1;
    }
    return ferror(stdout)?-1:0;
}
static int dds_zero(struct iio_channel **dds) {
    int failed=0;
    for(int j=0;j<DDS_COUNT;j++) {
        if(!dds[j]) continue;
        if(fn_iio_channel_attr_write(dds[j],"raw","0")<0) failed=1;
    }
    for(int j=0;j<DDS_COUNT;j++) {
        if(!dds[j]) continue;
        char value[256];double raw;
        if(read_attr(dds[j],"raw",value,sizeof value) || double_arg(value,&raw) || raw!=0.0) failed=1;
    }
    printf("DDS_ZERO_SOURCE_READBACK=%s\n",failed?"FAILED":"PASS");
    return failed?-1:0;
}
struct watchdog {
    pthread_mutex_t mutex;
    struct iio_buffer *buffer;
    double deadline;
    int done,expired;
};
static void *watch_deadline(void *arg) {
    struct watchdog *w=arg;
    for(;;) {
        pthread_mutex_lock(&w->mutex);int done=w->done;pthread_mutex_unlock(&w->mutex);
        if(done) return NULL;
        double current=now_s();
        if(signal_stop || current<0 || current>=w->deadline) {
            /* Thread-safe per libiio 0.24; deliberately never called by signal handler. */
            fn_iio_buffer_cancel(w->buffer);
            pthread_mutex_lock(&w->mutex);w->expired=1;pthread_mutex_unlock(&w->mutex);
            return NULL;
        }
        pause_short();
    }
}
static int run_source(struct iio_context *ctx,struct iio_device *phy,struct iio_device *dac,
                      struct iio_channel **dds,const int16_t *data,size_t count,
                      uint64_t fs,uint64_t lo,uint64_t bw,double gain,double duration,const char *expected_port) {
    struct iio_buffer *buffer=NULL;int status=1,mutated=0,thread_started=0;
    pthread_t thread;struct watchdog watch={PTHREAD_MUTEX_INITIALIZER,NULL,0,0,0};
    struct iio_channel *tx[2]={fn_iio_device_find_channel(dac,"voltage0",true),fn_iio_device_find_channel(dac,"voltage1",true)};
    struct iio_channel *p=fn_iio_device_find_channel(phy,"voltage0",true);
    struct iio_channel *rx=fn_iio_device_find_channel(phy,"voltage0",false);
    struct iio_channel *txlo=fn_iio_device_find_channel(phy,"altvoltage1",true);
    double actual;
    if(!p || !rx || !txlo || !tx[0] || !tx[1]) goto done;
    char port[256];
    if(read_attr(p,"rf_port_select",port,sizeof port) || strcmp(port,expected_port) ||
       attr_number(p,"sampling_frequency",&actual) || actual!=(double)fs ||
       attr_number(rx,"sampling_frequency",&actual) || actual!=(double)fs ||
       attr_number(tx[0],"sampling_frequency",&actual) || actual!=(double)fs ||
       attr_number(txlo,"frequency",&actual) || actual!=(double)lo ||
       attr_number(p,"rf_bandwidth",&actual) || actual!=(double)bw ||
       attr_number(p,"hardwaregain",&actual) || actual!=gain) {
        fprintf(stderr,"current RF/DMA settings do not exactly match request; interpolation bypass required; no configuration is written\n");goto done;
    }
    if(fn_iio_context_set_timeout(ctx,3000)) goto done;
    struct sigaction action;memset(&action,0,sizeof action);action.sa_handler=handle_stop;
    sigemptyset(&action.sa_mask);
    if(sigaction(SIGINT,&action,NULL) || sigaction(SIGTERM,&action,NULL) || sigaction(SIGALRM,&action,NULL)) goto done;
    for(unsigned int j=0;j<fn_iio_device_get_channels_count(dac);j++) fn_iio_channel_disable(fn_iio_device_get_channel(dac,j));
    fn_iio_channel_enable(tx[0]);fn_iio_channel_enable(tx[1]);
    if(fn_iio_device_get_sample_size(dac)!=4) goto done;
    if(signal_stop) goto done;
    /* Match validated pyadi order: select zero first, then buffer post-enable
     * selects DMA. A raw=0 write after create_buffer would select zero again. */
    mutated=1;if(dds_zero(dds)) goto done;
    buffer=fn_iio_device_create_buffer(dac,count,true);
    if(!buffer) { perror("create cyclic TX buffer");goto done; }
    ptrdiff_t step=fn_iio_buffer_step(buffer);
    char *end=fn_iio_buffer_end(buffer),*first[2]={fn_iio_buffer_first(buffer,tx[0]),fn_iio_buffer_first(buffer,tx[1])};
    if(step!=4 || !first[0] || !first[1] || !end) goto done;
    for(size_t n=0;n<count;n++) for(int j=0;j<2;j++) {
        char *dest=first[j]+n*step;
        if(dest+2>end) goto done;
        fn_iio_channel_convert_inverse(tx[j],dest,&data[n*2+(size_t)j]);
    }
    if(signal_stop) goto done;
    double start=now_s();if(start<0) goto done;
    watch.buffer=buffer;watch.deadline=start+duration;
    /* Alarm only requests stop. The thread cancels a blocked push at the same local deadline. */
    alarm((unsigned int)ceil(duration)+3u);
    if(pthread_create(&thread,NULL,watch_deadline,&watch)) goto done;
    thread_started=1;
    if(signal_stop) goto done;
    ssize_t bytes=fn_iio_buffer_push(buffer);
    if(bytes!=(ssize_t)(count*4)) { fprintf(stderr,"cyclic push failed/aborted bytes=%zd\n",bytes);goto done; }
    printf("CYCLIC_PUSH_SUBMITTED samples=%zu deadline_seconds=%.9g\n",count,duration);fflush(stdout);
    for(;;) {
        pthread_mutex_lock(&watch.mutex);int expired=watch.expired;pthread_mutex_unlock(&watch.mutex);
        if(signal_stop || expired) break;
        pause_short();
    }
    printf("TX_SOFTWARE_DEADLINE_END elapsed_seconds=%.9g stop_signal=%d\n",now_s()-start,(int)signal_stop);
    status=0;
done:
    if(thread_started) {
        pthread_mutex_lock(&watch.mutex);watch.done=1;pthread_mutex_unlock(&watch.mutex);
        if(pthread_join(thread,NULL)) status=1;
    }
    alarm(0);
    if(buffer) { fn_iio_buffer_cancel(buffer);fn_iio_buffer_destroy(buffer);buffer=NULL; }
    if(mutated && dds_zero(dds)) status=1;
    for(unsigned int j=0;j<fn_iio_device_get_channels_count(dac);j++) fn_iio_channel_disable(fn_iio_device_get_channel(dac,j));
    pthread_mutex_destroy(&watch.mutex);
    printf("TX_CLEANUP buffer_released=true rf_settings_written=false status=%d\n",status);
    printf("LIMITATION software_deadline_not_hardware_interlock RF_silence_and_LO_leakage_unverified\n");
    return status;
}
#endif
int main(int argc,char **argv) {
    int mode=0,status=2;uint64_t count=0,fs=0,lo=0,bw=0;double gain=0,duration=0;int16_t *samples=NULL;
    if(argc==2 && !strcmp(argv[1],"--sha256-selftest")) return sha_selftest();
    if(argc==2 && !strcmp(argv[1],"--gain-parse-selftest")) return gain_parse_selftest();
    if(argc==2 && !strcmp(argv[1],"--identity-selftest")) return identity_selftest();
    if(argc==2 && !strcmp(argv[1],"--inspect")) mode=1;
    else if((argc==4 || argc==5) && !strcmp(argv[1],"--check")) mode=2;
    else if(argc==13 && !strcmp(argv[1],"--run") && !strcmp(argv[12],"RF_LINK_REVIEWED")) mode=3;
    if(!mode || (mode>=2 && (uint_arg(argv[3],&count) || count<4 || count>MAX_SAMPLES)) ||
       (mode==2 && argc==5 && !valid_hash(argv[4])) ||
       (mode==3 && (uint_arg(argv[4],&fs) || !fs || fs>61440000 || uint_arg(argv[5],&lo) || lo<70000000 || lo>6000000000ULL || uint_arg(argv[6],&bw) || !bw || bw>56000000 || double_arg(argv[7],&gain) || gain>0 || gain< -89.75 || double_arg(argv[8],&duration) || duration<=0 || duration>60 || !*argv[9] || strlen(argv[9])>128 || (strcmp(argv[10],"A") && strcmp(argv[10],"B")) || !valid_hash(argv[11])))) {
        fprintf(stderr,"usage: --inspect | --sha256-selftest | --gain-parse-selftest | --identity-selftest | --check FILE SAMPLES [SHA256] | --run FILE SAMPLES FS TXLO TXBW TXGAIN SECONDS EXPECTED_ID PORT SHA256 RF_LINK_REVIEWED\n");return 2;
    }
    /* All argument and file rejection occurs before dlopen or any device access. */
    const char *expected_hash=mode==3?argv[11]:((mode==2 && argc==5)?argv[4]:NULL);
    if(mode>=2 && read_file(argv[2],(size_t)count,expected_hash,&samples)) return 2;
    if(mode==2) { free(samples);return 0; }
#ifdef ARM_TX_OFFLINE_ONLY
    (void)status;fprintf(stderr,"HARDWARE_DISABLED_OFFLINE_BUILD\n");free(samples);return 2;
#else
    void *library=dlopen("libiio.so.0",RTLD_NOW|RTLD_LOCAL);
    if(!library) { fprintf(stderr,"%s\n",dlerror());free(samples);return 2; }
    struct iio_context *ctx=NULL;
#define LOAD(n) {void *s=dlsym(library,#n);if(!s){fprintf(stderr,"missing %s\n",#n);goto done;} _Static_assert(sizeof fn_##n==sizeof s,"function pointer width");memcpy(&fn_##n,&s,sizeof s);}
    API(LOAD)
    unsigned int major,minor;char tag[8];fn_iio_library_get_version(&major,&minor,tag);
    printf("libiio=%u.%u\n",major,minor);if(major!=0 || minor!=24) goto done;
    ctx=fn_iio_create_context_from_uri("local:");if(!ctx) { perror("local IIO context");goto done; }
    const char *model=fn_iio_context_get_attr_value(ctx,"hw_model");
    const char *serial=fn_iio_context_get_attr_value(ctx,"hw_serial");
    if(!model || strcmp(model,"PUZHI PZSDR P201")) { fprintf(stderr,"exact P201 identity required\n");goto done; }
    print_value("hw_model",model);
    print_value("hw_serial",serial?serial:"MISSING");
    char identity[160];const char *identity_kind=NULL;
    if(guard_identity(serial,identity,sizeof identity,&identity_kind)) { fprintf(stderr,"board serial unavailable and boot-session identity could not be validated\n");goto done; }
    print_value("tx_guard_identity_kind",identity_kind);
    print_value("tx_guard_identity",identity);
    if(mode==3 && strcmp(identity,argv[9])) { fprintf(stderr,"exact TX guard identity required; boot-session IDs must be rechecked after reboot\n");goto done; }
    struct iio_device *phy=fn_iio_context_find_device(ctx,"ad9361-phy"),*dac=fn_iio_context_find_device(ctx,"cf-ad9361-dds-core-lpc"),*adc=fn_iio_context_find_device(ctx,"cf-ad9361-lpc");
    struct iio_channel *dds[DDS_COUNT]={NULL};
    if(!phy || !dac || !adc || snapshot(phy,dac,adc,mode==3,dds)) { fprintf(stderr,"IIO snapshot or TX preconditions rejected\n");goto done; }
    if(mode==1) { printf("INSPECT_PASS read_only=true no_buffers_created=true\n");status=0; }
    else status=run_source(ctx,phy,dac,dds,samples,(size_t)count,fs,lo,bw,gain,duration,argv[10]);
done:
    if(ctx) fn_iio_context_destroy(ctx);
    dlclose(library);free(samples);return status;
#endif
}
