import sys,pathlib,random,unittest,os
ROOT=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[os.environ.get('CANDIDATE_APP',str(ROOT/'app')),str(ROOT/'suite')]
from runner import execute
from oracle import oracle
class Contract(unittest.TestCase):
 def check(self,text,want=None):
  expected=oracle(text)
  if want is not None:self.assertEqual(expected,want)
  actual=execute(text,iterations=1)
  self.assertEqual(actual['answer'],expected);self.assertEqual(actual['reference_answer'],expected)
 def test_hand_derived(self):
  self.check('',{'invalid':0,'rows':[]})
  self.check('/a\t200\t7\n/a\t500\t9\r\n',{'invalid':0,'rows':[['/a',2,1,16]]})
  self.check('/a\t200\t18446744073709551615\n/a\t400\t18446744073709551615',{'invalid':0,'rows':[['/a',2,1,36893488147419103230]]})
  self.check('\n\r\n/a\t+200\t1\n/a\t200\t-1\n/a\t200\t18446744073709551616\n/a\t99\t1\n/a\t600\t1\n/a\t２００\t1\n/a\t200\t1\textra\n',{'invalid':9,'rows':[]})
  self.check('/東京\t00500\t0001\r',{'invalid':0,'rows':[['/東京',1,1,1]]})
  self.check('/\u2028x\t200\t1\n/\x00\t200\t1\n',{'invalid':1,'rows':[['/\u2028x',1,0,1]]})
  self.check('/x\u2029y\t200\t1\n',{'invalid':0,'rows':[['/x\u2029y',1,0,1]]})
  self.check('/x\t'+'0'*5000+'200\t'+'0'*5000+'1',{'invalid':0,'rows':[['/x',1,0,1]]})
  self.check('/x\t200\t'+'9'*5000,{'invalid':1,'rows':[]})
 def test_property_and_metamorphic(self):
  r=random.Random(90125)
  for _ in range(80):
   lines=[f'/p{r.randrange(9)}\t{r.choice([100,200,399,400,599])}\t{r.randrange(10**10)}' for _ in range(r.randrange(1,80))]
   text='\n'.join(lines);self.check(text)
   out=oracle(text);r.shuffle(lines);self.check('\n'.join(lines),out)
   doubled=oracle(text+'\n'+text)
   self.assertEqual(doubled['rows'],[[p,c*2,e*2,b*2] for p,c,e,b in out['rows']]); self.check(text+'\n'+text,doubled)
 def test_adversarial_mutations(self):
  valid='/x\t200\t42'
  for text in [valid+'\r\r',valid+'\t',valid.replace('200',' 200'),valid.replace('42','+42'),valid.replace('200','18446744073709551616200'),valid.replace('/x','/x\x7f'),valid.replace('/x',''),valid.replace('42','²'),valid.replace('42','4_2'),valid.replace('42','1e3')]:self.check(text,{'invalid':1,'rows':[]})
if __name__=='__main__':unittest.main(verbosity=2)
