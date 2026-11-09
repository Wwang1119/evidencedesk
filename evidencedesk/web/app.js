const $ = id => document.getElementById(id);
let currentBrief = null;
let events = [];
let timer;
const el = (tag, cls, text) => {const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;};
const stageOrder=['plan','search','extract','synthesize','review'];

async function refreshStatus(){
  try{
    const r=await fetch('/api/status'); if(!r.ok)throw Error(); const s=await r.json();
    $('connection').textContent=s.ready?'Ready for live research':'API keys needed';
    $('connection').classList.toggle('ready',s.ready); $('setup').hidden=s.ready;
  }catch{$('connection').textContent='Connection unavailable';}
}
refreshStatus();
window.addEventListener('focus',refreshStatus);
document.querySelectorAll('[data-example]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.example;$('question').focus();}));

function trace(event){
  events.push(event); $('trace-box').hidden=false; $('trace-count').textContent=`${events.length} events`;
  const row=el('div','trace-event');row.append(el('span','trace-time',`${event.elapsed||0}s`));
  const body=el('div');body.append(el('p','',event.message||`${event.service||'Agent'} · ${event.operation||event.stage}`));
  const metadata={...event};delete metadata.message;delete metadata.elapsed;delete metadata.type;
  if(metadata.source){metadata.source={id:metadata.source.id,url:metadata.source.url,http_status:metadata.source.http_status};}
  body.append(el('pre','',JSON.stringify(metadata,null,2)));row.append(body);$('trace').append(row);
  if(event.message)$('progress-title').textContent=event.message;
  let stage=event.stage==='follow_up'?'search':event.stage==='source'?'extract':event.stage==='validate'?'review':event.stage;
  const i=stageOrder.indexOf(stage);
  if(i>=0)document.querySelectorAll('[data-stage]').forEach(n=>{const j=stageOrder.indexOf(n.dataset.stage);n.classList.toggle('active',i===j);n.classList.toggle('passed',j<i);});
}

function render(brief){
  currentBrief=brief;$('result').hidden=false;$('research-question').textContent=brief.question;
  $('result-title').textContent=brief.status==='insufficient_evidence'?'The evidence is not there yet.':'Findings & evidence';
  $('metrics').replaceChildren();
  const metrics=[brief.status.replaceAll('_',' '),`${brief.claims.length} published claims`,`${brief.sources.length} cited sources`,`${brief.stats.facets_covered}/${brief.stats.facets_total} question facets`,`${brief.stats.elapsed_seconds}s`];
  metrics.forEach(t=>$('metrics').append(el('span','metric',t)));
  $('claims').replaceChildren();
  brief.claims.forEach((c,i)=>{
    const card=el('article','claim'),top=el('div','claim-top');
    top.append(el('span','',`${String(i+1).padStart(2,'0')} / ${c.facet.toUpperCase()}`));
    top.append(el('span','kind',c.kind==='finding'?'MODEL-REVIEWED':c.kind.toUpperCase()));card.append(top);
    const p=el('p','',c.text+' ');
    [...new Set(c.citations.map(x=>x.source_id))].forEach(id=>{const a=el('a','citation',`[${id}]`);a.href=`#source-${id}`;a.setAttribute('aria-label',`Inspect source ${id}`);p.append(a);});
    card.append(p);$('claims').append(card);
  });
  if(!brief.claims.length)$('claims').append(el('p','research-question','No factual answer passed the citation gates. Refine the question, search for a different source, or inspect the research trace.'));
  $('limits').replaceChildren();
  const limits=[...brief.gaps,...brief.warnings];$('limits').hidden=!limits.length;
  if(limits.length){$('limits').append(el('h3','','EVIDENCE LIMITS'));const ul=el('ul');[...new Set(limits)].forEach(t=>ul.append(el('li','',t)));$('limits').append(ul);}
  $('source-count').textContent=brief.sources.length;$('sources').replaceChildren();
  brief.sources.forEach(s=>{
    const card=el('section','source');card.id=`source-${s.id}`;
    const head=el('div','source-heading');head.append(el('span','source-number',s.id),el('h4','',s.title));card.append(head,el('p','source-domain',s.domain));
    const evidence=brief.claims.flatMap(c=>c.evidence).filter(e=>e.source_id===s.id);
    [...new Set(evidence.map(e=>e.quote))].forEach(q=>card.append(el('blockquote','',`“${q}”`)));
    const a=el('a','original','Open original source ↗');a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';card.append(a);
    card.append(el('div','source-check',`HTTP ${s.http_status} · Checked ${new Date(s.checked_at).toLocaleString('en-GB')}\nExact quote matched to extracted text`));
    const details=el('details');details.append(el('summary','','Inspect context & provenance'));
    evidence.forEach(e=>details.append(el('p','',e.context)));
    details.append(el('p','',s.selection_note),el('p','',`Final URL: ${s.final_url}`),el('p','',`Text SHA-256: ${s.text_sha256}`));
    card.append(details);$('sources').append(card);
  });
  $('result').scrollIntoView({behavior:'smooth',block:'start'});
}

$('research-form').addEventListener('submit',async event=>{
  event.preventDefault();const question=$('question').value.trim();if(question.length<10)return;
  $('submit').disabled=true;$('question').disabled=true;$('error').hidden=true;$('result').hidden=true;$('progress').hidden=false;
  $('workflow').hidden=true;$('examples').hidden=true;$('trace').replaceChildren();events=[];currentBrief=null;
  document.querySelectorAll('[data-stage]').forEach(n=>n.classList.remove('active','passed'));
  const start=Date.now();timer=setInterval(()=>$('elapsed').textContent=`${Math.floor((Date.now()-start)/1000)}s`,1000);
  let received=false;
  try{
    const response=await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
    if(!response.ok){const data=await response.json();throw Error(typeof data.detail==='string'?data.detail:'Enter a valid research question.');}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    const consume=line=>{if(!line.trim())return;const data=JSON.parse(line);if(data.type==='progress')trace(data);else if(data.type==='result'){received=true;render(data.brief);}else if(data.type==='error')throw Error(data.message);};
    while(true){const{value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let n;while((n=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,n);buffer=buffer.slice(n+1);consume(line);}}
    buffer+=decoder.decode();if(buffer.trim())consume(buffer);if(!received)throw Error('The research connection ended before a validated brief was ready. Please retry.');
  }catch(error){$('error').textContent=error.message;$('error').hidden=false;}
  finally{clearInterval(timer);$('progress').hidden=true;$('submit').disabled=false;$('question').disabled=false;refreshStatus();}
});

function download(kind){
  if(!currentBrief)return;const text=kind==='md'?currentBrief.markdown:JSON.stringify(currentBrief,null,2);
  const url=URL.createObjectURL(new Blob([text],{type:kind==='md'?'text/markdown':'application/json'}));
  const a=el('a');a.href=url;a.download=`evidencedesk-${currentBrief.id}.${kind}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('download-md').addEventListener('click',()=>download('md'));
$('download-json').addEventListener('click',()=>download('json'));
