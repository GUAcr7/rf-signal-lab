"""Render a pinned X init policy; fall back to original desktop outside P43."""
import hashlib,re
from p32_session import ROOT
def render(directory,original):
    if not re.fullmatch(r'/etc/p44-\d{8}T\d{6}Z',directory):raise ValueError('policy directory')
    if b'killproc xinit' not in original or b'xinit /etc/X11/Xsession' not in original:raise ValueError('unexpected original X init')
    awake=(ROOT/'board/boot/p44-display-awake.sh').read_bytes()
    text=(ROOT/'board/boot/p44-xserver-policy.sh.in').read_text('utf-8')
    for k,v in dict(DIRECTORY=directory,ORIGINAL_SHA=hashlib.sha256(original).hexdigest(),AWAKE_SHA=hashlib.sha256(awake).hexdigest()).items():text=text.replace('@@'+k+'@@',v)
    if '@@' in text:raise ValueError('unrendered policy')
    return dict(awake=awake,boot=text.encode('ascii'),original=original)
