"""Resolve Yocto /tmp symlinks before claiming temporary writes are RAM-only."""
import re

def validate_ram_tmp(mount_text,resolved):
    if resolved not in ('/tmp','/var/volatile/tmp'):raise ValueError('unexpected /tmp symlink target')
    mounts=[]
    for line in mount_text.splitlines():
        row=line.split()
        if len(row)==6 and row[1].startswith('/') and row[4].isdigit() and row[5].isdigit():
            if resolved==row[1] or resolved.startswith(row[1].rstrip('/')+'/'):mounts.append(row)
    if not mounts or max(mounts,key=lambda row:len(row[1]))[2]!='tmpfs':
        raise ValueError('resolved /tmp is not on the closest tmpfs mount')
    return resolved

def board_ram_tmp(board):
    text=board.command('readlink -f /tmp')
    paths=re.findall(r'^(/[^\r\n]+)\r?$',text,re.M)
    if len(paths)!=1:raise ValueError('ambiguous /tmp real path')
    return validate_ram_tmp(board.command('cat /proc/mounts'),paths[0])
