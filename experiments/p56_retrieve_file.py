"""P36 bounded SHA/CRC archive reader, with one additional P56 tar path."""
import argparse,re
import p36_retrieve_file as reader

def p56_path(value):
    if not re.fullmatch(r'/tmp/p35-p56-\d{6}/e\.tar\.gz',value):
        raise argparse.ArgumentTypeError('expected a uniquely staged P56 evidence tar')
    return value

if __name__=='__main__':
    reader.remote_path=p56_path
    raise SystemExit(reader.main())
