// Untrusted trace content is rendered ONLY with textContent; no remote assets.
export function mountReview(initial = null, {loadPacket} = {}) {
  const $ = (id) => document.getElementById(id);
  let packet = null, rubric = null, traces = [], selected = null, dirty = false;
  let catalog = [], loading = false, loadSequence = 0, editRevision = 0, importSequence = 0, packetRevision = 0;
  const annotations = new Map();
  const values = ['pass', 'fail', 'uncertain'];
  const show = (id, value) => { $(id).textContent = value; };
  const format = (value) => typeof value === 'string' ? value : JSON.stringify(value ?? null, null, 2);
  const criterion = () => rubric?.criteria.find((item) => item.id === $('criterion').value);
  const key = (row) => rubric ? `${row.id}\u0000${$('criterion').value}` : row.id;
  const active = () => traces.find((row) => row.id === selected);
  function save() {
    const row = active();
    if (!row) return;
    const verdict = document.querySelector('input[name=verdict]:checked')?.value;
    const rationale = $('rationale').value;
    const modes = $('failure-modes').value.split(',').map((x) => x.trim()).filter(Boolean);
    if (verdict || rationale || modes.length) {
      annotations.set(key(row), {trace_id: row.id, trace_sha256: row.trace_sha256,
        ...(rubric ? {criterion_id: $('criterion').value} : {failure_modes: [...new Set(modes)]}),
        verdict: verdict || null, rationale});
    } else annotations.delete(key(row));
  }
  function filtered() {
    const search = $('search').value.trim().toLowerCase();
    const filter = $('filter').value;
    const partition = $('partition').value;
    return traces.filter((row) => (!search || row.id.toLowerCase().includes(search)) &&
      (!partition || row.partition === partition) &&
      (filter === 'all' || (filter === 'unreviewed' ? !annotations.get(key(row))?.verdict : annotations.get(key(row))?.verdict === filter)));
  }
  function renderList() {
    const rows = filtered();
    $('trace-list').replaceChildren();
    for (const row of rows) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'trace-item';
      button.textContent = `${annotations.get(key(row))?.verdict || '○'} · ${row.id}`;
      button.setAttribute('aria-current', String(row.id === selected));
      button.addEventListener('click', () => select(row.id));
      $('trace-list').append(button);
    }
    show('progress', `${[...annotations.values()].filter((x) => x.verdict).length} marked · ${traces.length}${rubric ? ' traces × '+rubric.criteria.length+' criteria' : ' traces'} · ${rows.length} shown`);
    show('empty', rows.length ? '' : 'No traces match this filter. Existing annotations are preserved.');
    return rows;
  }
  function select(id) {
    save(); selected = id;
    const row = active();
    $('review-fields').disabled = !row;
    if (!row) {for(const id of ['trace-title','trace-context','input','output','transcript','criterion-detail'])show(id,'');$('rationale').value='';$('failure-modes').value='';document.querySelectorAll('input[name=verdict]').forEach((el)=>{el.checked=false;});renderList();return;}
    const annotation = annotations.get(key(row));
    show('trace-title', row.id); show('trace-context', `${row.partition} · group ${row.group}`);
    show('input', format(row.input)); show('output', format(row.output)); show('transcript', format(row.trace));
    $('rationale').value = annotation?.rationale || '';
    $('failure-modes').value = (annotation?.failure_modes || []).join(', ');
    document.querySelectorAll('input[name=verdict]').forEach((el) => {el.checked = el.value === annotation?.verdict;});
    const item = criterion();
    show('criterion-detail', item ? `${item.description}\nPASS: ${item.pass_when}\nFAIL: ${item.fail_when}` : 'Review what happened before turning recurring failures into atomic criteria.');
    renderList();
  }
  function applyFilter() {save(); const rows = renderList(); if (!rows.some((r) => r.id === selected)) select(rows[0]?.id || null);}
  function changed() {if(!packet)return;dirty = true;editRevision++; save(); renderList(); show('save-status', 'Unsaved changes · export JSON before closing');}
  for (const id of ['rationale', 'failure-modes', 'reviewer']) $(id).addEventListener('input', changed);
  document.querySelectorAll('input[name=verdict]').forEach((el) => el.addEventListener('change', changed));
  for (const id of ['search', 'filter', 'partition']) $(id).addEventListener(id === 'search' ? 'input' : 'change', applyFilter);
  $('criterion').addEventListener('change', () => {
    // The old criterion was saved on every edit; do not save its visible fields under the new one.
    const oldSelected = selected, rows = filtered();
    selected = null; select(rows.some((row)=>row.id===oldSelected) ? oldSelected : rows[0]?.id || null);
  });
  function navigate(offset) {save(); const rows=filtered(); if (!rows.length) return; const i=rows.findIndex((r)=>r.id===selected); select(rows[(i+offset+rows.length)%rows.length].id);}
  $('previous').addEventListener('click',()=>navigate(-1)); $('next').addEventListener('click',()=>navigate(1));
  document.addEventListener('keydown',(e)=>{if(e.altKey && ['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();navigate(e.key==='ArrowLeft'?-1:1);}});
  window.addEventListener('beforeunload',(event)=>{if(dirty){event.preventDefault();event.returnValue='';}});
  $('export').addEventListener('click',()=>{
    save();
    const reviewer=$('reviewer').value.trim();
    if(!reviewer){show('save-status','Enter your reviewer name before exporting');$('reviewer').focus();return;}
    const rows=[...annotations.values()];
    if(!rows.length || rows.some((r)=>!values.includes(r.verdict)||!r.rationale.trim())) {show('save-status','Every started annotation needs a verdict and rationale. Unstarted traces can remain for a later draft.');return;}
    if(!rubric && rows.some((r)=>(r.verdict==='fail'&&!r.failure_modes.length)||(r.verdict==='pass'&&r.failure_modes.length))){show('save-status','Fail judgments need at least one failure mode; pass judgments must have none.');return;}
    const payload={schema_version:1, kind:rubric?'criterion_labels_draft':'annotation_draft', packet_sha256:packet.packet_sha256, reviewer,
      ...(rubric?{rubric_sha256:rubric.rubric_sha256,labels:rows}:{annotations:rows})};
    const blob=new Blob([JSON.stringify(payload,null,2)+'\n'],{type:'application/json'});
    const link=document.createElement('a'); const url=URL.createObjectURL(blob);
    link.href=url;link.download=rubric?'criterion-labels.draft.json':'human-review.draft.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);dirty=false;
    show('save-status','Draft download requested. Finish all tuning annotations before sealing with the CLI. This is not an approval.');
  });
  $('import').addEventListener('change',async(event)=>{
    const file=event.target.files[0];if(!file||!packet)return;
    const request=++importSequence, packetAtStart=packetRevision;
    try {
      if(file.size>5*1024*1024)throw Error('Draft exceeds the 5 MiB limit');
      const obj=JSON.parse(await file.text());
      // File reads are asynchronous. An older import must not replace a newer
      // import or a packet that arrived while this file was being read.
      if(request!==importSequence)return;
      if(packetRevision!==packetAtStart)throw Error('The active packet changed while reading this draft; choose the file again');
      if(obj.packet_sha256!==packet.packet_sha256 || (rubric && obj.rubric_sha256!==rubric.rubric_sha256))throw Error('Draft belongs to a different packet or rubric');
      if(obj.schema_version!==1||obj.kind!==(rubric?'criterion_labels_draft':'annotation_draft'))throw Error('Unsupported draft schema');
      const rows=rubric?obj.labels:obj.annotations;if(!Array.isArray(rows))throw Error('Missing annotations');
      const restored=new Map();
      for(const row of rows){
        const trace=traces.find((t)=>t.id===row.trace_id);
        if(!trace||trace.trace_sha256!==row.trace_sha256||!values.includes(row.verdict)||typeof row.rationale!=='string')throw Error('Invalid trace, digest, verdict, or rationale');
        if(rubric&&!rubric.criteria.some((c)=>c.id===row.criterion_id))throw Error('Unknown criterion');
        if(!rubric&&(!Array.isArray(row.failure_modes)||!row.failure_modes.every((m)=>typeof m==='string')))throw Error('Invalid failure modes');
        const k=rubric?`${row.trace_id}\u0000${row.criterion_id}`:row.trace_id;
        if(restored.has(k))throw Error('Duplicate annotation');restored.set(k,row);
      }
      if(dirty&&!window.confirm('Replace unsaved annotations with this draft?'))return;
      editRevision++;annotations.clear();for(const [k,row]of restored)annotations.set(k,row);
      $('reviewer').value=typeof obj.reviewer==='string'?obj.reviewer:'';
      const id=selected, visible=filtered();selected=null;
      select(visible.some((row)=>row.id===id) ? id : visible[0]?.id || null);
      dirty=false;show('save-status','Draft restored locally; nothing sent to a server');
    }catch(error){if(request===importSequence)show('save-status',`Import rejected: ${error.message}`);}
    finally{if(request===importSequence)event.target.value='';}
  });
  function updatePicker() {
    $('packet-picker').hidden=!loadPacket;
    $('packet-select').disabled=loading||!catalog.length;
    $('open-packet').disabled=loading||!catalog.length;
    $('open-packet').textContent=loading?'Opening…':'Open packet';
  }
  $('open-packet').addEventListener('click',async()=>{
    if(loading||!loadPacket||!$('packet-select').value)return;
    if(dirty&&!window.confirm('Discard unsaved annotations and open another packet? Export your JSON first if you want to keep them.'))return;
    const revision=editRevision, request=++loadSequence, id=$('packet-select').value;
    loading=true;updatePicker();show('save-status','Loading the selected tuning packet…');
    try{
      const data=await loadPacket(id);
      if(request!==loadSequence)return;
      if(revision!==editRevision){show('save-status','The packet loaded, but you edited this draft while waiting. Export your annotations before opening another packet.');return;}
      if(!data?.packet||!Array.isArray(data.packet.traces))throw Error('The server did not return a review packet');
      receive(data,{replaceDirty:true});
    }catch(error){if(request===loadSequence)show('save-status',`Could not open packet: ${error.message}. Your current draft is preserved.`);}
    finally{if(request===loadSequence){loading=false;updatePicker();}}
  });
  function receive(data, {replaceDirty=false} = {}) {
    if(!data?.packet&&!Array.isArray(data?.catalog)) {show('save-status','No review packet available');return;}
    if(dirty&&!replaceDirty){show('save-status','A new packet arrived. Export your current annotations, then reopen the review.');return;}
    if(data.packet&&!Array.isArray(data.packet.traces)){show('save-status','Invalid review packet');return;}
    ++loadSequence;++packetRevision;loading=false;dirty=false;
    if(Array.isArray(data.catalog)){
      catalog=data.catalog.filter((item)=>typeof item?.packet_id==='string'&&Number.isSafeInteger(item.tuning_trace_count)&&item.tuning_trace_count>=0);
      const previous=$('packet-select').value;
      $('packet-select').replaceChildren();
      for(const item of catalog){const option=document.createElement('option');option.value=item.packet_id;option.textContent=`${item.packet_id} · ${item.tuning_trace_count} tuning traces`;$('packet-select').append(option);}
      if(catalog.some((item)=>item.packet_id===previous))$('packet-select').value=previous;
      show('packet-picker-note',catalog.length?'Choose an explicitly registered packet. Only tuning traces are available here.':'No review packets are registered. Start the local server with an approved packet path, then reopen Trace Review.');
    }
    updatePicker();
    if(!data.packet){
      packet=null;rubric=null;traces=[];selected=null;annotations.clear();$('export').disabled=true;
      select(null);show('packet-id','');show('mode','MCP Apps · local read-only server');
      show('scope-note',catalog.length?'Select a registered packet to begin human review':'No registered review packets');
      show('empty',catalog.length?'Select a packet above to see its tuning traces.':'No review packets are available in this server scope.');
      show('save-status',catalog.length?'No labels are created until you enter them.':'Register an approved packet with the local server to begin.');return;
    }
    packet=data.packet;rubric=data.rubric||null;
    traces=packet.traces;annotations.clear();selected=null;
    $('search').value='';$('filter').value='all';
    show('packet-id', packet.packet_sha256 || '');
    show('mode', data.mode==='standalone' ? 'Offline file · no network' : 'MCP Apps · local read-only server');
    $('criterion-wrap').hidden=!rubric;$('modes-wrap').hidden=!!rubric;
    $('criterion').replaceChildren();
    for(const c of rubric?.criteria||[]){const option=document.createElement('option');option.value=c.id;option.textContent=c.id;$('criterion').append(option);}
    $('partition').replaceChildren();
    for(const [value,label]of [['','All visible partitions'],['tuning','Tuning'],['validation','Calibration validation']]){
      if(value==='validation'&&!traces.some((t)=>t.partition==='validation'))continue;
      const option=document.createElement('option');option.value=value;option.textContent=label;$('partition').append(option);
    }
    show('scope-note', rubric ? 'Criterion labeling against a frozen rubric. Validation means calibration validation, never the experiment final test.' : 'Tuning traces only. Human judgments are drafts until validated and sealed with the CLI.');
    $('export').disabled=false;select(traces[0]?.id||null);show('save-status','Changes stay in this page until you export. Closing without export loses them.');
  }
  if(initial)receive(initial);
  return {receive};
}
