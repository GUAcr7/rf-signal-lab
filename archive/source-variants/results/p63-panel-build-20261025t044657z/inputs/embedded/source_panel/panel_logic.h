/* P63 source-panel control logic. Pure state transitions; never performs IO.
 * A future driver must validate source/guard and acknowledge CHECK/START/STOP.
 * LINK is supplied only after firmware identity + a fresh heartbeat are checked.
 */
#ifndef RFSIG_PANEL_LOGIC_H
#define RFSIG_PANEL_LOGIC_H
#include <stdint.h>
#include <string.h>

enum sp_state { SP_OFFLINE, SP_IDLE, SP_CHECKING, SP_READY, SP_STARTING,
                SP_RUNNING, SP_STOPPING, SP_FAULT };
enum sp_effect { SP_NONE, SP_CHECK, SP_START, SP_STOP };
struct sp_control {
    enum sp_state state;
    int selected, seconds, applied_selected, applied_seconds;
    int active_selected, active_seconds, child_active, linked, fault;
    unsigned generation, check_generation;
    int64_t last_now, last_heartbeat, active_started, phase_started;
    int64_t released[10];
};

static inline const char *sp_state_name(enum sp_state s) {
    const char *names[]={"OFFLINE","IDLE","CHECKING","READY","STARTING","RUNNING","STOPPING","FAULT"};
    return s>=SP_OFFLINE && s<=SP_FAULT ? names[s] : "INVALID";
}
static inline const char *sp_effect_name(enum sp_effect e) {
    const char *names[]={"NONE","CHECK","START","STOP"};
    return e>=SP_NONE && e<=SP_STOP ? names[e] : "INVALID";
}
static inline void sp_init(struct sp_control *c) {
    memset(c,0,sizeof *c);c->state=SP_OFFLINE;c->seconds=15;
    c->applied_selected=-1;c->active_selected=-1;
    c->last_now=-1;c->last_heartbeat=-1;c->active_started=-1;c->generation=1;
    for(int i=0;i<10;i++) c->released[i]=-10000;
}
static inline void sp_invalidate(struct sp_control *c) {
    c->applied_selected=-1;c->applied_seconds=0;c->generation++;
}
static inline enum sp_effect sp_clock(struct sp_control *c,int64_t now) {
    if(now<0 || now<c->last_now) {
        c->fault=1;c->linked=0;sp_invalidate(c);
        c->state=c->child_active?SP_STOPPING:SP_FAULT;
        return c->child_active?SP_STOP:SP_NONE;
    }
    c->last_now=now;return SP_NONE;
}
static inline enum sp_effect sp_disconnect(struct sp_control *c,int64_t now) {
    enum sp_effect e=sp_clock(c,now);
    if(c->fault) return e;
    c->linked=0;sp_invalidate(c);
    if(c->child_active) {
        if(c->state==SP_STOPPING) return SP_NONE;
        c->state=SP_STOPPING;return SP_STOP;
    }
    c->state=SP_OFFLINE;return SP_NONE;
}
static inline enum sp_effect sp_tick(struct sp_control *c,int64_t now) {
    enum sp_effect e=sp_clock(c,now);
    if(c->fault) return e;
    if(c->linked && (c->last_heartbeat<0 || now-c->last_heartbeat>=2500))
        return sp_disconnect(c,now);
    if((c->state==SP_CHECKING || c->state==SP_STARTING) && now-c->phase_started>=3000) {
        c->fault=1;sp_invalidate(c);c->state=c->child_active?SP_STOPPING:SP_FAULT;
        return c->child_active?SP_STOP:SP_NONE;
    }
    if(c->child_active && c->active_started>=0 &&
       now-c->active_started>=(int64_t)c->active_seconds*1000+2000 && c->state!=SP_STOPPING) {
        sp_invalidate(c);c->state=SP_STOPPING;return SP_STOP;
    }
    return SP_NONE;
}
static inline enum sp_effect sp_link(struct sp_control *c,int64_t now) {
    /* Expire the old session BEFORE accepting a late heartbeat. A renewal
     * cannot silently preserve READY or an active child across a stale gap. */
    enum sp_effect e=sp_tick(c,now);
    if(c->fault) return e;
    c->last_heartbeat=now;c->linked=1;
    if(c->state==SP_OFFLINE && !c->child_active) c->state=SP_IDLE;
    return e;
}
static inline enum sp_effect sp_touch(struct sp_control *c,int64_t now,
                                     unsigned page,unsigned id,unsigned edge) {
    enum sp_effect e=sp_tick(c,now);
    if(e!=SP_NONE || c->fault || !c->linked || page!=0 || edge!=0 || id<1 || id>9) return e;
    /* STOP always takes priority, including a rapid stop/start/stop sequence. */
    if(id!=7 && now-c->released[id]<250) return SP_NONE;
    c->released[id]=now;
    if(id==7) {
        sp_invalidate(c);
        if(c->child_active) {
            if(c->state==SP_STOPPING) return SP_NONE;
            c->state=SP_STOPPING;return SP_STOP;
        }
        c->state=SP_IDLE;return SP_NONE;
    }
    if(id<=4 || id==8 || id==9) {
        if(id<=4) c->selected=(int)id-1;
        if(id==8 && c->seconds>8) {c->seconds-=5;if(c->seconds<8)c->seconds=8;}
        if(id==9 && c->seconds<60) {c->seconds+=5;if(c->seconds>60)c->seconds=60;}
        sp_invalidate(c);
        if(c->child_active) {
            if(c->state==SP_STOPPING) return SP_NONE;
            c->state=SP_STOPPING;return SP_STOP;
        }
        c->state=SP_IDLE;return SP_NONE;
    }
    if(id==5 && !c->child_active && c->state!=SP_CHECKING) {
        sp_invalidate(c);
        c->check_generation=c->generation;c->phase_started=now;c->state=SP_CHECKING;return SP_CHECK;
    }
    if(id==6 && c->state==SP_READY && !c->child_active &&
       c->applied_selected==c->selected && c->applied_seconds==c->seconds) {
        c->child_active=1;c->active_selected=c->selected;c->active_seconds=c->seconds;
        c->active_started=now;c->phase_started=now;c->state=SP_STARTING;return SP_START;
    }
    return SP_NONE;
}
static inline enum sp_effect sp_check_done(struct sp_control *c,unsigned generation,int ok,int64_t now) {
    enum sp_effect e=sp_tick(c,now);
    if(e!=SP_NONE || c->fault || !c->linked || c->state!=SP_CHECKING || generation!=c->generation) return e;
    if(!ok) {c->fault=1;sp_invalidate(c);c->state=SP_FAULT;return SP_NONE;}
    c->applied_selected=c->selected;c->applied_seconds=c->seconds;c->state=SP_READY;
    return SP_NONE;
}
static inline enum sp_effect sp_submitted(struct sp_control *c,int64_t now) {
    enum sp_effect e=sp_tick(c,now);
    if(e!=SP_NONE || c->fault) return e;
    if(c->state==SP_STARTING && c->child_active) c->state=SP_RUNNING;
    return SP_NONE;
}
static inline enum sp_effect sp_finished(struct sp_control *c,int clean,int64_t now) {
    enum sp_effect e=sp_clock(c,now);
    if(!c->child_active) {c->fault=1;c->state=SP_FAULT;sp_invalidate(c);return e;}
    c->child_active=0;sp_invalidate(c);
    if(!clean || c->fault) {c->fault=1;c->state=SP_FAULT;return SP_NONE;}
    c->state=c->linked?SP_IDLE:SP_OFFLINE;return SP_NONE;
}
#endif
