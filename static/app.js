let sid, products = [], busy = false, confirmedProduct = '', ready = false;
let waitingTimers = new Set(), testEpoch = 0;
let selectedQuestion = null, selectedResult = null;
let access = {can_manage:false, public_demo:false}, ragAbort = null, ragSerial = 0, ragPendingResult = null;
let assistTab='advice', noticeTimer, starterEl=null;
let transcript=[],restoring=false;
const resumeKey='pac-chat-resume-v1';
function persistConversation(){
 try{if(!sid||restoring||!window.sessionStorage)return;const value=JSON.stringify({created:Date.now(),sid,product:confirmedProduct,reception:$('reception-type').value,stage:$('business-stage').value,input:$('input').value,entries:transcript.slice(-120)},(key,value)=>key==='bubble'?undefined:value);if(value.length<1500000)window.sessionStorage.setItem(resumeKey,value);}catch{}
}
function rememberedConversation(){try{const v=JSON.parse(window.sessionStorage?.getItem(resumeKey)||'null');return v&&Date.now()-v.created<1800000&&Array.isArray(v.entries)?v:null;}catch{return null;}}
async function restoreConversation(saved){
 let state,expired=false;
 try{state=await api('/api/sessions/'+encodeURIComponent(saved.sid));}
 catch(e){if(![403,404,410].includes(e.status))throw e;expired=true;await createSession(products.some(p=>p.id===saved.product)?saved.product:'');state=null;}
 restoring=true;
 try{
  if(state){sid=state.session_id;showState(state);}
  $('reception-type').value=saved.reception||'presales';$('business-stage').value=saved.stage||'presales';
  $('messages').replaceChildren();resetAssistant();transcript=saved.entries;
  for(const entry of transcript){
   if(entry.card){renderProductCard(entry.card);continue;}
   const el=bubble(entry.text,entry.role,entry.role==='user'?null:entry.result,entry.options||{});el.savedEntry=entry;
   if(entry.role==='user'&&entry.result)testFeedback(el,entry.result,entry.text,entry.conditions||{});
  }
  $('input').value=saved.input||'';
  const latest=[...transcript].reverse().find(e=>e.role==='user'&&e.result);
  if(latest)trace(latest.result);
  $('status').textContent=latest?labels[latest.result.status]||'待接待':'待接待';
 }finally{restoring=false;}
 if(expired)bubble('服务端会话已失效，历史对话已保留；后续咨询使用新会话。','system');
 else notify('已恢复原来的测试对话');
 persistConversation();return true;
}
const $ = id => document.getElementById(id);
const labels = {answered:'自动回答', clarify:'需要追问', handoff:'待客服查看', suppressed:'待客服查看', duplicate:'已答复 · 不重复发送', error:'系统失败'};
const receptionLabels = {presales:'售前接待', aftersales:'售后接待'};
const stageLabels = {presales:'售前', shipping:'发货中', received:'发货后', aftersales:'售后'};
async function api(path, data, options = {}) {
  const controller = options.controller || new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, {method:data === undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data === undefined?undefined:JSON.stringify(data),signal:controller.signal});
    const result = await response.json();
    if (!response.ok){const error=new Error(result.answer || result.detail || `HTTP ${response.status}`);error.status=response.status;throw error;}
    return result;
  } finally { clearTimeout(timer); }
}
function showState(s) {
  $('session').textContent = `会话 ${s.session_id}`;
  confirmedProduct = s.current_product_id || '';
  $('product-select').value = confirmedProduct;
  $('current').textContent = products.find(p=>p.id===confirmedProduct)?.name || '尚未确认';
  $('candidates').textContent = `候选卡片：${(s.recent_product_ids || []).map(id=>products.find(p=>p.id===id)?.name || id).join('、') || '无'}`;
  $('candidates').hidden=!(s.recent_product_ids||[]).length;
  $('stage-caption').textContent=stageLabels[$('business-stage').value];
  updateContextSummary();
  persistConversation();
  // 接待条件保留用户当前选择，避免旧回复把下一条问题的条件改回去。
}
function updateContextSummary(){
  const product=products.find(p=>p.id===$('product-select')?.value)?.name||'未确认商品';
  const reception=receptionLabels[$('reception-type')?.value]||'售前接待';
  const stage=stageLabels[$('business-stage')?.value]||'售前';
  const el=$('context-summary');if(el)el.textContent=`${product} · ${reception} · ${stage}`;
}
function replyOrigin(result){const method=result.debug?.retrieval?.method||'';return /faq|semantic_onnx/.test(method)?'FAQ':'知识库';}
function openReplyRag(result){
 trace(result);setAssistTab('advice');
 const panel=$('rag-panel');panel.hidden=false;highlight(panel);
 panel.scrollIntoView?.({block:'nearest',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
 if(!result.ragResult&&!result.ragLoading&&!busy)loadRag(result);
}
function nearLatest(){const box=$('messages');return box.scrollHeight-(box.scrollTop||0)-(box.clientHeight||0)<100;}
function followLatest(force=false){
 const box=$('messages');
 if(force){if(box.scrollTo)box.scrollTo({top:box.scrollHeight,behavior:'instant'});else box.scrollTop=box.scrollHeight;if($('new-replies'))$('new-replies').hidden=true;}
 else if($('new-replies'))$('new-replies').hidden=false;
}
function highlight(el){
 if(!el?.animate||window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)return;
 el.animate([{boxShadow:'0 0 0 0 #78a4fa00'},{boxShadow:'0 0 0 4px #78a4fa30'},{boxShadow:'0 0 0 0 #78a4fa00'}],{duration:480,easing:'ease-out'});
}
function bubble(text, role, result, options = {}) {
  const follow=role==='user'||nearLatest();
  const el = document.createElement('div'); el.className = `bubble ${role} ${result?.status || ''}`;
  if(result){
    const tag=document.createElement('small');tag.className='reply-source';
    const needsRag=options.waiting||result.status==='clarify'||result.status==='error'||(!result.send_to_customer&&result.status!=='duplicate');
    tag.append(node('span',options.waiting?'等待提示':result.status==='clarify'?'澄清追问':result.status==='error'?'异常提示':needsRag?'FAQ 未采用':role==='assistant'&&result.status==='answered'?replyOrigin(result)+' · 自动回复':labels[result.status]));
    if(needsRag){const action=node('button','查看 RAG 建议 ↗','reply-rag-link');action.type='button';action.setAttribute('aria-label','查看本条问题的 RAG 建议');action.onclick=e=>{e.stopPropagation();openReplyRag(result);};action.onkeydown=e=>e.stopPropagation();tag.append(action);}
    el.append(tag);el.tabIndex=0;el.onclick=()=>trace(result);el.onkeydown=e=>{if(e.key==='Enter')trace(result);};
  }
  el.append(document.createTextNode(text));
  if(result?.send_to_customer&&options.images!==false){for(const asset of result.images || []){const img=document.createElement('img');img.src=asset.url;img.alt=asset.alt;img.loading='lazy';img.style.cssText='display:block;max-width:100%;width:180px;height:180px;object-fit:contain;object-position:left top;border-radius:8px;margin-top:10px';const link=document.createElement('a');link.href=asset.url;link.target='_blank';link.rel='noopener';link.title='点击查看原图';link.onclick=e=>e.stopPropagation();link.append(img);el.append(link);}}
  if(role==='assistant'&&result?.send_to_customer&&options.edit!==false){const href=answerKnowledgeLink(result);if(href){const edit=node('a','修改答案','answer-inline-edit');edit.href=href;edit.target='_blank';edit.rel='noopener';edit.title='在知识库编辑答案、商品和接待条件';bindKnowledgeLink(edit);el.append(edit);}}
  $('messages').append(el);followLatest(follow);
  if(!restoring){const entry={text,role,result,options};el.savedEntry=entry;transcript.push(entry);persistConversation();}return el;
}
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function openKnowledgeEditor(href){
 const url=new URL(href,window.location.origin);
 if(url.origin!==window.location.origin||url.pathname!=='/knowledge')return;
 persistConversation();url.searchParams.set('embed','1');
 const dialog=$('knowledge-workspace'),frame=$('knowledge-workspace-frame');
 $('knowledge-workspace-note').textContent='正在读取知识配置…';frame.src=url.pathname+url.search;
 dialog.showModal();
}
function bindKnowledgeLink(link){link.target='_self';link.onclick=e=>{e.preventDefault();e.stopPropagation();openKnowledgeEditor(link.href);};}
function closeKnowledgeWorkspace(){
 const frame=$('knowledge-workspace-frame');
 if(frame.contentWindow)frame.contentWindow.postMessage({type:'pac-editor-close-request'},window.location.origin);
 else $('knowledge-workspace').close();
}
if($('knowledge-workspace')){
 $('close-knowledge-workspace').onclick=closeKnowledgeWorkspace;
 $('knowledge-workspace').oncancel=e=>{e.preventDefault();closeKnowledgeWorkspace();};
 $('knowledge-workspace-frame').onload=()=>{$('knowledge-workspace-note').textContent='修改保存在知识库，原咨询对话保留';};
 window.addEventListener?.('message',e=>{
  if(e.origin!==window.location.origin||e.source!==$('knowledge-workspace-frame').contentWindow)return;
  if(e.data?.type==='pac-editor-close'){$('knowledge-workspace').close();$('knowledge-workspace-frame').src='about:blank';}
  if(e.data?.type==='pac-editor-saved'){notify('知识已保存，可以继续测试原问题');$('knowledge-workspace-note').textContent='已保存 · 关闭面板后可继续原咨询';}
 });
}
function notify(text){if(!$('toast'))return;clearTimeout(noticeTimer);$('toast').textContent=text;$('toast').hidden=false;noticeTimer=setTimeout(()=>{$('toast').hidden=true;},2400);}
function setAssistTab(tab){
  assistTab=tab;
  if(!$('advice-panel'))return;
  $('advice-panel').hidden=tab!=='advice';$('diagnostic-panel').hidden=tab!=='diagnostic';
  $('tab-advice').setAttribute('aria-selected',String(tab==='advice'));
  $('tab-diagnostic').setAttribute('aria-selected',String(tab==='diagnostic'));
  const panel=$(tab==='advice'?'advice-panel':'diagnostic-panel');
  if(panel?.animate&&!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)panel.animate([{opacity:0,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:180,easing:'ease-out'});
  if(tab==='diagnostic')$('evidence-details').open=true;
}
function answerKnowledgeLink(result){
  if(!access.can_manage)return null;
  const ids=result.debug?.editable_answer_ids||[];if(ids.length!==1)return null;
  const analysis=result.debug?.analysis||{},context=result.uiContext||{};
  const url=new URL(context.url||analysis.knowledge_url||'/knowledge',window.location.origin);
  if(url.origin!==window.location.origin||url.pathname!=='/knowledge')return null;
  const scene=url.searchParams.get('scene')||(analysis.intents?.length===1?analysis.intents[0].id:null);if(!scene)return null;
  // 使用实际可编辑的唯一来源；派生分段也编辑完整知识，不按气泡覆盖答案。
  url.searchParams.set('scene',scene);url.searchParams.set('answer',ids[0]);url.searchParams.set('action','answer');
  if(context.key)url.searchParams.set('test',context.key);
  return url.pathname+url.search;
}
function resetAssistant(){
  setAssistTab('advice');
  selectedResult=null;cancelRag();if($('rag-panel'))$('rag-panel').hidden=true;
  selectedQuestion=null;$('assist-empty').hidden=false;$('assist-content').hidden=true;
  $('debug').textContent='尚无检索记录';$('trace-summary').textContent='';$('trace-evidence').replaceChildren();$('evidence-details').open=false;
}
function trace(r){
  if(selectedResult!==r)cancelRag();selectedResult=r;
  const a=r.debug?.analysis||{}, helper=a.assistant||{title:'暂未完成分析',badge:r.status==='error'?'请求失败':'待核实',tone:'warning',summary:a.outcome||'请查看检索依据。',advice:'核实意图与已有知识后，再决定是否补充。',action:r.status==='error'?'retry':'review'};
  const context=r.uiContext||{}, question=r.debug?.question||context.question||'本条咨询';
  if(selectedQuestion)selectedQuestion.className=selectedQuestion.className.replace(' selected','');
  selectedQuestion=context.bubble||null;if(selectedQuestion)selectedQuestion.className+=' selected';
  highlight($('assist-question'));
  if($('reply-mode')){const answered=r.status==='answered'&&r.send_to_customer;$('reply-mode').textContent=answered?replyOrigin(r)+' 已自动回复':r.status==='clarify'?'已发送澄清追问':'FAQ 未采用 · 辅助人工核实';$('reply-mode').setAttribute('data-mode',answered?'faq':'review');}
  $('assist-empty').hidden=true;$('assist-content').hidden=false;$('assist-question').textContent=question;
  $('assist-intent').textContent=a.status==='matched'?a.intents.map(i=>i.name).join('、'):helper.title;
  $('assist-badge').textContent=helper.badge;$('assist-badge').className='assist-badge '+helper.tone;
  $('trace-summary').textContent=helper.summary;$('assist-advice').textContent=helper.advice;
  if($('advice-panel'))$('advice-panel').setAttribute('data-outcome',r.status);
  const url=new URL(context.url||a.knowledge_url||'/knowledge',window.location.origin);
  const action=$('assist-action'), secondary=$('assist-secondary');
  const actions={answer:['修改 / 补充答案','answer'],view:['查看知识',''],review:[a.candidates?.length?'核实候选意图':'新建待完善条目',a.candidates?.length?'':'new']};
  const [label,kind]=actions[helper.action]||actions.review;
  action.onclick=null;action.target='_blank';action.textContent=label;
  if(kind)url.searchParams.set('action',kind);action.href=url.pathname+url.search;
  bindKnowledgeLink(action);
  if(helper.action==='retry'){
    action.textContent='重新测试本条';action.target='_self';action.href='#input';
    action.onclick=async e=>{e.preventDefault();if(busy||!ready)return;
      $('reception-type').value=context.conditions?.reception_type||r.session?.reception_type||'presales';
      $('business-stage').value=context.conditions?.business_stage||r.session?.business_stage||'presales';
      const product=r.session?.current_product_id||null;
      if(product!==confirmedProduct)await event('customer_select',product);
      await send(question);
    };
  }else if(helper.action==='review'&&a.candidates?.length){
    action.target='_self';action.href='#evidence-details';
    action.onclick=e=>{e.preventDefault();$('evidence-details').open=true;};
  }
  const general=new URL(context.url||a.knowledge_url||'/knowledge',window.location.origin);general.searchParams.delete('action');
  secondary.href=general.pathname+general.search;secondary.textContent=a.status==='matched'?'补充拓展问法':'关联已有意图';
  if(a.status==='matched'){general.searchParams.set('action','variant');secondary.href=general.pathname+general.search;}
  if(a.reason_code==='dimension_repair_exhausted'){general.searchParams.delete('action');secondary.href=general.pathname+general.search;secondary.textContent='核对上一轮意图';}
  bindKnowledgeLink(secondary);
  const details=$('trace-evidence');details.replaceChildren();$('evidence-details').open=false;
  const s=r.session||{}, conditions=[receptionLabels[s.reception_type],stageLabels[s.business_stage]].filter(Boolean).join(' / ');
  details.append(node('p',`${products.find(p=>p.id===s.current_product_id)?.name||'商品未确认'}${conditions?' · '+conditions:''}`,'evidence-meta'));
  details.append(node('p','识别方式：'+(a.method||'未完成识别')));
  if(a.matched_question)details.append(node('p','命中问法：'+a.matched_question));
  const semanticStates={matched:'已命中',low_confidence:'相似度或候选分差不足，未采纳',guard_rejected:'触发检索边界，未采用向量候选',empty:'没有可用候选',product_unconfirmed:'商品未确认',disabled:'未启用',model_missing:'本地向量模型未安装'};
  if(a.semantic_status)details.append(node('p','语义检索：'+(semanticStates[a.semantic_status]||a.semantic_status)));
  if(a.intent_model_status)details.append(node('p','辅助模型：'+({failed:'调用失败',matched:'已选中',no_match:'未采用候选',disabled:'未启用',success:'调用成功'}[a.intent_model_status]||a.intent_model_status)));
  if(a.error_type)details.append(node('p','错误类型：'+a.error_type,'evidence-error'));
  if(a.reason_code)details.append(node('p','原因代码：'+a.reason_code,'evidence-meta'));
  details.append(node('p',a.outcome||r.operator_note||helper.summary));
  if(a.candidates?.length&&a.status!=='matched'){
    details.append(node('h4','候选意图 · 尚未确认'));
    for(const c of a.candidates){const link=node(access.can_manage?'a':'span',c.name+(typeof c.score==='number'?` · 相似度 ${c.score.toFixed(2)}`:''),'candidate-link');const target=new URL(general);target.searchParams.set('scene',c.id);target.searchParams.delete('action');link.href=target.pathname+target.search;link.target='_blank';link.rel='noopener';if(access.can_manage)bindKnowledgeLink(link);details.append(link);}
  }
  for(const item of helper.evidence||[]){
    const card=node('article',undefined,'evidence-item');card.append(node('h4',(item.candidate_only?'候选资料：':'知识：')+item.scene_name),node('p',item.text||'暂无标准答案'));
    card.append(node('small',item.exclusions?.length?'条件排除：'+item.exclusions.join('、'):'条件符合'+(item.candidate_only?'；意图尚未确认':'；是否采用见原始诊断')));
    const sources=[...new Set((item.sources||[]).map(s=>[s.file,s.sheet,s.cell].filter(Boolean).join(' · ')||({'user_confirmation':'用户确认','user_confirmation_and_draft':'用户确认及核准话术'}[s.type])||'').filter(Boolean))];
    for(const source of sources.slice(0,2))card.append(node('small','来源：'+source));
    details.append(card);
  }
  if(!helper.evidence?.length)details.append(node('p','本次没有可展示的关联知识。','evidence-meta'));
  if(helper.evidence_count>6)details.append(node('small',`展示 ${helper.evidence.length} / ${helper.evidence_count} 条；全部答案可在知识库查看。`));
  $('debug').textContent=JSON.stringify(r.debug,null,2);
  action.hidden=!access.can_manage&&!['retry','review'].includes(helper.action);
  if(!access.can_manage&&helper.action==='review'&&!a.candidates?.length)action.hidden=true;
  secondary.hidden=!access.can_manage;
  renderRag(r);
  setAssistTab(assistTab);
}

function cancelRag(){ragSerial++;if(ragAbort)ragAbort.abort();ragAbort=null;if(ragPendingResult)ragPendingResult.ragLoading=false;ragPendingResult=null;}
function ragIntent(value){return typeof value==='string'?value:value?.name||value?.title||'待确认';}
function ragPresentation(rag,loading){
  if(loading)return {state:'loading',title:'正在查找回复依据',caption:'检索知识，整理回复参考'};
  if(!rag)return {state:'idle',title:'知识助手',caption:'从已有知识中寻找依据'};
  if(rag.generation_status==='generated')return {state:'generated',title:'AI 建议回复',caption:rag.status==='partial'?'依据不完整，请先核实缺失信息':'已基于引用资料生成 · 人工确认后使用'};
  if(rag.sources?.length)return {state:'excerpt',title:rag.retrieval_method==='faq_reference'?'FAQ 话术参考':'找到相关资料',caption:rag.retrieval_method==='faq_reference'?'来自已维护的 FAQ · 确认后使用':'以下为资料摘录，尚未生成可直接使用的新回复'};
  return {state:'holding',title:'建议先回应客户',caption:'暂无可用业务答案 · 以下为等待话术'};
}
function renderRag(result){
  if(!$('rag-panel'))return;
  $('rag-panel').hidden=false;
  const rag=result.ragResult, loading=!!result.ragLoading;
  const presentation=ragPresentation(rag,loading);
  $('rag-panel').setAttribute('data-state',presentation.state);
  const icon={loading:'search',generated:'reply',excerpt:'document',holding:'handoff',idle:'document'}[presentation.state];
  if($('rag-state-icon'))$('rag-state-icon').src='/static/icons/'+icon+'.svg';
  if($('rag-flow-label'))$('rag-flow-label').textContent=loading?'整理依据':presentation.state==='generated'?'建议已就绪':presentation.state==='excerpt'?'资料摘录':'回复参考';
  $('rag-empty').textContent=loading?'正在检索当前商品资料…':'复杂问题，从资料中找依据。';
  if($('rag-answer-title'))$('rag-answer-title').textContent=presentation.title;
  if($('rag-answer-caption'))$('rag-answer-caption').textContent=presentation.caption;
  $('rag-panel').setAttribute('aria-busy',String(loading));
  if($('rag-copy'))$('rag-copy').textContent=presentation.state==='generated'?'复制建议回复':presentation.state==='excerpt'?'复制参考内容':'复制等待话术';
  $('rag-search').disabled=loading;$('rag-search').textContent=loading?'检索中…':rag?'重新查资料':'查资料 ↗';
  $('rag-empty').hidden=!!rag;$('rag-content').hidden=!rag;
  $('rag-status').textContent=loading?'正在检索':rag?({generated:'基于资料生成',extractive:'资料摘录',partial:'资料不完整',product_required:'请先确认商品',manual_boundary:'需人工核实',no_evidence:'资料不足',insufficient:'资料不足',unavailable:'暂不可用',error:'暂不可用'}[rag.status]|| (rag.generation_status==='generated'?'基于资料生成':rag.sources?.length?'资料摘录':'资料不足')):'';
  if(!rag)return;
  const generation=rag.generation_status||'not_called',hasSources=!!rag.sources?.length;
  const offline=['disabled','mock'].includes(generation);
  const rejected=['invalid_output','invalid_citations','unsupported_numbers','unsupported_ranges','unsupported_topics','unsupported_promise','insufficient'].includes(generation);
  $('rag-generation-note').hidden=!hasSources||generation==='generated'||generation==='not_called';
  $('rag-generation-note').textContent=offline?'当前未启用生成，仅展示资料摘录。':generation==='missing_key'?'当前未配置生成，仅展示资料摘录。':rejected?'生成未通过核验，先查看资料摘录。':'生成暂不可用，先查看资料摘录。';
  $('rag-retrieval-method').textContent='检索：'+({hybrid:'关键词＋语义（混合检索）',keyword:'关键词检索',keyword_fallback:'关键词检索（语义暂不可用）',faq_reference:'通用接待 FAQ'}[rag.retrieval_method]||'未取得检索方式');
  const generationLabels={generated:'已基于引用资料生成',disabled:'未启用',mock:'演示模式，未调用生成',missing_key:'未配置生成密钥',not_called:'未调用',timeout:'调用超时',failed:'调用失败',invalid_output:'输出格式未通过核验',invalid_citations:'引用未通过核验',unsupported_numbers:'新增数字未通过核验',unsupported_ranges:'调节范围未通过核验',unsupported_topics:'内容主题未通过核验',unsupported_promise:'承诺未通过核验',insufficient:'生成依据不足'};
  $('rag-generation-status').textContent='生成：'+(generationLabels[generation]||'暂不可用')+' · '+generation;
  $('rag-suggestion').textContent=(rag.suggestion||'亲亲，小妹仔细看看您的问题，请您稍等～').replace(/^资料摘录[：:]\s*/,'');if($('rag-advice')){$('rag-advice').hidden=!rag.operator_advice;$('rag-advice').textContent=rag.operator_advice||'';}
  const intent=ragIntent(rag.proposed_intent);$('rag-intent').textContent='意图建议：'+intent+' · '+(rag.can_save_faq?'可人工确认后沉淀':'暂不建议沉淀');
  const sources=$('rag-sources');sources.replaceChildren();
  for(const source of (rag.sources||[]).slice(0,3)){
    const detail=node('details',undefined,'rag-source'),summary=node('summary',source.title||'参考资料');
    detail.append(summary,node('p',source.excerpt||source.content||''),node('small',typeof source.source==='string'?source.source:source.source?.title||'已维护资料'));sources.append(detail);
  }
  const missing=Array.isArray(rag.missing_info)?rag.missing_info.filter(Boolean):[];
  $('rag-missing').hidden=!missing.length;$('rag-missing').textContent=missing.length?'需补充：'+missing.slice(0,3).join('、'):'';
  const save=$('rag-save');save.hidden=!access.can_manage||!rag.can_save_faq||!rag.sources?.length;
  if(!save.hidden){const key=TestContext.saveRag(result,rag);save.hidden=!key;if(key){save.href='/knowledge?test='+encodeURIComponent(key)+'&action=rag-draft';bindKnowledgeLink(save);}}
}
async function loadRag(result){
  if(!sid||!ready||result.ragLoading)return;
  cancelRag();const serial=ragSerial,epoch=testEpoch,session=sid,controller=new AbortController();ragAbort=controller;ragPendingResult=result;result.ragLoading=true;result.ragRequest=serial;
  if(selectedResult===result)renderRag(result);
  const context=result.uiContext||{},state=result.session||{},conditions=context.conditions||{};
  try{
    const rag=await api('/api/rag/assist',{session_id:session,message:result.debug?.question||context.question||'',product_id:state.current_product_id||null,reception_type:conditions.reception_type||state.reception_type||'presales',business_stage:conditions.business_stage||state.business_stage||'presales'},{controller});
    if(serial!==ragSerial||epoch!==testEpoch||session!==sid)return;
    result.ragResult=rag;
  }catch(error){
    if(serial!==ragSerial||epoch!==testEpoch||session!==sid)return;
    result.ragResult={status:'unavailable',suggestion:'亲亲，小妹仔细看看您的问题，请您稍等～',operator_advice:'资料辅助暂不可用，先核实问题再答复。',sources:[],can_save_faq:false,proposed_intent:'待确认'};
  }finally{
    if(result.ragRequest===serial)result.ragLoading=false;if(ragAbort===controller){ragAbort=null;ragPendingResult=null;}
    if(serial===ragSerial&&epoch===testEpoch&&session===sid&&selectedResult===result)renderRag(result);
  }
}

function lock(value){
  busy=value;
  $('send').textContent=value&&ready?'处理中…':'发送 ↗';
  $('form').setAttribute('aria-busy',String(value));
  $('form').setAttribute('data-has-text',String(!!$('input').value.trim()));
  document.querySelectorAll('button, aside select').forEach(control=>{
    if(control.id==='new-replies')return;
    control.disabled=value || (!ready && control.id!=='reconnect') || (control.id==='rag-search'&&!!selectedResult?.ragLoading);
  });
}
async function event(type, product_id){if(busy)return;lock(true);try{showState(await api(`/api/sessions/${sid}/events`,{type,product_id}));const product=products.find(p=>p.id===product_id);const text=type==='customer_select'&&!product_id?'客户商品已清除，当前尚未确认':({agent_card:'客服发送候选卡片',customer_select:'客户确认商品',takeover:'客服接管会话',resume:'客服恢复 AI',handled:'客服已处理，等待提示已取消'})[type]+(product_id?` · ${product?.name || product_id}`:'');bubble(text,'system');notify(text);if(type==='resume')$('status').textContent='待接待';}catch(e){$('product-select').value=confirmedProduct;bubble(`操作失败：${e.message}`,'error');}finally{lock(false);}}
function starterIcon(){const img=node('img',undefined,'starter-icon');img.src='/static/icons/conversation.svg';img.alt='';return img;}
function showStarter(){starterEl=node('section',undefined,'chat-starter');starterEl.append(starterIcon(),node('h3','试一句，看看机器人怎么接待'),node('p','FAQ 自动回复，资料助手辅助核实。'));const choices=node('div',undefined,'starter-choices');for(const text of ['你好','有优惠吗','多久能到？']){const b=node('button',text);b.type='button';b.onclick=()=>send(text);choices.append(b);}starterEl.append(choices);$('messages').append(starterEl);}
async function createSession(product_id){
  cancelWaiting();
  let s=await api('/api/sessions',{});
  sid=s.session_id;
  transcript=[];
  // 新会话沿用测试商品和接待条件。
  if(product_id)s=await api(`/api/sessions/${sid}/events`,{type:'customer_select',product_id});
  $('messages').replaceChildren();resetAssistant();$('status').textContent='待接待';
  showState(s);showStarter();
}
function connectionFailed(message){
  ready=false;$('mode').textContent='连接失败';$('session').textContent='尚未建立会话';
  $('connection-note').textContent='连接未完成，请确认服务已启动后重试。';
  $('reconnect').hidden=false;bubble(message,'error');
}
function cancelWaiting(){cancelRag();testEpoch++;for(const timer of waitingTimers)clearTimeout(timer);waitingTimers.clear();}
async function resetTest(mode){
 if(busy||!ready)return;
 lock(true);cancelWaiting();
 try{
  const s=await api(`/api/sessions/${sid}/reset`,{mode,reception_type:$('reception-type').value,business_stage:$('business-stage').value});
  if(mode==='test'){
    $('reception-type').value='presales';$('business-stage').value='presales';
    if($('candidate-select'))$('candidate-select').value='';
  }
  // 重置后刷新页面也不应自动再发送 URL 中的旧复测问题。
  if(window.history?.replaceState)window.history.replaceState(null,'',window.location.pathname||'/');
  transcript=[];$('messages').replaceChildren();$('input').value='';resetAssistant();
  $('status').textContent='待接待';showState(s);
  bubble(mode==='test'?'测试已重置：记忆和商品已清除，接待条件恢复为售前。':'记忆已清除：对话、候选卡片和重复记录已清空，商品与接待条件保留。','system');
 }catch(e){bubble('清除失败：'+e.message+'。请重新连接后再试。','error');}
 finally{lock(false);}
}
async function newSession(){
  if(busy||!ready)return;
  const product_id=$('product-select').value;lock(true);
  try{await createSession(product_id);}
  catch(e){connectionFailed(`创建会话失败：${e.message}`);}
  finally{lock(false);}
}
function testFeedback(userBubble,r,text,conditions){
  if(userBubble.savedEntry){userBubble.savedEntry.result=r;userBubble.savedEntry.conditions=conditions;persistConversation();}
  const a=r.debug?.analysis || {status:'unrecognized',intents:[],outcome:r.operator_note||'未取得诊断信息，请查看回答依据。',knowledge_url:'/knowledge'};
  const box=document.createElement('section');box.className='intent-feedback';box.setAttribute('aria-label','本条问题分析');
  const heading=document.createElement('div');heading.className='intent-feedback-heading';
  const title=document.createElement('button');title.type='button';title.className='intent-label';
  title.textContent='客户意图：'+(a.status==='matched'?a.intents.map(i=>i.name).join('、'):a.status==='ambiguous'?'待确认':'未识别');
  const key=TestContext.save(r,r.debug?.question||text,conditions);
  const url=new URL(a.knowledge_url||'/knowledge',window.location.origin);if(key)url.searchParams.set('test',key);
  const optimize=document.createElement('a');optimize.textContent='优化 →';optimize.href=url.pathname+url.search;optimize.target='_blank';optimize.rel='noopener';bindKnowledgeLink(optimize);
  optimize.textContent='优化';optimize.hidden=!access.can_manage;
  heading.append(title,optimize);box.append(heading);
  r.uiContext={question:text,url:url.pathname+url.search,key,bubble:userBubble,conditions};
  userBubble.tabIndex=0;userBubble.setAttribute('aria-label','客户问题：'+text+'，查看分析');
  userBubble.setAttribute('role','button');userBubble.onclick=()=>trace(r);userBubble.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();trace(r);}};title.onclick=()=>trace(r);
  optimize.onclick=e=>{e.preventDefault();trace(r);if(window.innerWidth<=980)$('assist-content').scrollIntoView({block:'start',behavior:'auto'});};
  userBubble.after(box);
  return key;
}
async function send(text){
  if(busy||!ready||!text.trim())return;if(starterEl){starterEl.remove();starterEl=null;}
  const conditions={reception_type:$('reception-type').value,business_stage:$('business-stage').value};
  lock(true);const userBubble=bubble(text,'user');$('input').value='';if($('input-count'))$('input-count').textContent='0 / 2000';$('input').style.height='46px';$('status').textContent='匹配 FAQ…';$('send').textContent='匹配中…';
  const pending=bubble('正在分析问题','pending');pending.setAttribute('role','status');
  const stages=['正在分析问题','正在检索资料','正在生成回复'];let stageIndex=0;
  const stageTimer=typeof setInterval==='function'?setInterval(()=>{stageIndex=Math.min(stageIndex+1,stages.length-1);pending.firstChild?.remove();pending.prepend(document.createTextNode(stages[stageIndex]+' '));},650):null;
  const dots=node('span',undefined,'typing-dots');dots.setAttribute('aria-hidden','true');for(let i=0;i<3;i++)dots.append(node('i'));pending.append(dots);
  try{
    const r=await api('/api/chat',{session_id:sid,message:text,...conditions});
    pending.remove();
    testFeedback(userBubble,r,text,conditions);
    if(r.send_to_customer){const parts=Array.isArray(r.answer_parts)&&r.answer_parts.length?r.answer_parts:[r.answer];parts.forEach((part,i)=>bubble(part,'assistant',r,{images:i===parts.length-1,edit:i===parts.length-1}));}
    else bubble(r.status==='duplicate'?'同类问题已回复，本次未重复发送。':r.status==='error'?'处理失败 · 查看测试助手':'暂未自动回复 · 查看测试助手','system',r);
    if(!r.send_to_customer && ['suppressed','handoff'].includes(r.status)){
      const waitingSid=sid,waitingEpoch=testEpoch;
      const waitingTimer=setTimeout(async()=>{waitingTimers.delete(waitingTimer);if(sid!==waitingSid||testEpoch!==waitingEpoch)return;try{const w=await api(`/api/sessions/${waitingSid}/waiting/${r.debug.request_id}`,{});if(w.send_to_customer&&testEpoch===waitingEpoch)bubble(w.answer,'assistant',r,{waiting:true,images:false,edit:false});}catch(e){if(sid===waitingSid&&testEpoch===waitingEpoch)$('status').textContent='等待提示失败，请客服查看';}},Math.max(0,(r.debug.waiting_delay_ms||3000)-r.debug.elapsed_ms));waitingTimers.add(waitingTimer);
    }
    showState(r.session);$('status').textContent=labels[r.status];setAssistTab('advice');trace(r);
    if(!r.send_to_customer&&['handoff','suppressed'].includes(r.status))loadRag(r);
  }catch(e){
    pending.remove();
    const failed={status:'error',session:{current_product_id:confirmedProduct},debug:{analysis:{status:'unrecognized',intents:[],method:'请求未完成',outcome:'请求失败，无法判断意图和知识是否可用；请确认本地服务后重试。',knowledge_url:'/knowledge'}}};
    testFeedback(userBubble,failed,text,conditions);
    failed.debug.analysis.error_type=e.name;trace(failed);
    bubble('请求失败 · 查看测试助手','system',failed);$('status').textContent='系统失败';
  }finally{pending.remove();lock(false);$('send').textContent='发送 ↗';$('input').focus?.();}
  if(stageTimer!==null&&typeof clearInterval==='function')clearInterval(stageTimer);
}
function openProductLink(){
 if(busy||!ready)return;
 const select=$('product-link-product');const empty=node('option','暂不关联，先发送链接');empty.value='';select.replaceChildren(empty);
 for(const p of products){const option=node('option',p.name);option.value=p.id;select.append(option);}
 select.value=$('product-select').value||'';
 $('product-link-url').value='';$('product-link-error').hidden=true;
 $('product-link-dialog').showModal();$('product-link-url').focus?.();
}
async function sendProductLink(){
 if(busy||!ready)return;
 const value=$('product-link-url').value.trim(),pid=$('product-link-product').value||null;
 if(!value&&!pid){$('product-link-error').textContent='请选择商品，或填写商品网址。';$('product-link-error').hidden=false;return;}
 try{if(value){const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||!u.hostname||/\s|\\/.test(value))throw Error();}}
 catch{$('product-link-error').textContent='请粘贴完整的 http 或 https 商品链接。';$('product-link-error').hidden=false;return;}
 lock(true);cancelWaiting();$('product-link-error').hidden=true;$('submit-product-link').textContent='发送中…';
 try{
  const r=await api(`/api/sessions/${sid}/events`,{type:'customer_link',url:value,product_id:pid});
  if(starterEl){starterEl.remove();starterEl=null;}
  renderProductCard(r);transcript.push({card:r});persistConversation();
  resetAssistant();showState(r.session);highlight($('product-select'));
  bubble(r.message,'system');$('status').textContent=r.status==='linked'?'商品已关联':'待确认商品';
  $('product-link-dialog').close();notify(r.status==='linked'?'商品卡片已发送并关联':'商品链接已发送，请确认商品');
 }catch(e){$('product-link-error').textContent='发送失败：'+e.message;$('product-link-error').hidden=false;}
 finally{lock(false);$('submit-product-link').textContent='发送到聊天 ↗';}
}
function renderProductCard(r){
  const card=node('article',undefined,'bubble user product-link-card'),heading=node('small','商品卡片'),name=node('strong',products.find(p=>p.id===r.link.product_id)?.name||'待关联商品');
  card.append(heading,name);
  if(r.link.url){const link=node('a',r.link.url);link.href=r.link.url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}
  card.append(node('span',r.status==='linked'?'已关联 · 后续咨询按此商品回答':'未关联 · 需要确认商品','link-card-state'));
  $('messages').append(card);followLatest(true);
}
if($('open-product-link')){
 $('open-product-link').onclick=openProductLink;
 for(const id of ['close-product-link','cancel-product-link'])$(id).onclick=()=>{if(!busy)$('product-link-dialog').close();};
 $('product-link-form').onsubmit=e=>{e.preventDefault();sendProductLink();};
 $('product-link-dialog').oncancel=e=>{if(busy)e.preventDefault();};
}

if($('tab-advice'))$('tab-advice').onclick=()=>setAssistTab('advice');
if($('tab-diagnostic'))$('tab-diagnostic').onclick=()=>setAssistTab('diagnostic');
if($('show-diagnostic'))$('show-diagnostic').onclick=()=>setAssistTab('diagnostic');
if($('input-count'))$('input').oninput=()=>{$('form').setAttribute('data-has-text',String(!!$('input').value.trim()));$('input-count').textContent=$('input').value.length+' / 2000';$('input').style.height='auto';$('input').style.height=Math.min(120,Math.max(46,$('input').scrollHeight||46))+'px';$('input').style.overflowY=$('input').scrollHeight>120?'auto':'hidden';};
if($('rag-copy'))$('rag-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('rag-suggestion').textContent);const button=$('rag-copy'),label=button.textContent;button.textContent='✓ 已复制';button.classList?.add('is-copied');setTimeout(()=>{button.textContent=label;button.classList?.remove('is-copied');},1600);notify('已复制，确认后可用于人工回复');}catch{notify('复制暂不可用，请选择话术手动复制');}};
if($('rag-search'))$('rag-search').onclick=()=>{if(selectedResult)loadRag(selectedResult);};
$('form').onsubmit=e=>{e.preventDefault();send($('input').value);};
$('input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('input').value);}};
$('clear-memory').onclick=()=>resetTest('memory');$('reset-test').onclick=()=>resetTest('test');
$('new').onclick=newSession;$('handled').onclick=()=>event('handled');
$('reconnect').onclick=connect;
$('product-select').onchange=async()=>{await event('customer_select',$('product-select').value || null);highlight($('product-select'));updateContextSummary();};
 $('reception-type').onchange=()=>{highlight($('reception-type'));updateContextSummary();notify('已切换为'+receptionLabels[$('reception-type').value]+' · 下一条咨询生效');};
 $('business-stage').onchange=()=>{$('stage-caption').textContent=stageLabels[$('business-stage').value];updateContextSummary();highlight($('business-stage'));notify('已切换为'+stageLabels[$('business-stage').value]+' · 下一条咨询生效');};
if($('context-collapsible'))$('context-collapsible').ontoggle=e=>{const a=e.currentTarget.querySelector('.context-summary-action');if(a)a.textContent=e.currentTarget.open?'收起设置⌃':'展开设置⌄';};
if($('toggle-inspect'))$('toggle-inspect').onclick=()=>{const panel=document.querySelector('.inspect');const open=!panel.classList.toggle('is-collapsed');$('toggle-inspect').setAttribute('aria-expanded',String(open));$('toggle-inspect').textContent=open?'收起':'展开';};
const commandActions=[
 {label:'切换商品',hint:'打开接待条件中的商品选择',run:()=>{$('context-collapsible')?.setAttribute('open','');$('product-select')?.focus();}},
 {label:'插入快捷话术：有优惠吗',hint:'写入当前输入框',run:()=>{$('input').value='有优惠吗';$('input').dispatchEvent(new Event('input'));$('input').focus();}},
 {label:'插入快捷话术：多久能到？',hint:'写入当前输入框',run:()=>{$('input').value='多久能到？';$('input').dispatchEvent(new Event('input'));$('input').focus();}},
 {label:'发送商品卡片',hint:'打开商品卡片窗口',run:()=>openProductLink()},
 {label:'查看客户资料',hint:'打开右侧接待助手',run:()=>{$('toggle-inspect')?.click();}},
 {label:'切换接待条件',hint:'展开商品、接待类型和业务状态',run:()=>{$('context-collapsible')?.setAttribute('open','');$('reception-type')?.focus();}},
 {label:'清除记忆',hint:'保留商品和接待条件',run:()=>resetTest('memory')}
];
function openCommandPalette(){const d=$('command-palette');if(!d)return;renderCommands('');d.showModal();setTimeout(()=>$('command-search')?.focus(),0);}
function renderCommands(query){const list=$('command-list');if(!list)return;const q=(query||'').trim().toLowerCase();list.replaceChildren();commandActions.filter(a=>!q||a.label.toLowerCase().includes(q)||a.hint.toLowerCase().includes(q)).forEach((a,i)=>{const b=document.createElement('button');b.type='button';b.className='command-item';b.dataset.index=i;b.setAttribute('role','option');b.append(node('strong',a.label),node('small',a.hint));b.onclick=()=>{$('command-palette').close();a.run();};list.append(b);});const first=list.querySelector('button');first?.classList.add('is-active');}
if($('command-palette')){$('command-search').oninput=e=>renderCommands(e.target.value);$('command-palette').onkeydown=e=>{if(e.key==='Escape'){$('command-palette').close();return;}const buttons=[...$('command-list').querySelectorAll('button')];if(!buttons.length)return;let index=buttons.findIndex(b=>b.classList.contains('is-active'));if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();index=(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons.forEach(b=>b.classList.remove('is-active'));buttons[index].classList.add('is-active');buttons[index].scrollIntoView({block:'nearest'});}if(e.key==='Enter'){e.preventDefault();buttons[index].click();}};}
document.addEventListener?.('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommandPalette();}});

if($('new-replies')){$('new-replies').onclick=()=>followLatest(true);$('messages').onscroll=()=>{if(nearLatest())$('new-replies').hidden=true;};}
if($('send-card'))$('send-card').onclick=()=>{const id=$('candidate-select')?.value;if(id)event('agent_card',id);else bubble('请先选择候选商品。','system');};
document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>send(b.dataset.question));
async function connect(){
  if(busy)return;
  ready=false;lock(true);$('reconnect').hidden=true;
  $('mode').textContent='连接中';$('connection-note').textContent='正在读取商品和建立测试会话…';
  try{
    const previous=$('product-select').value;
    products=await api('/api/products');
    if(!Array.isArray(products))throw new Error('商品资料格式异常，请重新连接。');
    for(const id of ['product-select','candidate-select']){
      const select=$(id);
      // 候选发卡是可选工具，不让它阻塞主商品选择。
      if(!select)continue;
      select.replaceChildren();
      const placeholder=document.createElement('option');placeholder.value='';
      placeholder.textContent=id==='product-select'?'未确认商品':'请选择候选商品';select.append(placeholder);
      for(const p of products){
        const option=document.createElement('option');option.value=p.id;
        option.textContent=p.name;select.append(option);
      }
    }
    const selected=products.some(p=>p.id===previous)?previous:'';
    const saved=rememberedConversation();
    if(saved)await restoreConversation(saved);else await createSession(selected);
    ready=true;$('mode').textContent='● 服务正常';
    $('connection-note').textContent='已连接本地服务';
    // 状态展示失败不应阻止创建会话和选择商品。
    api('/api/health').then(health=>{
      if(!ready)return;
      access={public_demo:!!health.deployment?.public_demo,can_manage:health.deployment?!!health.deployment.can_manage:true};
      for(const id of ['knowledge-nav','review-nav','materials-nav','consultations-nav'])if($(id))$(id).hidden=!access.can_manage;
      if($('access-label'))$('access-label').textContent=access.can_manage?(access.public_demo?'管理员模式':'本地管理'):'访客体验';
      if($('admin-entry')){const entry=$('admin-entry');entry.textContent=access.can_manage?'管理后台':'管理员登录';entry.href=access.can_manage?'/knowledge':'/admin';entry.title=access.can_manage?'进入知识库、资料库和数据看板':'登录后可管理知识库、资料库和数据看板';}
      if($('experience-nav'))$('experience-nav').hidden=access.can_manage;if($('statistics-nav')){$('statistics-nav').hidden=false;$('statistics-nav').href=access.can_manage?'/statistics':'/experience/statistics';}
      $('connection-note').textContent=access.public_demo?'在线体验 · 各设备会话独立':'已连接本地服务';
      if(selectedResult)trace(selectedResult);
      $('mode').title=(health.mode==='mock'?'本地测试模式':'模型 API 已配置')+(health.semantic==='ready'?' · 语义检索就绪':' · 基础检索');
    }).catch(()=>{if(ready)$('mode').textContent='● 已连接 · 状态信息暂不可用';});
  }catch(e){connectionFailed(`工作台连接失败：${e.message}`);}
  finally{lock(false);}
}
connect().then(async()=>{const key=new URLSearchParams(window.location.search).get('retest');const context=key&&TestContext.read(key);if(!context||!ready)return;$('reception-type').value=context.reception_type||'presales';$('business-stage').value=context.business_stage||'presales';if(context.product_id)await event('customer_select',context.product_id);bubble('重新测试原问题 · 修改前：'+(context.analysis?.outcome||context.previous_status||'未记录'),'system');await send(context.question);});
window.addEventListener?.('pagehide',persistConversation);
window.addEventListener?.('visibilitychange',persistConversation);
