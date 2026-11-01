"""Reject incomplete or misleading UART inference evidence without board access."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p52_arm_verify import parse_inference

REF=np.array([[2.,1.,0.],[0.,2.,1.],[1.,0.,2.]])
TEXT='0,2,1,0,0\r\n1,0,2,1,1\r\n2,1,0,2,2\r\n'

def test_uart_shell_text_cannot_become_inference():
    a,b=parse_inference('root# command\r\n'+TEXT+'__P46_deadbeef__:0\r\n',REF)
    np.testing.assert_array_equal(a[:,4],[0,1,2]);assert b==[]

@pytest.mark.parametrize('text',[TEXT.splitlines()[0],TEXT+TEXT,TEXT.replace('2,1,0,2,2','1,1,0,2,2'),TEXT.replace('2,1,0,2,2','2,nan,0,2,2')])
def test_incomplete_duplicate_out_of_order_nonfinite_rejected(text):
    with pytest.raises(ValueError):parse_inference(text,REF)

def test_matching_logits_with_wrong_reported_class_rejected():
    with pytest.raises(ValueError,match='classes differ'):parse_inference(TEXT.replace('0,2,1,0,0','0,2,1,0,1'),REF)

def test_wrong_logits_rejected_even_if_class_matches():
    with pytest.raises(AssertionError):parse_inference(TEXT.replace('0,2,1,0,0','0,2.1,1,0,0'),REF)
