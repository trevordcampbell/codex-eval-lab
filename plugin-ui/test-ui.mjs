import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { JSDOM, VirtualConsole } from 'jsdom';
import { AppBridge } from '@modelcontextprotocol/ext-apps/app-bridge';
const root = new URL('..', import.meta.url).pathname;
const fixture = JSON.parse(execFileSync('python', ['-c', `
import json
from copy import deepcopy
from tests.review_helpers import review_fixture, calibration_args
from codex_eval_lab.calibration import create_judge_outputs
from codex_eval_lab.review import create_packet
from codex_eval_lab.review_ui import render_standalone_review, render_calibration_review, render_mcp_review, review_payload
f=review_fixture()
rows=deepcopy(f['outputs']['rows'])
for row in rows:
 if row['trace_id']=='validation-fail-0': row['status']='pass'; row['reason']='Synthetic missed-failure reason'
 if row['trace_id']=='validation-pass-0': row['status']='fail'; row['reason']='Synthetic false-alarm reason'
f['outputs']=create_judge_outputs(f['packet'],f['rubric'],f['judge_config'],rows)
other_traces=[{k: v for k, v in row.items() if k != 'sha256'} for row in f['packet']['traces']]
for row in other_traces:
 row['id']='second-'+row['id']; row['group']='second-'+row['group']
other=create_packet(other_traces,reviewer='Synthetic test author',source={'kind':'synthetic','reference':'test-ui.mjs'})
print(json.dumps({'review':render_standalone_review(f['packet']),'labels':render_standalone_review(f['packet'],f['rubric']),'calibration':render_calibration_review(**calibration_args(f)),'app':render_mcp_review(),'appPayload':review_payload(f['packet'],mode='app'),'otherPayload':review_payload(other,mode='app')}))
`], {cwd:root, env:{...process.env,PYTHONPATH:root+'/src'},encoding:'utf8'}));
function view(kind, parent) {
  const downloads=[]; const errors=[];
  const vc=new VirtualConsole();vc.on('jsdomError',(e)=>errors.push(e.message));
  const dom=new JSDOM(fixture[kind],{runScripts:'dangerously',url:'file:///review.html',virtualConsole:vc,pretendToBeVisual:true,beforeParse(win){
    if(parent)Object.defineProperty(win,'parent',{value:parent});
    win.ResizeObserver=class{observe(){}disconnect(){}};
    win.Blob=class{constructor(parts){this.parts=parts;}};
    win.URL.createObjectURL=(blob)=>{downloads.push(JSON.parse(blob.parts.join('')));return'blob:test';};win.URL.revokeObjectURL=()=>{};
    win.HTMLAnchorElement.prototype.click=function(){};
    win.confirm=()=>true;
  }});
  const d=dom.window.document;
  const value=(id,val,event='input')=>{d.getElementById(id).value=val;d.getElementById(id).dispatchEvent(new dom.window.Event(event,{bubbles:true}));};
  const radio=(val)=>{const el=d.querySelector(`input[name=verdict][value=${val}]`);el.checked=true;el.dispatchEvent(new dom.window.Event('change',{bubbles:true}));};
  return{dom,d,downloads,errors,value,radio};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function beginImport(v, draft, {text=async()=>JSON.stringify(draft), size=JSON.stringify(draft).length}={}) {
 const input=v.d.getElementById('import');
 Object.defineProperty(input,'files',{configurable:true,value:[{name:'synthetic.draft.json',size,text}]});
 input.dispatchEvent(new v.dom.window.Event('change',{bubbles:true}));
}
async function restore(v, draft, options) {beginImport(v,draft,options);await settle();}
function draftFor(payload=fixture.appPayload, rationale='Restored synthetic rationale') {
 const row=payload.packet.traces[0];
 return {schema_version:1,kind:'annotation_draft',packet_sha256:payload.packet.packet_sha256,reviewer:'Synthetic UI test reviewer',
  annotations:[{trace_id:row.id,trace_sha256:row.trace_sha256,verdict:'pass',rationale,failure_modes:[]}]};
}
function verifyCLIEnvelope(draft) {
 // Use the real CLI draft parser without making a human attestation or sealing
 // an artifact. All labels in these tests are explicitly synthetic fixtures.
 const count=execFileSync('python',['-c',`
import json, sys, tempfile
from pathlib import Path
from tests.review_helpers import review_fixture
from codex_eval_lab.review_cli import _draft
draft=json.load(sys.stdin)
f=review_fixture()
field='labels' if draft['kind']=='criterion_labels_draft' else 'annotations'
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'synthetic-draft.json'
 path.write_text(json.dumps(draft),encoding='utf-8')
 rows=_draft(path,field,f['packet'],draft['reviewer'],f['rubric'] if field=='labels' else None)
 print(len(rows))
`],{cwd:root,env:{...process.env,PYTHONPATH:root+'/src'},input:JSON.stringify(draft),encoding:'utf8'});
 assert.equal(Number(count),draft.labels?.length??draft.annotations.length);
}
test('blind trace review initializes without judge decisions or validation data',()=>{
 const v=view('review');assert.equal(v.d.querySelectorAll('.trace-item').length,2);assert.match(v.d.getElementById('trace-title').textContent,/tuning/);assert.equal(v.d.getElementById('partition').options.length,2);assert.equal(v.d.querySelector('input[name=verdict]:checked'),null);assert.equal(v.d.getElementById('judge-verdict'),null);assert.deepEqual(v.errors,[]);v.dom.window.close();
});
test('navigation and filters preserve actual entered annotations, draft export matches CLI',()=>{
 const v=view('review');v.value('reviewer','Synthetic UI test reviewer');v.radio('pass');v.value('rationale','Synthetic pass rationale');v.d.getElementById('next').click();v.radio('fail');v.value('rationale','Synthetic failure rationale');v.value('failure-modes','unsupported claim');v.value('filter','pass','change');assert.equal(v.d.querySelectorAll('.trace-item').length,1);assert.equal(v.d.getElementById('rationale').value,'Synthetic pass rationale');v.value('filter','all','change');v.d.getElementById('export').click();assert.equal(v.downloads.length,1);const draft=v.downloads[0];assert.equal(draft.kind,'annotation_draft');assert.equal(draft.annotations.length,2);assert.equal(draft.annotations[1].failure_modes[0],'unsupported claim');assert.equal(draft.provenance,undefined);assert.match(draft.packet_sha256,/^[a-f0-9]{64}$/);assert.match(v.d.getElementById('save-status').textContent,/download requested/);assert.deepEqual(v.errors,[]);v.dom.window.close();
});
test('criterion switching never saves one criterion under another',()=>{
 const v=view('labels');v.value('reviewer','Synthetic UI reviewer');v.radio('pass');v.value('rationale','Grounded judgment');v.value('criterion','format','change');assert.equal(v.d.getElementById('rationale').value,'');assert.equal(v.d.querySelector('input[name=verdict]:checked'),null);v.radio('uncertain');v.value('rationale','Format uncertain');v.value('criterion','grounded','change');assert.equal(v.d.getElementById('rationale').value,'Grounded judgment');v.d.getElementById('export').click();const draft=v.downloads[0];assert.equal(draft.kind,'criterion_labels_draft');assert.equal(draft.labels.length,2);assert.equal(draft.labels.find((x)=>x.criterion_id==='format').verdict,'uncertain');assert.match(draft.rubric_sha256,/^[a-f0-9]{64}$/);assert.deepEqual(v.errors,[]);v.dom.window.close();
});
test('calibration viewer shows actual missed calls with separate human/judge reasons',()=>{
 const v=view('calibration');v.value('error-filter','missed_failure','change');assert.equal(v.d.getElementById('trace-title').textContent,'validation-fail-0');assert.equal(v.d.getElementById('human-verdict').textContent,'fail');assert.equal(v.d.getElementById('judge-verdict').textContent,'pass');assert.equal(v.d.getElementById('judge-reason').textContent,'Synthetic missed-failure reason');assert.match(v.d.getElementById('output').textContent,/fail fixture/);v.value('error-filter','false_alarm','change');assert.equal(v.d.getElementById('trace-title').textContent,'validation-pass-0');assert.equal(v.d.getElementById('human-verdict').textContent,'pass');assert.equal(v.d.getElementById('judge-verdict').textContent,'fail');assert.match(v.d.getElementById('intervals').textContent,/Group-level bounds/);assert.deepEqual(v.errors,[]);v.dom.window.close();
});
test('empty search clears previous evidence, preserves drafts, and gives useful state',()=>{
 const v=view('review');v.radio('pass');v.value('rationale','kept');v.value('search','no-match');assert.equal(v.d.getElementById('trace-title').textContent,'');assert.equal(v.d.getElementById('review-fields').disabled,true);assert.match(v.d.getElementById('empty').textContent,/No traces match/);v.value('search','');assert.equal(v.d.getElementById('rationale').value,'kept');v.dom.window.close();
});
async function appView(oncalltool) {
 const host=new JSDOM('',{url:'https://synthetic-host.invalid'});
 const bridge=new AppBridge(null,{name:'Synthetic SDK test host',version:'1.0.0'},{serverTools:{}});
 let v;
 // The released host protocol talks to the bundled browser protocol. Only the
 // in-process window delivery is synthetic; this does not claim native rendering.
 const transport={
  async start(){},
  async send(message){const data=structuredClone(message);queueMicrotask(()=>v.dom.window.dispatchEvent(new v.dom.window.MessageEvent('message',{data,source:host.window})));},
  async close(){this.onclose?.();}
 };
 const initialized=new Promise(resolve=>{bridge.oninitialized=resolve;});
 if(oncalltool)bridge.oncalltool=oncalltool;
 host.window.postMessage=(message)=>{const data=structuredClone(message);queueMicrotask(()=>transport.onmessage?.(data));};
 await bridge.connect(transport);
 v=view('app',host.window);
 await initialized;
 const settle=()=>new Promise(resolve=>setImmediate(resolve));
 return {...v,bridge,settle,
  async receive(data){await bridge.sendToolResult({content:[],_meta:{'codex-eval-lab/review':data}});await settle();},
  async close(){await bridge.close();v.dom.window.close();host.window.close();}
 };
}
test('released MCP Apps bridge initializes the bundled app and delivers tuning-only tool metadata', {timeout:5000}, async()=>{
 const v=await appView();
 try{
  assert.equal(v.bridge.getAppVersion().name,'Codex Eval Lab Review');
  await v.bridge.sendToolInput({arguments:{packet_id:'synthetic-packet'}});
  await v.receive(fixture.appPayload);
  assert.equal(v.d.querySelectorAll('.trace-item').length,2);
  assert.match(v.d.getElementById('trace-title').textContent,/tuning/);
  assert.equal(v.d.getElementById('partition').options.length,2);
  assert.equal(v.d.getElementById('judge-verdict'),null);
  assert.doesNotMatch(v.d.getElementById('save-status').textContent,/did not connect/);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});
test('empty entrypoint shows scoped packet chooser, handles empty scope, and opens through the released SDK', {timeout:5000}, async()=>{
 const calls=[];
 const v=await appView(async(params)=>{calls.push(params);return{content:[],_meta:{'codex-eval-lab/review':fixture.appPayload}};});
 try{
  await v.bridge.sendToolInput({arguments:{}});
  await v.receive({mode:'mcp',catalog:[],packet:null,rubric:null});
  assert.equal(v.d.getElementById('packet-picker').hidden,false);
  assert.equal(v.d.getElementById('open-packet').disabled,true);
  assert.match(v.d.getElementById('packet-picker-note').textContent,/No review packets are registered/);
  assert.equal(v.d.getElementById('export').disabled,true);
  await v.receive({mode:'mcp',catalog:[{packet_id:'synthetic-packet',tuning_trace_count:2}],packet:null,rubric:null});
  assert.equal(v.d.querySelectorAll('.trace-item').length,0);
  assert.equal(v.d.getElementById('open-packet').disabled,false);
  v.d.getElementById('open-packet').click();v.d.getElementById('open-packet').click();
  await v.settle();
  assert.equal(calls.length,1);
  assert.equal(calls[0].name,'open_review');
  assert.deepEqual(calls[0].arguments,{packet_id:'synthetic-packet'});
  assert.equal(v.d.querySelectorAll('.trace-item').length,2);
  assert.equal(v.d.getElementById('open-packet').disabled,false);
  assert.equal(v.d.getElementById('judge-verdict'),null);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});
test('packet switching preserves drafts on cancellation, server failure, unsolicited data, and edits while loading', {timeout:5000}, async()=>{
 let calls=0, response, resolveResponse;
 const v=await appView(async()=>{calls++;return response;});
 try{
  await v.bridge.sendToolInput({arguments:{}});
  await v.receive({...fixture.appPayload,catalog:[{packet_id:'synthetic-a',tuning_trace_count:2},{packet_id:'synthetic-b',tuning_trace_count:2}]});
  v.radio('pass');v.value('rationale','Keep this judgment');
  v.value('packet-select','synthetic-b','change');
  v.dom.window.confirm=()=>false;v.d.getElementById('open-packet').click();await v.settle();
  assert.equal(calls,0);assert.equal(v.d.getElementById('rationale').value,'Keep this judgment');
  await v.receive(fixture.appPayload);
  assert.equal(v.d.getElementById('rationale').value,'Keep this judgment');
  assert.match(v.d.getElementById('save-status').textContent,/new packet arrived/);
  v.dom.window.confirm=()=>true;response={isError:true,content:[]};
  v.d.getElementById('open-packet').click();await v.settle();
  assert.equal(calls,1);assert.equal(v.d.getElementById('rationale').value,'Keep this judgment');
  assert.match(v.d.getElementById('save-status').textContent,/current draft is preserved/);
  response=new Promise(resolve=>{resolveResponse=resolve;});
  v.d.getElementById('open-packet').click();await v.settle();
  v.value('rationale','Edited while packet was loading');
  resolveResponse({content:[],_meta:{'codex-eval-lab/review':fixture.appPayload}});await v.settle();
  assert.equal(calls,2);assert.equal(v.d.getElementById('rationale').value,'Edited while packet was loading');
  assert.match(v.d.getElementById('save-status').textContent,/edited this draft while waiting/);
  response={content:[],_meta:{'codex-eval-lab/review':fixture.appPayload}};
  v.d.getElementById('open-packet').click();await v.settle();
  assert.equal(calls,3);assert.equal(v.d.getElementById('rationale').value,'');
  assert.equal(v.d.querySelector('input[name=verdict]:checked'),null);
  assert.equal(v.d.getElementById('open-packet').disabled,false);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});

test('annotation export restores in a fresh offline page and uses the real CLI draft envelope', async()=>{
 const source=view('review'), target=view('review');
 try{
  source.value('reviewer','Synthetic UI test reviewer');source.radio('pass');source.value('rationale','Synthetic first judgment');
  source.d.getElementById('next').click();source.radio('fail');source.value('rationale','Synthetic second judgment');source.value('failure-modes','unsupported claim');
  source.d.getElementById('export').click();
  const draft=source.downloads[0];verifyCLIEnvelope(draft);
  await restore(target,draft);
  assert.equal(target.d.getElementById('reviewer').value,draft.reviewer);
  assert.equal(target.d.getElementById('rationale').value,'Synthetic first judgment');
  target.d.getElementById('next').click();
  assert.equal(target.d.getElementById('rationale').value,'Synthetic second judgment');
  assert.equal(target.d.getElementById('failure-modes').value,'unsupported claim');
  target.d.getElementById('export').click();
  assert.deepEqual(target.downloads[0],draft);
  assert.deepEqual([...source.errors,...target.errors],[]);
 }finally{source.dom.window.close();target.dom.window.close();}
});
test('criterion draft round trip keeps criterion bindings and checks the frozen rubric', async()=>{
 const source=view('labels'),target=view('labels');
 try{
  source.value('reviewer','Synthetic criterion reviewer');source.radio('pass');source.value('rationale','Synthetic grounded judgment');
  source.value('criterion','format','change');source.radio('uncertain');source.value('rationale','Synthetic format uncertainty');
  source.d.getElementById('export').click();const draft=source.downloads[0];verifyCLIEnvelope(draft);
  await restore(target,draft);assert.equal(target.d.getElementById('rationale').value,'Synthetic grounded judgment');
  target.value('criterion','format','change');assert.equal(target.d.getElementById('rationale').value,'Synthetic format uncertainty');
  assert.equal(target.d.querySelector('input[name=verdict]:checked').value,'uncertain');
  target.d.getElementById('export').click();assert.deepEqual(target.downloads[0],draft);
  const invalid={...draft,rubric_sha256:'0'.repeat(64)};await restore(target,invalid);
  assert.match(target.d.getElementById('save-status').textContent,/different packet or rubric/);
  assert.equal(target.d.getElementById('rationale').value,'Synthetic format uncertainty');
  assert.deepEqual([...source.errors,...target.errors],[]);
 }finally{source.dom.window.close();target.dom.window.close();}
});
test('invalid imports and canceled replacement preserve the current draft atomically', async()=>{
 const v=view('review');
 try{
  v.value('reviewer','Current synthetic reviewer');v.radio('pass');v.value('rationale','Keep my current draft');
  const draft=draftFor();
  const invalids=[
   {...draft,packet_sha256:'0'.repeat(64)},
   {...draft,schema_version:2},
   {...draft,annotations:[...draft.annotations,...draft.annotations]},
   {...draft,annotations:[{...draft.annotations[0],trace_sha256:'0'.repeat(64)}]},
   {...draft,annotations:[{...draft.annotations[0],failure_modes:'not an array'}]},
  ];
  for(const invalid of invalids){await restore(v,invalid);assert.match(v.d.getElementById('save-status').textContent,/Import rejected/);assert.equal(v.d.getElementById('rationale').value,'Keep my current draft');}
  await restore(v,draft,{text:async()=>'{broken json'});assert.match(v.d.getElementById('save-status').textContent,/Import rejected/);
  await restore(v,draft,{size:5*1024*1024+1});assert.match(v.d.getElementById('save-status').textContent,/5 MiB limit/);
  v.dom.window.confirm=()=>false;await restore(v,draft);
  assert.equal(v.d.getElementById('rationale').value,'Keep my current draft');assert.equal(v.d.getElementById('reviewer').value,'Current synthetic reviewer');
  v.dom.window.confirm=()=>true;await restore(v,draft);
  assert.equal(v.d.getElementById('rationale').value,draft.annotations[0].rationale);
  assert.match(v.d.getElementById('save-status').textContent,/restored locally/);
  assert.deepEqual(v.errors,[]);
 }finally{v.dom.window.close();}
});
test('a slow older import cannot overwrite a newer restored draft',async()=>{
 const v=view('review');let resolveRead;
 try{
  const older=draftFor(fixture.appPayload,'Older draft'), newer=draftFor(fixture.appPayload,'Newer draft');
  beginImport(v,older,{text:()=>new Promise(resolve=>{resolveRead=resolve;})});
  await restore(v,newer);resolveRead(JSON.stringify(older));await settle();
  assert.equal(v.d.getElementById('rationale').value,'Newer draft');
  assert.match(v.d.getElementById('save-status').textContent,/restored locally/);
  assert.deepEqual(v.errors,[]);
 }finally{v.dom.window.close();}
});
test('criterion and draft changes respect the selected verdict filter',async()=>{
 const v=view('labels');
 try{
  v.radio('pass');v.value('rationale','Synthetic grounded judgment');v.value('filter','pass','change');
  v.value('criterion','format','change');
  assert.equal(v.d.querySelectorAll('.trace-item').length,0);assert.equal(v.d.getElementById('review-fields').disabled,true);assert.equal(v.d.getElementById('output').textContent,'');
  v.value('criterion','grounded','change');assert.equal(v.d.getElementById('rationale').value,'Synthetic grounded judgment');
  assert.deepEqual(v.errors,[]);
 }finally{v.dom.window.close();}
 const review=view('review');
 try{
  review.value('filter','fail','change');await restore(review,draftFor());
  assert.equal(review.d.querySelectorAll('.trace-item').length,0);assert.equal(review.d.getElementById('review-fields').disabled,true);
  review.value('filter','pass','change');assert.equal(review.d.getElementById('rationale').value,'Restored synthetic rationale');
  assert.deepEqual(review.errors,[]);
 }finally{review.dom.window.close();}
});
test('exported app drafts survive a real packet switch and restore without another server call', {timeout:5000}, async()=>{
 const calls=[];
 const payloads={'synthetic-a':fixture.appPayload,'synthetic-b':fixture.otherPayload};
 const catalog=Object.keys(payloads).map(packet_id=>({packet_id,tuning_trace_count:2}));
 const v=await appView(async(params)=>{calls.push(params);return{content:[],_meta:{'codex-eval-lab/review':{...payloads[params.arguments.packet_id],catalog}}};});
 try{
  await v.receive({mode:'mcp',catalog,packet:null,rubric:null});
  v.d.getElementById('open-packet').click();await v.settle();
  v.value('reviewer','Synthetic app reviewer');v.radio('pass');v.value('rationale','First packet annotation');
  v.d.getElementById('export').click();const draft=v.downloads[0];verifyCLIEnvelope(draft);
  let confirmations=0;v.dom.window.confirm=()=>{confirmations++;return false;};
  v.value('packet-select','synthetic-b','change');v.d.getElementById('open-packet').click();await v.settle();
  assert.equal(confirmations,0);assert.equal(v.d.getElementById('packet-id').textContent,fixture.otherPayload.packet.packet_sha256);
  assert.match(v.d.getElementById('trace-title').textContent,/^second-/);assert.equal(v.d.getElementById('rationale').value,'');
  await restore(v,draft);assert.match(v.d.getElementById('save-status').textContent,/different packet or rubric/);
  v.value('packet-select','synthetic-a','change');v.d.getElementById('open-packet').click();await v.settle();
  await restore(v,draft);assert.equal(v.d.getElementById('rationale').value,'First packet annotation');
  assert.equal(calls.length,3);assert.ok(calls.every(call=>call.name==='open_review'));
  v.d.getElementById('export').click();assert.deepEqual(v.downloads[1],draft);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});
test('an import started before a new packet arrives cannot restore stale state', {timeout:5000}, async()=>{
 const v=await appView();let resolveRead;
 try{
  await v.receive(fixture.appPayload);
  const draft=draftFor();beginImport(v,draft,{text:()=>new Promise(resolve=>{resolveRead=resolve;})});
  // Even reopening the same packet is a newer view, so a stale file read must stop.
  await v.receive(fixture.appPayload);resolveRead(JSON.stringify(draft));await v.settle();
  assert.equal(v.d.getElementById('rationale').value,'');
  assert.match(v.d.getElementById('save-status').textContent,/active packet changed/);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});
test('empty packet and empty chooser clear prior evidence and queue entries', {timeout:5000}, async()=>{
 const v=await appView();
 try{
  await v.receive(fixture.appPayload);assert.equal(v.d.querySelectorAll('.trace-item').length,2);
  await v.receive({...fixture.appPayload,packet:{...fixture.appPayload.packet,traces:[]}});
  assert.equal(v.d.querySelectorAll('.trace-item').length,0);assert.equal(v.d.getElementById('output').textContent,'');assert.equal(v.d.getElementById('review-fields').disabled,true);
  await v.receive(fixture.appPayload);await v.receive({mode:'mcp',catalog:[],packet:null,rubric:null});
  assert.equal(v.d.querySelectorAll('.trace-item').length,0);assert.equal(v.d.getElementById('packet-id').textContent,'');assert.equal(v.d.getElementById('export').disabled,true);
  assert.deepEqual(v.errors,[]);
 }finally{await v.close();}
});
test('calibration criterion, partition, search and navigation preserve independent decisions',()=>{
 const v=view('calibration');
 try{
  v.value('criterion','format','change');v.value('error-filter','missed_failure','change');
  assert.equal(v.d.getElementById('trace-title').textContent,'validation-fail-0');assert.equal(v.d.getElementById('human-verdict').textContent,'fail');assert.equal(v.d.getElementById('judge-verdict').textContent,'pass');
  v.value('partition','tuning','change');assert.equal(v.d.querySelectorAll('.trace-item').length,0);assert.equal(v.d.getElementById('judge-reason').textContent,'');
  v.value('error-filter','agreement','change');assert.equal(v.d.querySelectorAll('.trace-item').length,2);assert.match(v.d.getElementById('rates').textContent,/^Tuning/);
  const first=v.d.getElementById('trace-title').textContent;v.d.getElementById('next').click();assert.notEqual(v.d.getElementById('trace-title').textContent,first);v.d.getElementById('previous').click();assert.equal(v.d.getElementById('trace-title').textContent,first);
  v.value('search','no-synthetic-trace');assert.equal(v.d.querySelectorAll('.trace-item').length,0);
  for(const id of ['trace-title','input','output','transcript','human-verdict','human-reason','judge-verdict','judge-reason'])assert.equal(v.d.getElementById(id).textContent,'');
  v.value('search','');v.value('partition','validation','change');v.value('error-filter','unresolved','change');assert.equal(v.d.querySelectorAll('.trace-item').length,0);
  v.value('error-filter','all','change');assert.equal(v.d.querySelectorAll('.trace-item').length,4);
  assert.deepEqual(v.errors,[]);
 }finally{v.dom.window.close();}
});
