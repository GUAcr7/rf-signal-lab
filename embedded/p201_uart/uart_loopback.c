/* Bounded external UART loopback check. No screen protocol or RF operations.
 * Production build refuses ttyPS0 and requires sysfs UART0 e0000000 identity.
 * Wire loopback ONLY after independent pin/voltage verification.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void on_signal(int value) { (void)value; stopped=1; }
static long long milliseconds(void) {
    struct timespec ts;
    if(clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    return (long long)ts.tv_sec*1000+ts.tv_nsec/1000000;
}
static int number(const char *s,int low,int high) {
    char *end=NULL; errno=0; long v=strtol(s,&end,10);
    return errno || !*s || *end || v<low || v>high ? -1 : (int)v;
}
static int allowed_device(const char *device,int test_pty) {
#ifdef UART_HOST_TEST
    if(test_pty) return !strncmp(device,"/dev/pts/",9);
#else
    (void)test_pty;
#endif
    char expected[PATH_MAX],actual[PATH_MAX];
    /* Never use the serial console, even if aliases are misconfigured. */
    if(strcmp(device,"/dev/ttyPS1") && strcmp(device,"/dev/ttyPS2") && strcmp(device,"/dev/ttyPS3")) return 0;
    if(snprintf(expected,sizeof expected,"/sys/class/tty/%s/device",device+5)>=(int)sizeof expected) return 0;
    if(!realpath(expected,actual)) return 0;
    return strstr(actual,"/e0000000.serial")!=NULL || strstr(actual,"/e0000000.uart")!=NULL;
}
int main(int argc,char **argv) {
    const char *device=NULL; int run=0,test_pty=0,count=1024,timeout=2000;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--device") && i+1<argc) device=argv[++i];
        else if(!strcmp(argv[i],"--bytes") && i+1<argc) count=number(argv[++i],1,4096);
        else if(!strcmp(argv[i],"--timeout-ms") && i+1<argc) timeout=number(argv[++i],100,10000);
        else if(!strcmp(argv[i],"--run-loopback")) run=1;
#ifdef UART_HOST_TEST
        else if(!strcmp(argv[i],"--test-pty")) test_pty=1;
#endif
        else { fprintf(stderr,"unknown/incomplete argument\n"); return 2; }
    }
    if(!device || !run || count<0 || timeout<0) {
        fprintf(stderr,"Requires --device /dev/ttyPSN --run-loopback [--bytes 1..4096] [--timeout-ms 100..10000]\n");return 2;
    }
    if(!allowed_device(device,test_pty)) { fprintf(stderr,"refused: verified non-console UART0 required\n");return 2; }
    signal(SIGINT,on_signal);signal(SIGTERM,on_signal);
    int fd=open(device,O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);
    if(fd<0) { perror("open");return 3; }
    struct termios saved,raw;
    if(tcgetattr(fd,&saved)) { perror("tcgetattr");close(fd);return 3; }
    raw=saved;cfmakeraw(&raw);
    raw.c_cflag &= ~(CSIZE|PARENB|CSTOPB|CRTSCTS);
    raw.c_cflag |= CS8|CLOCAL|CREAD;
    raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
    if(cfsetispeed(&raw,B115200) || cfsetospeed(&raw,B115200) || tcsetattr(fd,TCSANOW,&raw)) {
        perror("termios");close(fd);return 3;
    }
    uint8_t tx[4096],rx[4096];
    for(int i=0;i<count;i++) tx[i]=(uint8_t)i; /* includes NUL/CR/LF/XON/XOFF/FF */
    size_t sent=0,received=0;int result=4;
    long long start=milliseconds(),deadline=start+timeout;
    if(start<0 || tcflush(fd,TCIOFLUSH)) goto done;
    while(received<(size_t)count && !stopped) {
        long long now=milliseconds();
        if(now<0 || now>=deadline) break;
        struct pollfd p={fd,(short)(POLLIN|(sent<(size_t)count?POLLOUT:0)),0};
        int ready=poll(&p,1,(int)(deadline-now));
        if(ready<0) { if(errno==EINTR) continue; break; }
        if(!ready || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) break;
        if((p.revents&POLLOUT) && sent<(size_t)count) {
            ssize_t n=write(fd,tx+sent,(size_t)count-sent);
            if(n>0) sent+=(size_t)n;
            else if(n<0 && errno!=EAGAIN && errno!=EINTR) break;
        }
        if(p.revents&POLLIN) {
            ssize_t n=read(fd,rx+received,(size_t)count-received);
            if(n>0) received+=(size_t)n;
            else if(n<0 && errno!=EAGAIN && errno!=EINTR) break;
        }
    }
    if(stopped) result=130;
    else if(sent==(size_t)count && received==(size_t)count) result=memcmp(tx,rx,(size_t)count)?5:0;
done:
    if(tcsetattr(fd,TCSANOW,&saved) && result==0) result=3;
    close(fd);
    printf("{\"status\":\"%s\",\"sent\":%zu,\"received\":%zu,\"baud\":115200,\"exit_code\":%d}\n",
           result==0?"pass":"failed_or_incomplete",sent,received,result);
    return result;
}
