"""Explicit bench-test plan; emits recorded touch IDs, never runs RF directly."""
class ProtocolRegression:
    plan=(('bpsk',True),('bpsk',False),('qpsk',False),('qam16',False))
    ids={'bpsk':2,'qpsk':3,'qam16':4}
    def __init__(self):
        self.index=0;self.phase='select';self.due=0;self.started=None
    def next_button(self,status,busy,now):
        if self.index>=len(self.plan) or now<self.due:return None
        signal,cancel=self.plan[self.index]
        if self.phase=='select' and status=='IDLE' and not busy:
            self.phase='apply';self.due=now+.3;return self.ids[signal]
        if self.phase=='apply' and status=='IDLE' and not busy:
            self.phase='ready';return 5
        if self.phase=='ready' and status=='READY' and not busy:
            self.phase='running';return 6
        if self.phase=='running' and status=='RUNNING':
            self.phase='active';self.started=now
        if self.phase=='active':
            if cancel and status=='RUNNING' and now-self.started>=3:
                self.phase='finish';return 7
            if not cancel and status=='IDLE' and not busy:self.phase='finish'
        if self.phase=='finish' and status=='IDLE' and not busy:
            self.index+=1;self.phase='select';self.due=now+.3
        return None
