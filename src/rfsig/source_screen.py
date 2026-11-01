"""Teammate page contract and IO-free selection state. No RF operations."""
from dataclasses import dataclass, field
from .tjc_protocol import Event, set_text

SIGNALS=('TONE','BPSK','QPSK','16QAM')
BUTTONS={1:'bTone',2:'bBpsk',3:'bQpsk',4:'bQam',5:'bApply',6:'bStart',7:'bStop',8:'bMinus',9:'bPlus'}

@dataclass
class PanelSelection:
    signal: int=0
    seconds: int=15
    applied: tuple|None=None
    last: dict=field(default_factory=dict)

    def touch(self,event:Event,now:float):
        """Route only page0 releases. START is a request, never RF authorization."""
        if event.kind!='touch' or len(event.payload)!=3:
            return None
        page,button,edge=event.payload
        if page!=0 or edge!=0 or button not in BUTTONS:
            return None
        if button!=7 and now-self.last.get(button,-100)<.25:
            return None
        self.last[button]=now
        if button<=4:
            self.signal=button-1;self.applied=None
            return 'select'
        if button in (8,9):
            self.seconds=max(8,min(60,self.seconds+(5 if button==9 else -5)))
            self.applied=None
            return 'duration'
        if button==5:
            # Caller must validate the actual backend before marking applied.
            self.applied=None
            return 'check'
        if button==6:
            return 'start' if self.applied==(self.signal,self.seconds) else 'unapplied'
        self.applied=None
        return 'stop'

    def checked(self):
        self.applied=(self.signal,self.seconds)

    def fields(self,status):
        label='SEL '+SIGNALS[self.signal]
        # The delivered HMI has short text buffers. Keep selection <=9 bytes;
        # applied/running belongs in t1, never a long suffix that gets truncated.
        return {'t1':status,'t2':label,'t4':str(self.seconds)}

    def commands(self,status):
        return [set_text(key,value) for key,value in self.fields(status).items()]
