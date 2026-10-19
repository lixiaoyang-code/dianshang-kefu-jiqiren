let sid, products = [], busy = false, confirmedProduct = '';
const $ = id => document.getElementById(id);
const labels = {answered:'自动回答', clarify:'需要追问', handoff:'待客服查看', suppressed:'待客服查看', duplicate:'已答复 · 不重复发送', error:'系统失败'};
const receptionLabels = {presales:'售前接待', aftersales:'售后接待'};
const stageLabels = {presales:'售前', shipping:'发货中', received:'发货后', aftersales:'售后'};
async function api(path, data) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, {method:data === undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data === undefined?undefined:JSON.stringify(data),signal:controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.answer || result.detail || `HTTP ${response.status}`);
    return result;
  } finally { clearTimeout(timer); }
}
function showState(s) {
  $('session').textContent = `会话 ${s.session_id}`;
  confirmedProduct = s.current_product_id || '';
  $('product-select').value = confirmedProduct;
  $('current').textContent = products.find(p=>p.id===confirmedProduct)?.name || '尚未确认';
  $('candidates').textContent = `候选卡片：${(s.recent_product_ids || []).map(id=>products.find(p=>p.id===id)?.name || id).join('、') || '无'}`;
  // 接待条件保留用户当前选择，避免旧回复把下一条问题的条件改回去。
}
function bubble(text, role, result) {
  const el = document.createElement('div'); el.className = `bubble ${role} ${result?.status || ''}`;
  if(result){const tag=document.createElement('small');tag.textContent=labels[result.status];el.append(tag);el.tabIndex=0;el.onclick=()=>trace(result);el.onkeydown=e=>{if(e.key==='Enter')trace(result);};}
  el.append(document.createTextNode(text));
  if(result?.send_to_customer){for(const asset of result.images || []){const img=document.createElement('img');img.src=asset.url;img.alt=asset.alt;img.loading='lazy';img.style.cssText='display:block;max-width:100%;width:260px;height:auto;border-radius:8px;margin-top:10px';const link=document.createElement('a');link.href=asset.url;link.target='_blank';link.rel='noopener';link.title='点击查看原图';link.onclick=e=>e.stopPropagation();link.append(img);el.append(link);}}
  $('messages').append(el); $('messages').scrollTop=$('messages').scrollHeight;
}
function trace(r){const s=r.session;const conditions=[receptionLabels[s.reception_type],stageLabels[s.business_stage]].filter(Boolean).join(' / ');$('debug').textContent=JSON.stringify(r.debug,null,2);$('trace-summary').textContent=`${labels[r.status]} · 商品 ${s.current_product_id || '未确认'}${conditions?` · ${conditions}`:''} · ${r.debug.elapsed_ms} ms · ${r.debug.model}`;}
function lock(value){busy=value;document.querySelectorAll('button, aside select').forEach(control=>control.disabled=value);}
async function event(type, product_id){if(busy)return;lock(true);try{showState(await api(`/api/sessions/${sid}/events`,{type,product_id}));const product=products.find(p=>p.id===product_id);const text=type==='customer_select'&&!product_id?'客户商品已清除，当前尚未确认':({agent_card:'客服发送候选卡片',customer_select:'客户确认商品',takeover:'客服接管会话',resume:'客服恢复 AI',handled:'客服已处理，等待提示已取消'})[type]+(product_id?` · ${product?.name || product_id}`:'');bubble(text,'system');if(type==='resume')$('status').textContent='待接待';}catch(e){$('product-select').value=confirmedProduct;bubble(`操作失败：${e.message}`,'error');}finally{lock(false);}}
async function newSession(){if(busy)return;const product_id=$('product-select').value;lock(true);try{let s=await api('/api/sessions',{});sid=s.session_id;/* 新会话沿用测试条件，保留已选择的商品。 */if(product_id)s=await api(`/api/sessions/${sid}/events`,{type:'customer_select',product_id});$('messages').replaceChildren();$('debug').textContent='尚无检索记录';$('trace-summary').textContent='等待咨询';$('status').textContent='待接待';showState(s);bubble('新会话已就绪，按左侧条件发送客户问题即可。','system');}catch(e){bubble(`创建失败：${e.message}`,'error');}finally{lock(false);}}
async function send(text){if(busy||!text.trim())return;const conditions={reception_type:$('reception-type').value,business_stage:$('business-stage').value};lock(true);bubble(text,'user');$('input').value='';$('status').textContent='处理中…';try{const r=await api('/api/chat',{session_id:sid,message:text,...conditions});if(r.send_to_customer){bubble(r.answer,'assistant',r);}else if(r.status==='duplicate'){bubble('同类问题已回复，本次不重复发送（仅工作台提示）','system');}else{bubble('此条未自动回复，请客服查看（仅工作台提示）','system');const waitingSid=sid;setTimeout(async()=>{if(sid!==waitingSid)return;try{const w=await api(`/api/sessions/${waitingSid}/waiting/${r.debug.request_id}`,{});if(w.send_to_customer)bubble(w.answer,'assistant');}catch(e){$('status').textContent='等待提示失败，请客服查看';}},Math.max(0,25000-r.debug.elapsed_ms));}showState(r.session);$('status').textContent=labels[r.status];trace(r);}catch(e){bubble(`请求失败，需要人工查看：${e.message}。请确认服务仍在运行；恢复后可重新发送。`,'error');$('status').textContent='系统失败';}finally{lock(false);}}
$('form').onsubmit=e=>{e.preventDefault();send($('input').value);};
$('input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('input').value);}};
$('new').onclick=newSession;$('handled').onclick=()=>event('handled');
$('product-select').onchange=()=>event('customer_select',$('product-select').value || null);
$('send-card').onclick=()=>{const id=$('candidate-select').value;if(id)event('agent_card',id);else bubble('请先选择候选商品。','system');};
document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>send(b.dataset.question));
(async()=>{try{products=await api('/api/products');const health=await api('/api/health');$('mode').textContent=(health.mode==='mock'?'● Mock 本地模式':'● 模型 API 模式')+(health.semantic==='ready'?' · 语义检索就绪':' · 基础检索');for(const id of ['product-select','candidate-select']){for(const p of products){const option=document.createElement('option');option.value=p.id;option.textContent=`${p.name} · ${p.id}`;$(id).append(option);}}await newSession();}catch(e){$('mode').textContent='连接失败';bubble(e.message,'error');}})();
