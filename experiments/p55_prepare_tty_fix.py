"""Create a corrected deployment driver without changing any frozen ML input."""
from p45_checkpoint import ROOT,read,sha

def main():
    frozen=read(ROOT/'results/p52-export-20261024T043113Z/report.json')
    original=ROOT/frozen['frozen_inputs']['ARM_verifier']['path']
    if sha(original)!=frozen['frozen_inputs']['ARM_verifier']['sha256']:raise ValueError('original frozen verifier changed')
    text=original.read_text('utf-8')
    old="        upload(board,remote+'/a',arm.read_bytes());board.command('stty -echo')"
    new="        board.command(\"PS1='# '\")\n        upload(board,remote+'/a',arm.read_bytes())\n        board.command(\"PS1=''\");board.command('stty -echo')"
    if text.count(old)!=1:raise ValueError('uploader anchor differs')
    text=text.replace(old,new)
    anchor="    def save():write(out/'report.json',r)"
    extra="    r.update(deployment_driver_revision='p55_tty_upload_fix',frozen_original_verifier='"+frozen['frozen_inputs']['ARM_verifier']['path']+"',frozen_original_verifier_sha256='"+sha(original)+"',model_or_preprocessor_modified=False,fix='nonempty prompt only during existing upload protocol; empty prompt for framed numeric output')\n"
    if text.count(anchor)!=1:raise ValueError('record anchor differs')
    target=ROOT/'experiments/p55_arm_verify.py'
    if target.exists():raise ValueError('do not overwrite deployment driver')
    target.write_text(text.replace(anchor,extra+anchor),encoding='utf-8');print(target)
if __name__=='__main__':main()
