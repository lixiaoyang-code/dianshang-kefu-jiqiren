const $=id=>document.getElementById(id);
let page=1,serial=0;
if(typeof location!=='undefined' && location.pathname==='/consultations'){$('outcome').value='pending';document.body.classList.add('consultation-page');$('page-title').textContent='咨询记录';$('page-description').textContent='从真实提问出发，补充知识，再验证一次。';$('statistics-link').removeAttribute('aria-current');$('consultations-link').setAttribute('aria-current','page');}
const statuses={answered:'已应答',clarify:'澄清追问',suppressed:'转人工',handoff:'转人工',error:'系统异常',duplicate:'重复抑制'};
const reasons={catalog_ineligible:'商品答案未启用或条件不符',catalog_ambiguous:'同一问题存在冲突答案',catalog_knowledge_missing:'当前商品缺少对应知识',catalog_review_required:'此问题需人工核实依据',insufficient_evidence:'缺少有效知识',presales_scope:'接待范围不符',scene_ineligible:'答案条件不符',scene_ambiguous:'答案冲突',manual_or_unsupported_request:'人工处理边界',system_failure:'系统异常',common_reception:'物流／售后需人工核实',affirmation_uncertain:'客户质疑需核实',product_unconfirmed:'未确认商品',answer_validation_failed:'答案核验未通过'};
function el(tag,text,cls){const v=document.createElement(tag);if(text!==undefined)v.textContent=text;if(cls)v.className=cls;return v;}
async function api(path,data){const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw Error(v.detail||'请求失败');return v;}
const pct=v=>v===null?'—':v.toFixed(1)+'%';
async function load(){
 const token=++serial;$('refresh').disabled=true;$('error').hidden=true;
 $('updated').textContent='正在刷新数据…';document.body.classList.add('is-loading');
 try{
  const q=new URLSearchParams({days:$('days').value,product:$('product').value,include_interactions:$('interactions').checked,outcome:$('outcome').value,page});
  const d=await api('/api/statistics?'+q);if(token!==serial)return;
  const c=d.counts,r=d.rates;
  $('pending-count').textContent=`待处理 ${c.pending||0} 条`;
  for(const [id,value] of [['queue-all',''],['queue-pending','pending'],['queue-handled','handled']])$(id).setAttribute('aria-pressed',String($('outcome').value===value));
  const previous=d.previous_rates||{};
  for(const id of ['response','handoff','intent','accuracy'])$(id).textContent=pct(r[id]);
  for(const id of ['response','handoff','intent','accuracy']){const card=$(id)?.closest('article');if(!card)continue;let delta=card.querySelector('.metric-delta');if(!delta){delta=el('small','', 'metric-delta');card.append(delta);}const p=previous[id];delta.textContent=p===undefined||p===null||r[id]===null?'':`${r[id]>=p?'↑':'↓'} ${Math.abs(r[id]-p).toFixed(1)}pp vs 上周期`;delta.classList.toggle('is-up',r[id]>=p);delta.classList.toggle('is-down',r[id]<p);}
  for(const id of ['response','handoff','intent','accuracy']){const c=$(id)?.closest('article');if(c&&Number(String($(id).textContent).replace('%',''))<20&&!c.querySelector('.sample-note'))c.append(el('small','样本较少','sample-note'));}
  $('response-count').textContent=`${c.responded} / ${c.total} 条 · 业务答复`;
  $('handoff-count').textContent=`${c.manual} / ${c.total} 条 · 转人工`;
  $('intent-count').textContent=`${c.recognized} / ${c.total} 条 · 明确意图`;
  $('accuracy-count').textContent=c.reviewed?`${c.correct} / ${c.reviewed} 条已评价 · 部分正确 ${c.partial}`:'暂无人工评价，暂不计算';
  $('volume').textContent=`有效消息 ${c.total} · 重复抑制 ${c.duplicates} · 澄清 ${c.clarifications} · 系统异常 ${c.errors}`;
  $('review-coverage').textContent=`评价覆盖率 ${pct(r.review_coverage)}`+(c.unknown_time?` · 历史未标时 ${c.unknown_time} 条`:'');
  $('updated').textContent='更新于 '+new Date().toLocaleTimeString('zh-CN');
  const trend=$('trend');trend.replaceChildren();const max=Math.max(1,...d.trend.map(v=>v.total));
  for(const v of d.trend){const row=el('div',undefined,'bar-row');row.tabIndex=0;row.setAttribute('role','img');const bar=el('div',undefined,'bar'),fill=el('b');bar.style.width=(v.total/max*100)+'%';fill.style.width=(v.total?v.responded/v.total*100:0)+'%';bar.append(fill);row.append(el('span',v.day.slice(5)),bar,el('span',v.total));row.title=`${v.day}：${v.total}条，已应答${v.responded}条，转人工${v.manual}条`;row.setAttribute('aria-label',row.title);trend.append(row);}
  if(!d.trend.length)trend.append(el('p','暂无带日期的业务记录','empty'));
  const rs=$('reasons');rs.replaceChildren();for(const v of d.reasons){const row=el('div',undefined,'reason');row.append(el('span',reasons[v.reason]||v.reason||'待核实'),el('strong',v.count+' 条'));rs.append(row);}if(!d.reasons.length)rs.append(el('p','当前范围暂无转人工或异常','empty'));
  const list=$('records');list.replaceChildren();
  for(const v of d.records){const row=el('article',undefined,'record'),top=el('div',undefined,'record-top');top.append(el('span',(v.occurred_at?new Date(v.occurred_at).toLocaleString('zh-CN'):'历史记录 · 时间未知')+' · '+(v.product_id||'通用咨询')),el('span',(statuses[v.status]||v.status)+(v.manual&&v.status==='answered'?' · 需人工继续处理':'')));row.append(top,el('h3',v.question));
   if(v.answer)row.append(el('p',v.answer,'answer'));
   const detail=el('details');detail.append(el('summary','诊断依据'),el('p',`意图：${v.intent||'未识别'} · 方式：${v.method||'—'} · 耗时：${v.elapsed} ms`),el('p','原因：'+(reasons[v.reason]||v.reason||'—')));row.append(detail);
   const actions=el('div',undefined,'record-actions');
   const improve=el('button','补充问法／答案 →');improve.type='button';improve.onclick=()=>{const key=TestContext.save({status:v.status,session:{current_product_id:v.product_id},debug:{request_id:v.id,analysis:{status:v.recognized?'matched':'unrecognized',intents:v.intents||[],outcome:reasons[v.reason]||v.reason||'待核实'}}},v.question,{reception_type:v.reception,business_stage:v.stage});if(key)location.href='/knowledge?test='+encodeURIComponent(key)+(v.intents?.length===1?'&scene='+encodeURIComponent(v.intents[0].id):'');else{$('error').textContent='无法保存跳转信息，请检查浏览器存储权限。';$('error').hidden=false;}};actions.append(improve);
   if(v.pending||v.handled_at){const b=el('button',v.handled_at?'重新打开':'标记已处理');b.type='button';b.onclick=async()=>{b.disabled=true;try{await api('/api/statistics/processing',{request_id:v.id,handled:!v.handled_at});await load();}catch(e){$('error').textContent=e.message;$('error').hidden=false;b.disabled=false;}};actions.append(b);actions.append(el('span',v.handled_at?'已处理 · '+new Date(v.handled_at).toLocaleDateString('zh-CN'):'待处理','muted'));}row.append(actions);
   if(v.responded){const controls=el('div',undefined,'review');controls.append(el('span','人工评价'));for(const [key,title] of [['correct','正确'],['partial','部分正确'],['incorrect','错误'],[null,'清除评价']]){const b=el('button',title);b.type='button';b.setAttribute('aria-pressed',String(v.review===key&&key!==null));b.onclick=async()=>{for(const other of controls.querySelectorAll('button'))other.disabled=true;try{await api('/api/statistics/review',{request_id:v.id,verdict:key});await load();}catch(e){$('error').textContent=e.message;$('error').hidden=false;for(const other of controls.querySelectorAll('button'))other.disabled=false;}};controls.append(b);}row.append(controls);}list.append(row);
  }
  if(!d.records.length)list.append(el('p','暂无记录。去咨询测试提问，或调整筛选范围。','empty'));
  $('record-count').textContent=`共 ${d.record_total} 条 · 第 ${page} 页`;$('previous').disabled=page===1;$('next').disabled=page*30>=d.record_total;
 }catch(e){if(token===serial){$('error').textContent='读取失败：'+e.message+'，请重试';$('error').hidden=false;}}finally{if(token===serial){$('refresh').disabled=false;document.body.classList.remove('is-loading');}}
}
for(const id of ['days','product','interactions','outcome'])$(id).onchange=()=>{page=1;load();};
for(const [id,value] of [['queue-all',''],['queue-pending','pending'],['queue-handled','handled']])$(id).onclick=()=>{$('outcome').value=value;page=1;load();};
$('refresh').onclick=()=>load();$('previous').onclick=()=>{if(page>1){page--;load();}};$('next').onclick=()=>{page++;load();};
async function start(){try{for(const p of await api('/api/products')){const o=el('option',p.name);o.value=p.id;$('product').append(o);}}catch(e){$('error').textContent=e.message;$('error').hidden=false;}await load();}start();
