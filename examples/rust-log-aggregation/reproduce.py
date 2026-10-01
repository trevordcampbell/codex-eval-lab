#!/usr/bin/env python3
"""Reproduce the frozen synthetic study offline once rustc is installed.
Creates a NEW state; preserves original measurements. Archived proposals replay
source transformations, not the live model interaction that originally wrote them.
"""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--rustc',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);p.add_argument('--approve-local-benchmark',action='store_true');a=p.parse_args()
if not a.approve_local_benchmark:p.error('Review PREREGISTRATION.md then explicitly approve the local synthetic commands')
if a.out.exists():p.error('--out must be new')
if not (ROOT/'suite/cases.jsonl').exists():subprocess.run([sys.executable,str(ROOT/'generate_suite.py')],check=True)
version=subprocess.check_output([str(a.rustc.resolve()),'--version'],text=True)
if not version.startswith('rustc 1.98.1 '):p.error('Exact reproduction requires rustc 1.98.1 (Linux x86_64 target)')
a.out.mkdir(parents=True);shutil.copytree(ROOT/'app',a.out/'app');shutil.copytree(ROOT/'suite',a.out/'suite')
(a.out/'app/build-config.json').write_text(json.dumps({'rustc':str(a.rustc.resolve()),'cache':str(a.out.resolve()/'build-cache')}))
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
if (ROOT/'engine/src').exists():env['PYTHONPATH']=str(ROOT/'engine/src')
def lab(*args):
 command=[sys.executable,'-m','codex_eval_lab',*map(str,args)];r=subprocess.run(command,env=env,capture_output=True,text=True)
 with (a.out/'commands.jsonl').open('a') as f:f.write(json.dumps({'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})+'\n')
 if r.returncode:raise RuntimeError(r.stderr)
 return json.loads(r.stdout)
state=a.out/'state'
lab('audit',a.out/'suite');lab('start',a.out/'suite','--app',a.out/'app','--state',state,'--approve-cases','--approve-grader','--approve-execution','--note','Operator approved reproduction of preregistered local synthetic benchmark')
for split in ['train','validation']:lab('run',state,'--split',split)
lab('register',state,'--app',a.out/'app','--label','unchanged-before','--hypothesis','Unchanged pre-search timing control')
lab('run',state,'--label','unchanged-before','--split','train')
lab('compare',state,'--baseline','baseline','--candidate','unchanged-before','--split','train')
best='baseline'
for row in [json.loads(s) for s in (ROOT/'artifacts/candidate-history.jsonl').read_text().splitlines()]:
 label=row['candidate'];proposal=a.out/(label+'.json');proposal.write_text(json.dumps(row['proposal']))
 lab('import-proposal',state,'--proposal',proposal,'--label',label,'--base',row['base'])
 with tempfile.TemporaryDirectory(prefix='rust-reproduction-preflight-') as tmp:
  check_app=pathlib.Path(tmp)/'app';shutil.copytree(state/'candidates'/label,check_app)
  test=subprocess.run([sys.executable,'-B',str(ROOT/'test_contract.py')],env={**env,'CANDIDATE_APP':str(check_app)},capture_output=True,text=True)
  (a.out/(label+'-contract-tests.txt')).write_text(test.stdout+test.stderr)
 for split in ['train','validation']:lab('run',state,'--label',label,'--split',split)
 incumbent=lab('compare',state,'--baseline',best,'--candidate',label)
 original=lab('compare',state,'--baseline','baseline','--candidate',label)
 if incumbent['accepted'] and original['accepted']:lab('select',state,'--candidate',label);best=label
lab('register',state,'--app',a.out/'app','--label','unchanged-after','--hypothesis','Unchanged post-search timing control')
lab('run',state,'--label','unchanged-after','--split','train')
lab('compare',state,'--baseline','baseline','--candidate','unchanged-after','--split','train')
lab('finalize',state,'--approve-final');lab('report',state,'--out',a.out/'report.html');lab('export-best',state,'--out',a.out/'winner')
print(json.dumps({'state':str(state),'selected':best,'note':'Fresh measurements, archived model-authored proposals; results need not reproduce exactly'},indent=2))
