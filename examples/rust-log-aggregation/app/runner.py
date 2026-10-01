"""Protected, cooperative-local compile and measurement adapter; not editable."""
import hashlib,json,os,pathlib,statistics,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/'build-config.json').read_text())
FLAGS=['--edition=2024','-C','opt-level=3','-C','codegen-units=1','-C','debuginfo=0','--target=x86_64-unknown-linux-gnu']
def build():
    compiler=CONFIG['rustc']
    identity=subprocess.check_output([compiler,'--version','--verbose'],text=True)
    sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['aggregate.rs','reference.rs','driver.rs']}
    key=hashlib.sha256(json.dumps([sources,identity,FLAGS],sort_keys=True).encode()).hexdigest()
    cache=pathlib.Path(CONFIG['cache']); cache.mkdir(parents=True,exist_ok=True)
    binary=cache/(key+'.bin'); meta=cache/(key+'.json')
    if not binary.exists():
        started=time.perf_counter()
        result=subprocess.run([compiler,*FLAGS,str(ROOT/'driver.rs'),'-o',str(binary)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr)
        info={'source_hashes':sources,'compiler':identity,'flags':FLAGS,'cold_compile_s':time.perf_counter()-started,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
        meta.write_text(json.dumps(info,indent=2))
    info=json.loads(meta.read_text())
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=info['binary_sha256']:raise RuntimeError('Cached binary digest mismatch')
    return binary,info

def execute(text, iterations=None, seed=0):
    binary,build_info=build()
    line_count=max(1,text.count('\n'))
    if iterations is None:iterations=max(1,min(256,(131072+line_count-1)//line_count))
    # A single CPU affinity minimizes migration without claiming exclusive hardware.
    affinity=None
    if hasattr(os,'sched_getaffinity'):
        allowed=os.sched_getaffinity(0); affinity=min(allowed); os.sched_setaffinity(0,{affinity})
    started=time.perf_counter_ns()
    run=subprocess.run([str(binary),str(iterations),str(seed)],input=text,capture_output=True,text=True,check=True)
    external=time.perf_counter_ns()-started
    lines=run.stdout.rstrip('\n').split('\n'); samples=[float(v) for v in lines[0].split('\t')[1].split(',')]
    refs=[float(v) for v in lines[1].split('\t')[1].split(',')]
    order=lines[2].split('\t')[1]
    boundary=next(i for i,l in enumerate(lines) if l.startswith('REFERENCE_INVALID\t'))
    def answer(invalid,rows):return {'invalid':invalid,'rows':[[p,int(c),int(e),int(b)] for p,c,e,b in [r.split('\t') for r in rows]]}
    actual=answer(int(lines[3].split('\t')[1]),lines[4:boundary])
    ref=answer(int(lines[boundary].split('\t')[1]),lines[boundary+1:])
    return {'answer':actual,'reference_answer':ref,'samples_ns':samples,'reference_samples_ns':refs,'order':order,'median_ns':statistics.median(samples),'reference_median_ns':statistics.median(refs),'external_process_ns':external,'iterations':iterations,'warmups':2,'cpu_affinity':affinity,'build':build_info}
if __name__=='__main__':
    req=json.load(sys.stdin); result=execute(req['input']['text'],seed=req['seed'])
    json.dump({'output':result,'model':'rust-log-aggregate-v1','usage':{'cost_usd':0},'trace':[{'role':'tool','name':'rust_aggregate','content':{'source_sha256':result['build']['source_hashes']['aggregate.rs'],'median_ns':result['median_ns'],'invalid_rows':result['answer']['invalid'],'output_rows':len(result['answer']['rows'])}}]},sys.stdout)
