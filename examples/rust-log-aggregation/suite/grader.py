import json,math,statistics,sys
from oracle import oracle
req=json.load(sys.stdin); output=req['output']; expected=oracle(req['input']['text']); actual=output['answer']
correct=float(actual==expected and output['reference_answer']==expected)
ns=statistics.median(output['samples_ns'])
if not math.isfinite(ns) or ns<=0:raise ValueError('Invalid fixed-driver timing')
json.dump({'metrics':{'correctness':correct,'log_ratio':statistics.mean(math.log(statistics.mean(output['samples_ns'][i:i+2])/statistics.mean(output['reference_samples_ns'][i:i+2])) for i in range(0,8,2)),'kernel_ns':ns,'external_process_ns':output['external_process_ns']},'explanation':'Exact independent Python aggregation match' if correct else 'Wrong aggregates or invalid-row count','model':'python-independent-oracle-v1','usage':{'cost_usd':0}},sys.stdout)
