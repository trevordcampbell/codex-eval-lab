import { App } from '@modelcontextprotocol/ext-apps';
import { mountReview } from './review.js';
const app=new App({name:'Codex Eval Lab Review',version:'0.5.0'},{},{autoResize:true});
const view=mountReview(null,{loadPacket:async(packetId)=>{
 const result=await app.callServerTool({name:'open_review',arguments:{packet_id:packetId}});
 if(result.isError)throw Error('The local server rejected the selected packet');
 return result._meta?.['codex-eval-lab/review'];
}});
// Handler precedes connect so the initial tool result cannot race registration.
app.ontoolresult=(result)=>view.receive(result._meta?.['codex-eval-lab/review']);
app.connect().catch(()=>{document.getElementById('save-status').textContent='This host did not connect the review UI. Use eval-lab review render for the offline viewer.';});
