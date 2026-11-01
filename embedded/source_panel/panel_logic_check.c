/* Executable logic checker only. No UART, process spawning, IIO or RF backend. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "panel_logic.h"

static void snapshot(struct sp_control *c,enum sp_effect e) {
    printf("{\"mode\":\"LOGIC_ONLY_NO_RF\",\"state\":\"%s\",\"effect\":\"%s\","
           "\"selected\":%d,\"seconds\":%d,\"applied\":%d,\"active\":%d,"
           "\"active_seconds\":%d,\"generation\":%u,\"run_generation\":%u,\"child_active\":%d,\"fault\":%d}\n",
           sp_state_name(c->state),sp_effect_name(e),c->selected,c->seconds,
           c->applied_selected,c->active_selected,c->active_seconds,c->generation,c->run_generation,c->child_active,c->fault);
    fflush(stdout);
}

static int selftest(void) {
    struct sp_control c;unsigned checks=0;
#define REQUIRE(x) do {checks++;if(!(x)){fprintf(stderr,"logic assertion %u failed\n",checks);return 1;}} while(0)
    sp_init(&c);REQUIRE(c.state==SP_OFFLINE && !c.child_active);
    REQUIRE(sp_touch(&c,0,0,6,0)==SP_NONE && !c.child_active);
    sp_link(&c,1);REQUIRE(c.state==SP_IDLE);
    REQUIRE(sp_touch(&c,100,0,5,1)==SP_NONE);
    REQUIRE(sp_touch(&c,200,0,5,0)==SP_CHECK && c.state==SP_CHECKING);
    unsigned token=c.check_generation;
    sp_check_done(&c,token,1,210);REQUIRE(c.state==SP_READY);
    REQUIRE(sp_touch(&c,300,0,6,0)==SP_START && c.state==SP_STARTING);
    REQUIRE(sp_touch(&c,400,0,6,0)==SP_NONE);
    sp_submitted(&c,c.run_generation,410);REQUIRE(c.state==SP_RUNNING);
    REQUIRE(sp_touch(&c,500,0,3,0)==SP_STOP && c.selected==2 && c.active_selected==0);
    REQUIRE(sp_touch(&c,600,0,6,0)==SP_NONE && c.state==SP_STOPPING);
    sp_finished(&c,c.run_generation,1,700);REQUIRE(c.state==SP_IDLE && c.applied_selected==-1);
    REQUIRE(sp_touch(&c,900,0,6,0)==SP_NONE);
    REQUIRE(sp_touch(&c,1000,0,5,0)==SP_CHECK);
    token=c.check_generation;
    sp_touch(&c,1100,0,4,0);sp_check_done(&c,token,1,1200);
    REQUIRE(c.state==SP_IDLE && c.applied_selected==-1);
    sp_touch(&c,1400,0,5,0);sp_check_done(&c,c.check_generation,1,1500);
    REQUIRE(sp_touch(&c,1600,0,6,0)==SP_START);
    REQUIRE(sp_tick(&c,2501)==SP_STOP && !c.linked && c.state==SP_STOPPING);
    sp_link(&c,2600);REQUIRE(c.state==SP_STOPPING);
    sp_finished(&c,c.run_generation,1,2700);REQUIRE(c.state==SP_IDLE && c.applied_selected==-1);
    REQUIRE(sp_touch(&c,2800,0,6,0)==SP_NONE);
    sp_touch(&c,3000,0,5,0);sp_check_done(&c,c.check_generation,0,3100);
    REQUIRE(c.state==SP_FAULT);
    REQUIRE(sp_touch(&c,3200,0,7,0)==SP_NONE && c.state==SP_FAULT);
    sp_init(&c);sp_link(&c,10);sp_touch(&c,100,0,5,0);sp_check_done(&c,c.check_generation,1,110);
    sp_touch(&c,200,0,6,0);REQUIRE(sp_touch(&c,300,0,7,0)==SP_STOP);
    sp_submitted(&c,c.run_generation,400);REQUIRE(c.state==SP_STOPPING);
    sp_finished(&c,c.run_generation,0,500);REQUIRE(c.state==SP_FAULT);
    sp_init(&c);sp_link(&c,100);sp_tick(&c,90);REQUIRE(c.state==SP_FAULT);
    printf("{\"status\":\"passed_P63_ARM_portable_logic_selftest\",\"checks\":%u,"
           "\"mode\":\"LOGIC_ONLY_NO_RF\",\"UART_opened\":false,\"RF_operations\":false}\n",checks);
    return 0;
#undef REQUIRE
}

int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--selftest")) return selftest();
    if(argc!=2 || strcmp(argv[1],"--replay")) {
        fprintf(stderr,"logic-only checker: --selftest | --replay; no hardware mode\n");return 2;
    }
    struct sp_control c;sp_init(&c);snapshot(&c,SP_NONE);
    char line[160],op[32],extra;long long now;unsigned page,id,edge;int good;
    unsigned pending=0,token;
    while(fgets(line,sizeof line,stdin)) {
        if(!strchr(line,'\n')) return 2;
        enum sp_effect effect=SP_NONE;
        if(sscanf(line,"%31s %lld %c",op,&now,&extra)==2 && !strcmp(op,"LINK")) effect=sp_link(&c,now);
        else if(sscanf(line,"%31s %lld %c",op,&now,&extra)==2 && !strcmp(op,"LOST")) effect=sp_disconnect(&c,now);
        else if(sscanf(line,"%31s %lld %c",op,&now,&extra)==2 && !strcmp(op,"TICK")) effect=sp_tick(&c,now);
        else if(sscanf(line,"%31s %lld %c",op,&now,&extra)==2 && !strcmp(op,"SUBMITTED")) effect=sp_submitted(&c,c.run_generation,now);
        else if(sscanf(line,"%31s %lld %u %c",op,&now,&token,&extra)==3 && !strcmp(op,"SUBMITTED_GEN")) effect=sp_submitted(&c,token,now);
        else if(sscanf(line,"%31s %lld %u %u %u %c",op,&now,&page,&id,&edge,&extra)==5 && !strcmp(op,"TOUCH") && page<=255 && id<=255 && edge<=1) {
            effect=sp_touch(&c,now,page,id,edge);
            if(effect==SP_CHECK) pending=c.check_generation;
        } else if(sscanf(line,"%31s %lld %u %d %c",op,&now,&token,&good,&extra)==4 && !strcmp(op,"CHECKED_GEN") && (good==0 || good==1)) effect=sp_check_done(&c,token,good,now);
        else if(sscanf(line,"%31s %lld %d %c",op,&now,&good,&extra)==3 && !strcmp(op,"CHECKED") && (good==0 || good==1)) effect=sp_check_done(&c,pending,good,now);
        else if(sscanf(line,"%31s %lld %u %d %c",op,&now,&token,&good,&extra)==4 && !strcmp(op,"FINISHED_GEN") && (good==0 || good==1)) effect=sp_finished(&c,token,good,now);
        else if(sscanf(line,"%31s %lld %d %c",op,&now,&good,&extra)==3 && !strcmp(op,"FINISHED") && (good==0 || good==1)) effect=sp_finished(&c,c.run_generation,good,now);
        else return 2;
        snapshot(&c,effect);
    }
    return ferror(stdin)?2:0;
}
