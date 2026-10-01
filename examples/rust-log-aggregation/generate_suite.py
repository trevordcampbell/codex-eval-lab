"""Generate fixed synthetic realizations, keeping paired sizes in one source group.
Generation can be rerun, but the optimizer must not inspect reserved case contents.
"""
import hashlib,json,pathlib,random
ROOT=pathlib.Path(__file__).resolve().parent
PROFILES=['low-cardinality','high-cardinality','zipf-like','unicode','malformed','mixed']
def workload(seed,n,profile):
 r=random.Random(seed); suffix=r.randrange(1000000)
 card={'low-cardinality':8,'high-cardinality':max(16,n//2),'zipf-like':128,'unicode':64,'malformed':64,'mixed':96}[profile]
 paths=[f'/api/{suffix}/item/{i:05d}' for i in range(card)]
 if profile=='unicode':paths=[p+['/café','/東京','/😀','/αβγ'][i%4] for i,p in enumerate(paths)]
 lines=[]
 for i in range(n):
  k=(0 if r.random()<.9 else r.randrange(card)) if profile=='zipf-like' else r.randrange(card)
  path=paths[k]; status=r.choice([200,200,201,204,301,400,404,429,500,503]); size=r.randrange(1048576)
  line=f'{path}\t{status}\t{size}'
  if profile in ('malformed','mixed') and r.random()<(.23 if profile=='malformed' else .06):
   line=r.choice([f'{path}\t+200\t{size}',f'{path}\t200\t18446744073709551616',f'{path}\t099\t2',f'{path}\t600\t3',f'{path}\t200\t-1',f'{path}\t２００\t4',f'{path}\t200\t3\textra','',f'no-slash\t200\t3',f'/bad\x00path\t200\t3'])
  elif r.random()<.01:line=f'{path}\t00500\t18446744073709551615'
  if r.random()<.15:line+='\r'
  lines.append(line)
 text='\n'.join(lines)
 if r.random()<.8:text+='\n'
 return text

def main():
 rows=[]
 # These are independent random realizations within common synthetic profile families.
 for p,profile in enumerate(PROFILES):
  for j in range(10):
   split='train' if j<4 else 'validation' if j<7 else 'test'
   seed=88481+p*10007+j*997
   group=hashlib.sha256(f'group:{seed}'.encode()).hexdigest()[:12]
   for n in (512,8192):
    ident=hashlib.sha256(f'case:{seed}:{n}'.encode()).hexdigest()[:16]
    rows.append({'id':ident,'group':group,'split':split,'tags':[profile,'small' if n==512 else 'large'],'input':{'text':workload(seed,n,profile)},'metadata':{'origin':'synthetic independent seeded log realization','profile':profile,'rows':n,'related_cases':'small and large use same source seed'}})
 path=ROOT/'suite/cases.jsonl';path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
 print(json.dumps({'cases':len(rows),'groups':60,'train_groups':24,'validation_groups':18,'test_groups':18,'cases_sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2))
if __name__=='__main__':main()
