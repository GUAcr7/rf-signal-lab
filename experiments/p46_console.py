"""Prompt-safe framed commands for the P201, including echo-off transfers."""
from datetime import datetime,timezone
import re,uuid
from p32_session import BoardConsole

class Console(BoardConsole):
    def command(self,command,timeout=8):
        if len(command)>72 or '\n' in command or '\r' in command:raise ValueError('one short command required')
        token='__P46_'+uuid.uuid4().hex[:8]+'__'
        marker="printf '\\n"+token+":%s\\n' \"$?\""
        self.port.write((command+'\r'+marker+'\r').encode('ascii'))
        text=self.read(timeout,r'^'+token+r':\d+\r?$')
        match=re.search(r'^'+token+r':(\d+)\r?$',text,re.M);rc=int(match[1]) if match else None
        self.record['stages'].append(dict(port=self.name,command=command,output=text,exit_code=rc,utc=datetime.now(timezone.utc).isoformat()));self.save()
        if rc!=0:raise RuntimeError(f'{self.name} command failed rc={rc}: {command}')
        return text
