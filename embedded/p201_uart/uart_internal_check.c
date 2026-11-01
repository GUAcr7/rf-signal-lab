/* Bounded P201 UART0 LOCAL loopback via the kernel driver, no RF operations.
 * No physical wire loopback claim. Restores modem controls and termios.
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
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
/* Verified in both Linux UAPI and this ARM sysroot's asm-generic/termios.h;
 * libc's sys/ioctl.h does not expose this flag on every architecture. */
#ifndef TIOCM_LOOP
#define TIOCM_LOOP 0x8000
#endif
static volatile sig_atomic_t interrupted;
static void stop(int signum){(void)signum;interrupted=1;}
static int64_t ms(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static int identity(const char *device) {
    char path[PATH_MAX],line[256],name[64];
    if(strcmp(device,"/dev/ttyPS1"))return 0;
    if(!realpath("/sys/class/tty/ttyPS1/device",path) ||
       (!strstr(path,"/e0000000.serial") && !strstr(path,"/e0000000.uart")))return 0;
    FILE *f=fopen("/proc/consoles","r");if(!f)return 0;
    while(fgets(line,sizeof line,f))if(sscanf(line,"%63s",name)==1 && !strcmp(name,"ttyPS1")){fclose(f);return 0;}
    fclose(f);return 1;
}
int main(int argc,char **argv) {
    if(argc!=4 || strcmp(argv[1],"--device") || strcmp(argv[3],"--run-internal") || !identity(argv[2])){
        fprintf(stderr,"requires verified non-console /dev/ttyPS1 and --run-internal\n");return 2;
    }
    signal(SIGINT,stop);signal(SIGTERM,stop);
    int fd=open(argv[2],O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);if(fd<0){perror("open");return 3;}
    struct termios saved,raw;int old_modem=0,have_tty=0,have_modem=0,result=3,restored=0;
    size_t sent=0,received=0;uint8_t tx[512],rx[512];
    if(ioctl(fd,TIOCEXCL) || tcgetattr(fd,&saved))goto done;
    have_tty=1;raw=saved;cfmakeraw(&raw);raw.c_cflag&=~(CSIZE|PARENB|CSTOPB|CRTSCTS);
    raw.c_cflag|=CS8|CLOCAL|CREAD;raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
    if(cfsetispeed(&raw,B115200) || cfsetospeed(&raw,B115200) || tcsetattr(fd,TCSANOW,&raw))goto done;
    if(ioctl(fd,TIOCMGET,&old_modem))goto done;
    have_modem=1;int loop=old_modem|TIOCM_LOOP;
    if(ioctl(fd,TIOCMSET,&loop) || tcflush(fd,TCIOFLUSH))goto done;
    for(unsigned i=0;i<sizeof tx;i++)tx[i]=(uint8_t)i;
    int64_t start=ms(),end=start+2000;if(start<0)goto done;
    result=4;
    while(received<sizeof rx && !interrupted) {
        int64_t now=ms();if(now<0 || now>=end)break;
        struct pollfd p={fd,(short)(POLLIN|(sent<sizeof tx?POLLOUT:0)),0};
        int n=poll(&p,1,(int)(end-now));if(n<0 && errno==EINTR)continue;
        if(n<=0 || (p.revents&(POLLERR|POLLNVAL|POLLHUP)))break;
        if((p.revents&POLLOUT) && sent<sizeof tx){ssize_t z=write(fd,tx+sent,sizeof tx-sent);if(z>0)sent+=(size_t)z;else if(z<0 && errno!=EAGAIN && errno!=EINTR)break;}
        if(p.revents&POLLIN){ssize_t z=read(fd,rx+received,sizeof rx-received);if(z>0)received+=(size_t)z;else if(z<0 && errno!=EAGAIN && errno!=EINTR)break;}
    }
    if(interrupted)result=130;
    else if(sent==sizeof tx && received==sizeof rx)result=memcmp(tx,rx,sizeof tx)?5:0;
done:
    restored=1;
    if(have_modem && ioctl(fd,TIOCMSET,&old_modem))restored=0;
    if(have_tty && tcsetattr(fd,TCSANOW,&saved))restored=0;
    if(!restored)result=3;
    if(close(fd) && result==0)result=3;
    printf("{\"status\":\"%s\",\"mode\":\"UART0_DRIVER_LOCAL_LOOPBACK\",\"sent\":%zu,\"received\":%zu,\"controls_restored\":%s,\"physical_pins_verified\":false,\"exit_code\":%d}\n",
        result==0?"pass":"failed_or_incomplete",sent,received,restored?"true":"false",result);
    return result;
}
