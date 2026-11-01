/* Wire-format logic only; stdin/stdout. No UART/RF backend. */
#include <stdio.h>
#include <stdlib.h>
#include "panel_wire.h"

static int selftest(void) {
    struct pw_parser p={0};struct pw_event e;int result=0;unsigned checks=0;uint32_t number_value=0;
#define REQUIRE(x) do {checks++;if(!(x)){fprintf(stderr,"wire assertion %u failed\n",checks);return 1;}} while(0)
    uint8_t number[]={0x71,255,255,255,255,255,255,255};
    for(unsigned i=0;i<8;i++){result=pw_byte(&p,number[i],&e);REQUIRE(result==(i==7?1:0));}
    REQUIRE(e.kind==PW_NUMBER && e.length==4 && pw_number(&e,&number_value) && number_value==UINT32_MAX);
    uint8_t touch[]={0x65,0,6,0,255,255,255};
    for(unsigned i=0;i<7;i++)result=pw_byte(&p,touch[i],&e);
    REQUIRE(result==1 && e.kind==PW_TOUCH && e.payload[1]==6 && e.payload[2]==0);
    REQUIRE(!pw_number(&e,&number_value));
    REQUIRE(pw_byte(&p,0x99,&e)==-1 && p.used==0);
    touch[3]=2;
    for(unsigned i=0;i<7;i++)result=pw_byte(&p,touch[i],&e);
    REQUIRE(result==-1 && p.used==0);
    REQUIRE(pw_byte(&p,0x70,&e)==0);
    for(unsigned i=0;i<128;i++)REQUIRE(pw_byte(&p,'A',&e)==0);
    REQUIRE(pw_byte(&p,255,&e)==0);REQUIRE(pw_byte(&p,255,&e)==0);
    REQUIRE(pw_byte(&p,255,&e)==1 && e.kind==PW_TEXT && e.length==128);
    printf("{\"status\":\"passed_P63_portable_wire_selftest\",\"checks\":%u,\"mode\":\"LOGIC_ONLY_NO_RF\"}\n",checks);
    return 0;
#undef REQUIRE
}
static int nibble(int c) {
    if(c>='0' && c<='9')return c-'0';
    if(c>='a' && c<='f')return c-'a'+10;
    if(c>='A' && c<='F')return c-'A'+10;
    return -1;
}
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--selftest"))return selftest();
    if(argc!=2 || strcmp(argv[1],"--hex-replay"))return 2;
    struct pw_parser p={0};struct pw_event e;int first=-1,c;
    while((c=getchar())!=EOF) {
        if(c=='\n' || c=='\r' || c==' ' || c=='\t') {if(first>=0)return 2;continue;}
        int n=nibble(c);if(n<0)return 2;
        if(first<0){first=n;continue;}
        int result=pw_byte(&p,(uint8_t)(first*16+n),&e);first=-1;
        if(result<0)return 2;
        if(result) {
            printf("{\"mode\":\"LOGIC_ONLY_NO_RF\",\"code\":%u,\"payload\":\"",e.code);
            for(unsigned i=0;i<e.length;i++)printf("%02x",e.payload[i]);
            printf("\"}\n");
        }
    }
    return ferror(stdin) || first>=0 || p.used ? 2:0;
}
