/* Bounded TJC return subset, portable C, no device or command execution.
 * Feed bytes, collect validated events, then route only through the controller.
 * An error resets the parser; the IO adapter must invalidate its link/arming.
 */
#ifndef RFSIG_PANEL_WIRE_H
#define RFSIG_PANEL_WIRE_H
#include <stdint.h>
#include <string.h>
enum pw_kind { PW_STATUS, PW_TOUCH, PW_PAGE, PW_NUMBER, PW_TEXT };
struct pw_event {enum pw_kind kind;uint8_t code,payload[128];unsigned length;};
struct pw_parser {uint8_t bytes[132];unsigned used;};
static inline void pw_reset(struct pw_parser *p) {p->used=0;}
static inline int pw_status(uint8_t v) {
    switch(v) {
    case 0:case 1:case 2:case 3:case 4:case 5:case 6:case 9:
    case 0x11:case 0x12:case 0x1a:case 0x1b:case 0x1c:case 0x1d:case 0x1e:case 0x1f:
    case 0x20:case 0x23:case 0x24:case 0x86:case 0x87:case 0x88:case 0x89:case 0xfd:case 0xfe:return 1;
    default:return 0;
    }
}
static inline int pw_byte(struct pw_parser *p,uint8_t byte,struct pw_event *e) {
    unsigned size=0;enum pw_kind kind=PW_STATUS;
    if(p->used>=sizeof p->bytes){pw_reset(p);return -1;}
    p->bytes[p->used++]=byte;uint8_t code=p->bytes[0];
    if(code==0x70) {
        kind=PW_TEXT;
        if(p->used>=4 && p->bytes[p->used-3]==255 && p->bytes[p->used-2]==255 && byte==255) size=p->used;
        else if(p->used>=sizeof p->bytes){pw_reset(p);return -1;}
        else return 0;
    } else {
        if(pw_status(code))size=4;
        else if(code==0x65){size=7;kind=PW_TOUCH;}
        else if(code==0x66){size=5;kind=PW_PAGE;}
        else if(code==0x71){size=8;kind=PW_NUMBER;}
        else {pw_reset(p);return -1;}
        if(p->used<size)return 0;
    }
    if(p->bytes[size-3]!=255 || p->bytes[size-2]!=255 || p->bytes[size-1]!=255 ||
       (kind==PW_TOUCH && p->bytes[3]>1)) {pw_reset(p);return -1;}
    e->kind=kind;e->code=code;e->length=size-4;
    memcpy(e->payload,p->bytes+1,e->length);pw_reset(p);return 1;
}
static inline int pw_number(const struct pw_event *e,uint32_t *value) {
    if(e->kind!=PW_NUMBER || e->length!=4)return 0;
    *value=(uint32_t)e->payload[0] | (uint32_t)e->payload[1]<<8 |
           (uint32_t)e->payload[2]<<16 | (uint32_t)e->payload[3]<<24;
    return 1;
}
#endif
