const $=id=>document.getElementById(id);
const reviewMode=document.body.dataset.knowledgeView==='review';
let queuePage=1;
let data=null,sceneType='industry',page=1,currentSceneId=null,editing=null,editingScene=null,selectedImages=[],dirty=false,sceneDirty=false;
const pageSize=12;
let initialFiltersApplied=false;
function applyInitialFilters(){if(initialFiltersApplied)return;initialFiltersApplied=true;const p=new URLSearchParams(window.location.search);if(p.get('status')==='needs_review')$('status').value='needs_review';if(data.products.some(v=>v.id===p.get('product')))$('product-filter').value=p.get('product');}
function showReviewQueue(){window.location.assign('/review');}
const states={active:'已启用',needs_review:'待审核',manual_policy:'人工处理',disabled:'已停用'};
const scopes={product:'指定商品',store:'店铺通用',catalog:'跨款推荐'};
const sceneTypes={industry:'客户意图',special:'特殊场景',custom:'自定义场景'};
const receptions={all:'全部接待',presales:'售前接待',aftersales:'售后接待'};
const stages={presales:'售前',shipping:'发货中',received:'发货后',aftersales:'售后'};
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function message(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
async function api(url,options={}){const r=await fetch(url,options);let v;try{v=await r.json();}catch{throw new Error('服务暂时不可用，请检查本地服务是否正在运行。');}if(!r.ok)throw new Error(typeof v.detail==='string'?v.detail:v.answer||'操作失败，请稍后重试。');return v;}
function imageElement(asset){const img=node('img');img.src=asset.url;img.alt=asset.alt||'知识库配图';img.loading='lazy';return img;}
function addImages(container,assets=[]){container.replaceChildren();container.className='images';for(const asset of assets){if(!asset.url?.startsWith('/static/images/'))continue;const a=node('a');a.href=asset.url;a.target='_blank';a.rel='noopener';a.append(imageElement(asset));container.append(a);}}
function productName(id){return data.products.find(p=>p.id===id)?.name||id;}
function dateLabel(value,withTime=false){if(!value)return '';const d=new Date(value);return Number.isNaN(d.valueOf())?value:d.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',...(withTime?{hour:'2-digit',minute:'2-digit'}:{})});}
function rangeLabel(r){return r.scope==='product'?(r.product_ids||[]).map(productName).join('、')||'未绑定商品':scopes[r.scope]||'未设置范围';}
function records(){return data.scenes.flatMap(s=>s.answers||[]);}
function currentScene(){return data?.scenes.find(s=>s.id===currentSceneId);}
function lines(value){return [...new Set(value.split('\n').map(s=>s.trim()).filter(Boolean))];}
// 场景负责共用问法；每条答案单独保留商品、接待和生效条件。
function conditions(row){return {reception:'presales',stages:['presales'],valid_from:null,valid_until:null,...row.conditions};}
function conditionLabels(row){const c=conditions(row);const labels=[rangeLabel(row),receptions[c.reception]||'全部接待',c.stages.length?c.stages.map(s=>stages[s]||s).join(' / '):'全部业务状态'];labels.push(c.valid_from||c.valid_until?`${c.valid_from?dateLabel(c.valid_from,true):'不限开始'} 至 ${c.valid_until?dateLabel(c.valid_until,true):'不限结束'}`:'全时间段');return labels;}
function applySavedAnswer(result){
 if(!data||!result.record||!result.revision)return false;
 const row=result.record,target=data.scenes.find(s=>s.id===row.scene_id);if(!target)return false;
 for(const scene of data.scenes)scene.answers=(scene.answers||[]).filter(r=>r.id!==row.id);
 target.answers.push(row);data.revision=result.revision;if(Array.isArray(result.covered_drafts))data.covered_drafts=result.covered_drafts;
 renderFilters();render();renderDetail();return true;
}
async function load(){try{const value=await api('/api/scenes');data={...value,scenes:value.scenes||[],products:value.products||[]};renderFilters();applyInitialFilters();render();if(currentSceneId&&!currentScene())currentSceneId=null;renderDetail();applyTestContext();message('已读取本地问答知识库。');}catch(e){message(e.message,true);$('result-count').textContent='知识库读取失败';}}
function renderFilters(){
 const rows=records();$('review-count').textContent=rows.filter(r=>r.status==='needs_review').length;$('total').textContent=data.scenes.length;$('active').textContent=rows.filter(r=>r.status==='active').length;$('review').textContent=rows.filter(r=>r.status==='needs_review').length;$('pictured').textContent=rows.filter(r=>(r.images||[]).length).length;
 const oldProduct=$('product-filter').value;$('product-filter').replaceChildren(new Option('全部商品与通用答案',''));for(const p of data.products)$('product-filter').add(new Option(p.name,p.id));$('product-filter').add(new Option('店铺通用','store'));$('product-filter').add(new Option('跨款推荐','catalog'));$('product-filter').value=oldProduct;
 const cats=[...new Set(data.scenes.map(s=>s.category).filter(Boolean))].sort(),oldCategory=$('category').value;$('category').replaceChildren(new Option('全部业务分类',''));$('categories').replaceChildren();for(const c of cats){$('category').add(new Option(c,c));$('categories').append(new Option(c,c));}$('category').value=oldCategory;
 for(const [type,title]of Object.entries(sceneTypes)){const tab=$('tab-'+type);tab.firstChild.textContent=title+' ';tab.querySelector('span').textContent=data.scenes.filter(s=>s.type===type).length;tab.setAttribute('aria-selected',sceneType===type);}
}
function variantList(variants){const list=node('ul',undefined,'variant-list');for(const text of variants)list.append(node('li',text));return list;}
function appendSceneSummary(card,scene,answers){
 const variants=[...new Set(scene.question_variants||[])].filter(text=>text.trim()!==scene.name.trim());
 const questions=node('div',undefined,'scene-meta'),examples=node('div',undefined,'question-examples');
 for(const text of variants.slice(0,3)){const item=node('span',text,'question-example');item.title=text;examples.append(item);}
 if(!variants.length)examples.append(node('span','已支持标准问题','muted'));
 questions.append(node('span','拓展问法','meta-label'),examples);card.append(questions);
 if(variants.length>3){const more=node('details',undefined,'variant-more');more.append(node('summary',`查看全部 ${variants.length} 种拓展问法`),variantList(variants));card.append(more);}
 const ranges=[...new Set(answers.map(rangeLabel))],range=node('div',undefined,'scene-meta');
 range.append(node('span','适用商品','meta-label'),node('span',ranges.length?ranges.join(' · '):'尚未配置条件答案'));card.append(range);
}
function renderDetailVariants(scene){
 const container=$('detail-variants');container.replaceChildren();
 if(scene.description)container.append(node('p',scene.description));
 const variants=[...new Set(scene.question_variants||[])],more=node('details');
 more.open=variants.length<=3;more.append(node('summary',`拓展问法 · ${variants.length} 种`),variantList(variants));container.append(more);
}
function answerMatches(r){const p=$('product-filter').value,status=$('status').value,rec=$('reception-filter').value,stage=$('stage-filter').value,c=conditions(r);return (!status||r.status===status)&&(!p||(p==='store'||p==='catalog'?r.scope===p:r.scope!=='product'||(r.product_ids||[]).includes(p)))&&(!rec||c.reception==='all'||c.reception===rec)&&(!stage||!c.stages.length||c.stages.includes(stage));}
function visible(){const q=$('search').value.trim().toLowerCase(),category=$('category').value;return data.scenes.filter(s=>{if(s.type!==sceneType||category&&s.category!==category)return false;const matching=(s.answers||[]).filter(answerMatches),hasAnswerFilters=['product-filter','status','reception-filter','stage-filter'].some(id=>$(id).value);if(hasAnswerFilters&&!matching.length)return false;return !q||[s.name,...s.question_variants||[],s.category,...matching.flatMap(r=>[r.standard_answer,...r.keywords||[]])].join(' ').toLowerCase().includes(q);});}
function render(){
 if(!data)return;if(reviewMode){renderReviewQueue();return;}for(const id of ['knowledge-nav','review-nav']){const link=$(id);if(!link)continue;const selected=id==='knowledge-nav';if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}$('review-guide').hidden=$('status').value!=='needs_review';const rows=visible(),pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.min(page,pages);$('records').replaceChildren();$('result-count').textContent=`共 ${rows.length} 个${sceneTypes[sceneType]} · 点击进入查看条件答案`;
 for(const s of rows.slice((page-1)*pageSize,page*pageSize)){const card=node('article',undefined,'scene-card'),top=node('div',undefined,'card-top'),info=node('div'),title=node('button',s.name,'scene-title');title.onclick=()=>openDetail(s.id);info.append(title);const badges=node('div',undefined,'badges'),answers=s.answers||[];badges.append(node('span',s.category||'未分类','badge'),node('span',`${answers.length} 条答案`,'badge'),node('span',`${answers.filter(r=>r.status==='active').length} 条启用`,'badge'));info.append(badges);const reviewing=$('status').value==='needs_review';const view=node('button',reviewing?'审核答案 →':'查看答案 →','quiet');view.onclick=()=>{openDetail(s.id);const pending=answers.filter(r=>r.status==='needs_review');if(reviewing&&pending.length===1)openEditor(pending[0]);};top.append(info,view);card.append(top);appendSceneSummary(card,s,answers);$('records').append(card);}
 if(!rows.length)$('records').append(node('div','暂无符合条件的场景。你可以调整筛选条件，或新建客户意图。','empty'));$('page-label').textContent=`${page} / ${pages}`;$('prev').disabled=page===1;$('next').disabled=page===pages;
}
function openDetail(id){currentSceneId=id;renderDetail();$('scene-detail').scrollIntoView({block:'start',behavior:'smooth'});}
function renderDetail(){if(reviewMode)return;const s=currentScene();$('scene-list').hidden=!!s;$('scene-detail').hidden=!s;if(!s)return;$('detail-title').textContent=s.name;renderDetailVariants(s);$('detail-badges').replaceChildren(node('span',sceneTypes[s.type]||'客户意图','badge'),node('span',s.category||'未分类','badge'));const answers=s.answers||[],covered=coveredFor(s.id);$('cleanup-drafts').hidden=!covered.length;$('cleanup-drafts').textContent=`清理已覆盖草稿（${covered.length}）`;$('answer-count').textContent=`共 ${answers.length} 条条件答案 · 展示此场景的全部答案`;$('answers').replaceChildren();for(const r of answers){const card=node('article',undefined,'faq-card'),top=node('div',undefined,'card-top'),info=node('div');info.append(node('h3',rangeLabel(r),'card-title'));const badges=node('div',undefined,'badges');badges.append(node('span',states[r.status]||r.status,'badge'+(r.status!=='active'?' review':'')));for(const text of conditionLabels(r).slice(1))badges.append(node('span',text,'badge'));info.append(badges);const edit=node('button',r.status==='needs_review'?'审核答案':'编辑答案','quiet');edit.onclick=()=>openEditor(r);const actions=node('div',undefined,'answer-actions'),remove=node('button','删除答案','danger quiet');remove.type='button';remove.onclick=()=>requestDelete('answer',r);actions.append(edit,remove);top.append(info,actions);card.append(top,node('div',r.standard_answer||'暂无标准答案，等待人工核实。','answer'));if((r.keywords||[]).length)card.append(node('p',`关键词（${r.keyword_mode==='all'?'全部命中':'任意命中'}）：${r.keywords.join(' / ')}`,'question'));if(r.answer_product_id&&r.scope!=='product')card.append(node('p','介绍 / 推荐：'+productName(r.answer_product_id),'question'));const images=node('div');addImages(images,r.images);card.append(images,node('div',`优先级 ${r.priority||0}${r.updated_at?' · 更新 '+dateLabel(r.updated_at):''}`,'card-id'));if(covered.some(item=>item.id===r.id))card.append(node('p','已有启用答案覆盖这条空白草稿，可确认后清理。','covered-hint'));if(r.review_note)card.append(node('p','核对备注：'+r.review_note,'question'));if(r.sources?.length){const sources=node('details',undefined,'answer-sources');sources.append(node('summary','查看原始参考与来源'));for(const source of r.sources){sources.append(node('p',[source.file,source.sheet,source.cell,source.excerpt].filter(Boolean).join(' · '),'muted'));}card.append(sources);}$('answers').append(card);}if(!answers.length)$('answers').append(node('div','场景已建好。添加一条答案，设置它适用的商品和接待条件。','empty'));}
function allImages(){const map=new Map();for(const r of records())for(const a of r.images||[])if(a.url?.startsWith('/static/images/'))map.set(a.url,a);return [...map.values()];}
function renderPicker(){addImages($('edit-images'),selectedImages);$('image-picker').replaceChildren();for(const asset of allImages()){const chosen=selectedImages.some(a=>a.url===asset.url),b=node('button',undefined,'pick'+(chosen?' chosen':''));b.type='button';b.setAttribute('aria-pressed',chosen);b.title=asset.alt||'知识库配图';b.append(imageElement(asset),node('span',asset.alt||'知识库配图'));b.onclick=()=>{selectedImages=chosen?selectedImages.filter(a=>a.url!==asset.url):[...selectedImages,asset];dirty=true;renderPicker();};$('image-picker').append(b);}if(!$('image-picker').children.length)$('image-picker').append(node('p','当前没有可选图片。','muted'));}
function openSceneEditor(scene=null){editingScene=scene?structuredClone(scene):null;sceneDirty=false;$('scene-editor-title').textContent=scene?'编辑意图与拓展问法':'新建客户意图';$('scene-name').value=scene?.name||'';$('scene-type').value=scene?.type||sceneType;$('scene-category').value=scene?.category||'商品咨询';$('scene-variants').value=(scene?.question_variants||[]).join('\n');$('scene-description').value=scene?.description||'';$('scene-save-note').textContent='';$('scene-editor').showModal();}
// 表单统一按北京时间展示和保存，避免浏览器所在时区改变活动时间。
function localTime(value){if(!value)return '';const d=new Date(value);if(Number.isNaN(d.valueOf()))return '';return new Date(d.getTime()+8*60*60*1000).toISOString().slice(0,16);}
function updateScope(){const scope=$('scope').value;$('product-binding').hidden=scope!=='product';$('owner-field').hidden=scope!=='catalog';$('scope-note').textContent=scope==='product'?'仅当当前咨询商品属于勾选范围时，这条答案才可触发。':scope==='store'?'所有商品共用这条答案，不改变当前咨询商品。':'用于推荐其他款式，不改变当前咨询商品。';}
function updateTimeMode(){const range=document.querySelector('input[name="time-mode"]:checked').value==='range';$('validity-fields').hidden=!range;}
function answerParts(){return [...$('answer-parts').children].map(row=>row.children[1].value.trim());}
function numberAnswerParts(){[...$('answer-parts').children].forEach((row,i)=>{row.children[0].children[0].textContent=`第 ${i+1} 条`;row.children[1].setAttribute('aria-label',`第 ${i+1} 条标准回复`);});$('add-answer-part').disabled=$('answer-parts').children.length>=8;}
function addAnswerPart(value=''){const container=$('answer-parts');if(container.children.length>=8)return;const row=node('div',undefined,'reply-part'),top=node('div',undefined,'reply-part-heading'),label=node('label'),remove=node('button','删除','text-button'),text=node('textarea');remove.type='button';text.rows=4;text.maxLength=4000;text.value=value;text.placeholder='填写希望发给客户的原话';remove.onclick=()=>{if(container.children.length===1)text.value='';else row.remove();dirty=true;numberAnswerParts();};top.append(label,remove);row.append(top,text);container.append(row);numberAnswerParts();}
// 编辑时复制原记录，保存时保留来源和图片等已有资料，只更新表单中的维护项。
function updateProductSummary(){
 const checked=[...$('product-options').querySelectorAll('input:checked')];
 $('product-selection-summary').textContent=checked.length?`已选 ${checked.length} 款：${checked.map(input=>productName(input.value)).join('、')}`:'尚未选择商品';
 for(const input of $('product-options').querySelectorAll('input'))input.parentElement.classList.toggle('selected',input.checked);
}
function filterProductChoices(){const q=$('product-search').value.trim().toLowerCase();for(const label of $('product-options').children)label.hidden=!!q&&!label.textContent.toLowerCase().includes(q)&&!label.querySelector('input').value.toLowerCase().includes(q);}
function updateReviewActions(){
 const pending=$('edit-status').value==='needs_review';
 $('approve-answer').hidden=!pending;
 $('save').classList.toggle('quiet',pending);
 $('save').textContent=({active:'保存并启用',needs_review:'保存为待审核',manual_policy:'保存为人工处理',disabled:'保存并停用'})[$('edit-status').value]||'保存配置';
}
function savedAnswerMessage(row){
 if(document.body?.dataset?.knowledgeEmbed==='true')window.parent.postMessage({type:'pac-editor-saved'},window.location.origin);
 return ({active:'答案已启用，符合商品和接待条件时可自动回复。',needs_review:'已保存为待审核，尚未启用；确认后请点击“审核并启用”。',manual_policy:'已保存为人工处理，不会自动回复。',disabled:'答案已停用，不会自动回复。'})[row.status]||'答案已保存。';
}
function openEditor(row){const scene=currentScene();if(!scene)return;editing=row?structuredClone(row):null;selectedImages=structuredClone(row?.images||[]);dirty=false;$('editor-title').textContent=row?'编辑条件答案':'添加条件答案';$('answer-scene-name').textContent='所属客户意图：'+scene.name;$('edit-status').value=row?.status||'needs_review';$('scope').value=row?.scope||'product';$('product-search').value='';$('answer-parts').replaceChildren();for(const part of row?.answer_parts?.length?row.answer_parts:[row?.standard_answer||''])addAnswerPart(part);
 const selected=row?.product_ids||[],preferred=$('product-filter').value;$('product-options').replaceChildren();for(const p of data.products){const label=node('label'),input=node('input');input.type='checkbox';input.value=p.id;input.checked=selected.includes(p.id)||!row&&p.id===preferred;label.append(input,document.createTextNode(p.name));$('product-options').append(label);}$('owner').replaceChildren(new Option('不指定',''));for(const p of data.products)$('owner').add(new Option(p.name,p.id));$('owner').value=row?.answer_product_id||'';const c=conditions(row||{});$('reception').value=c.reception;for(const input of $('stage-options').querySelectorAll('input'))input.checked=c.stages.includes(input.value);document.querySelector(`input[name="time-mode"][value="${c.valid_from||c.valid_until?'range':'all'}"]`).checked=true;$('valid-from').value=localTime(c.valid_from);$('valid-until').value=localTime(c.valid_until);$('keywords').value=(row?.keywords||[]).join('\n');$('keyword-mode').value=row?.keyword_mode||'any';$('priority').value=row?.priority||0;$('sources').textContent=JSON.stringify({来源:row?.sources||[],边界:row?.boundaries||{}},null,2);$('save-note').textContent='';updateProductSummary();$('product-binding').open=!$('product-options').querySelectorAll('input:checked').length;updateReviewActions();updateScope();updateTimeMode();renderPicker();$('editor').showModal();$('editor').querySelector('.editor-scroll').scrollTop=0;}
function closeEditor(){if($('save').disabled)return;if(dirty&&!confirm('还有未保存的答案修改，确定关闭吗？'))return;dirty=false;$('editor').close();}
function closeSceneEditor(){if($('save-scene').disabled)return;if(sceneDirty&&!confirm('还有未保存的场景修改，确定关闭吗？'))return;sceneDirty=false;$('scene-editor').close();}
$('edit-form').addEventListener('input',event=>{if(event.target.id!=='product-search')dirty=true;});$('scene-form').addEventListener('input',()=>{sceneDirty=true;});
$('scene-form').addEventListener('submit',async e=>{e.preventDefault();const scene={...(editingScene?{id:editingScene.id}:{}),name:$('scene-name').value.trim(),type:$('scene-type').value,category:$('scene-category').value.trim(),question_variants:lines($('scene-variants').value),description:$('scene-description').value.trim()};if(!scene.question_variants.length){$('scene-save-note').textContent='请至少填写一个客户问法。';return;}$('save-scene').disabled=true;$('scene-save-note').textContent='正在保存客户意图…';try{const result=await api('/api/scenes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:data.revision,scene})});sceneDirty=false;$('scene-editor').close();sceneType=scene.type;currentSceneId=result.scene.id;await load();message(result.message||'客户意图已保存，可继续维护条件答案。');}catch(error){$('scene-save-note').textContent=error.message;}finally{$('save-scene').disabled=false;}});
$('add-answer-part').onclick=()=>{addAnswerPart();dirty=true;};
$('edit-form').addEventListener('submit',async e=>{e.preventDefault();if(answerParts().some(part=>!part)&&answerParts().length>1){$('save-note').textContent='请填完每条回复，或删除空白条目。';return;}const scene=currentScene(),scope=$('scope').value,owner=$('owner').value,productIds=[...$('product-options').querySelectorAll('input:checked')].map(el=>el.value),isRange=document.querySelector('input[name="time-mode"]:checked').value==='range',from=$('valid-from').value,until=$('valid-until').value;if(scope==='product'&&!productIds.length){$('save-note').textContent='请至少绑定一个商品。';return;}if(isRange&&!from&&!until){$('save-note').textContent='请填写有效时间，或选择全时间段。';return;}if(isRange&&from&&until&&from>=until){$('save-note').textContent='结束时间需要晚于开始时间。';return;}const record={...(editing||{}),scene_id:scene.id,standard_answer:answerParts().join('\n\n'),answer_parts:answerParts().filter(Boolean),status:e.submitter?.id==='approve-answer'?'active':$('edit-status').value,scope,product_ids:scope==='product'?productIds:[],answer_product_id:scope==='store'?null:scope==='product'?(productIds.includes(owner)?owner:productIds[0]):owner||null,images:selectedImages,conditions:{reception:$('reception').value,stages:[...$('stage-options').querySelectorAll('input:checked')].map(el=>el.value),valid_from:isRange&&from?from+':00+08:00':null,valid_until:isRange&&until?until+':00+08:00':null},keywords:lines($('keywords').value),keyword_mode:$('keyword-mode').value,priority:Number($('priority').value)||0};$('save').disabled=true;$('approve-answer').disabled=true;$('save-note').textContent=record.status==='active'?'正在保存并启用…':'正在保存配置…';try{const result=await api('/api/faq',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:data.revision,record})});dirty=false;$('editor').close();if(!applySavedAnswer(result))await load();message(savedAnswerMessage(result.record||record));}catch(error){$('save-note').textContent=error.message;}finally{$('save').disabled=false;$('approve-answer').disabled=false;}});
for(const id of ['search','status','category','product-filter','reception-filter','stage-filter'])$(id).addEventListener(id==='search'?'input':'change',()=>{page=1;render();});for(const tab of document.querySelectorAll('[data-type]'))tab.onclick=()=>{sceneType=tab.dataset.type;currentSceneId=null;page=1;renderFilters();render();renderDetail();};$('prev').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};$('review-queue').onclick=showReviewQueue;if($('review-stat')){$('review-stat').onclick=showReviewQueue;$('review-stat').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showReviewQueue();}};}$('refresh').onclick=load;$('add-scene').onclick=()=>openSceneEditor();$('edit-scene').onclick=()=>openSceneEditor(currentScene());$('back').onclick=()=>{currentSceneId=null;renderDetail();};$('add-answer').onclick=()=>openEditor(null);$('close').onclick=closeEditor;$('cancel').onclick=closeEditor;$('close-scene').onclick=closeSceneEditor;$('cancel-scene').onclick=closeSceneEditor;$('scope').onchange=updateScope;$('edit-status').onchange=updateReviewActions;for(const radio of document.querySelectorAll('input[name="time-mode"]'))radio.onchange=updateTimeMode;$('editor').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});$('scene-editor').addEventListener('cancel',e=>{e.preventDefault();closeSceneEditor();});window.addEventListener('beforeunload',e=>{if(dirty&&$('editor').open||sceneDirty&&$('scene-editor').open){e.preventDefault();e.returnValue='';}});
let contextApplied=false;
function applyTestContext(){
 const params=new URLSearchParams(window.location.search),key=params.get('test'),context=key&&TestContext.read(key),banner=$('test-context');
 const openRequested=!contextApplied;
 if(!contextApplied){
  const selected=data.scenes.find(s=>s.id===params.get('scene'));
  if(selected){sceneType=selected.type;currentSceneId=selected.id;renderFilters();render();renderDetail();}
  contextApplied=true;
 }
 if(!context){
  banner.hidden=!key;if(key)banner.replaceChildren(node('p','测试上下文已过期。你仍可在知识库查找和维护答案。'));
  // 编辑既有答案不依赖原问题仍在本机缓存；只按已存在的场景和答案定位。
  if(openRequested&&params.get('action')==='answer'&&currentScene()){
   const row=currentScene().answers.find(r=>r.id===params.get('answer'));
   if(row)openEditor(row);else message('来源答案已变更，请重新测试后再定位。',true);
  }
  return;
 }
 banner.hidden=false;banner.replaceChildren(node('h2','优化这条客户问题'),node('p','客户原话：'+context.question),node('p','测试商品：'+(context.product_id?productName(context.product_id):'未确认')+' · '+(receptions[context.reception_type]||'售前接待')+' / '+(stages[context.business_stage]||'售前')),node('p','原测试结果：'+(context.analysis?.outcome||'请求未完成')));
 const actions=node('div',undefined,'context-actions'),select=node('select');select.setAttribute('aria-label','纠正到客户意图');select.append(new Option('选择正确的客户意图…',''));
 for(const scene of data.scenes)select.append(new Option(scene.name,scene.id));select.value=currentSceneId||'';
 select.onchange=()=>{if(!select.value)return;currentSceneId=select.value;sceneType=currentScene().type;renderFilters();render();renderDetail();};actions.append(select);
 const variants=node('button','补充问法 / 纠正意图','quiet');variants.onclick=()=>{const target=currentScene();if(!target){message('请先选择正确的客户意图，再补充问法。',true);return;}openSceneEditor(target);const values=lines($('scene-variants').value);if(!values.includes(context.question))values.push(context.question);$('scene-variants').value=values.join('\n');sceneDirty=true;$('scene-save-note').textContent='请确认原话属于这个意图，再保存；不会自动归类。';};actions.append(variants);
 const answer=node('button','修改 / 补充答案','quiet');answer.onclick=()=>{const scene=currentScene();if(!scene){message('请先选择客户意图，或新建客户意图。',true);return;}const row=scene.answers.find(r=>r.id===params.get('answer'));openEditor(row||null);if(!row&&context.product_id){for(const input of $('product-options').querySelectorAll('input'))input.checked=input.value===context.product_id;}if(!row)$('reception').value=context.reception_type||'presales';for(const input of $('stage-options').querySelectorAll('input'))if(!row)input.checked=input.value===context.business_stage;};actions.append(answer);
 const create=node('button','新建客户意图','quiet');create.onclick=()=>{openSceneEditor();$('scene-name').value=context.question;$('scene-variants').value=context.question;sceneDirty=true;};actions.append(create);
 if(context.rag){
  const rag=context.rag,box=node('section',undefined,'rag-draft');box.append(node('h3','资料辅助草稿 · 待人工确认'),node('p',rag.suggestion||''));
  const title=typeof rag.proposed_intent==='string'?rag.proposed_intent:rag.proposed_intent?.name||rag.proposed_intent?.title||context.question;
  for(const source of rag.sources||[])box.append(node('small','来源：'+(source.title||source.id)+' · '+(typeof source.source==='string'?source.source:'已维护资料')));
  const draft=node('button','添加为待核实答案','quiet');draft.onclick=()=>{
   if(!currentScene()){message('先选择已有客户意图，或保存一个新客户意图，再添加草稿。',true);return;}
   openEditor(null);$('answer-parts').replaceChildren();addAnswerPart(rag.suggestion||'');$('edit-status').value='needs_review';
   $('scope').value=context.product_id?'product':'store';updateScope();
   for(const input of $('product-options').querySelectorAll('input'))input.checked=input.value===context.product_id;
   $('reception').value=context.reception_type||'presales';for(const input of $('stage-options').querySelectorAll('input'))input.checked=input.value===(context.business_stage||'presales');
   dirty=true;$('save-note').textContent='请核对建议、来源与适用条件；保存为待核实，不会自动回复客户。';
  };
  const draftScene=node('button','按建议新建意图','quiet');draftScene.onclick=()=>{openSceneEditor();$('scene-name').value=title.slice(0,200);$('scene-variants').value=context.question;sceneDirty=true;};
  const tools=node('div',undefined,'context-actions');tools.append(draft,draftScene);box.append(tools);banner.append(box);
 }

 const retry=node('a','重新测试原问题 →');retry.href='/?retest='+encodeURIComponent(key);retry.target='_blank';retry.rel='noopener';actions.append(retry);banner.append(actions,node('p','先确认归属，再保存修改；保存后点击重新测试，对照修改前的结果。测试原话只在本机浏览器暂存30分钟。'));
 // 测试助手的快捷入口仅预填编辑器，必须由训练者确认保存。
 if(openRequested){const action=params.get('action');if(action==='new')create.onclick();else if(action==='variant'&&currentScene())variants.onclick();else if(action==='answer'&&currentScene()){
  if(currentScene().answers.some(r=>r.id===params.get('answer')))answer.onclick();else message('来源答案已变更，请重新测试后再定位。',true);
 }}
}
let deleting=null;
function requestDelete(kind,row){
 deleting={kind,id:row.id};$('confirm-delete').textContent='确认删除';
 $('delete-title').textContent=kind==='scene'?'删除整个客户意图？':'删除这条条件答案？';
 $('delete-summary').textContent=kind==='scene'?`将删除“${row.name}”及其全部 ${row.answers.length} 条条件答案。`:`将删除“${currentScene().name}”下适用于“${rangeLabel(row)}”的这条答案；其他答案保留。`;
 $('delete-note').textContent='';$('delete-dialog').showModal();
}
function closeDelete(){if($('confirm-delete').disabled)return;deleting=null;$('delete-dialog').close();}
async function confirmDelete(){
 if(!deleting)return;
 const target=deleting;$('confirm-delete').disabled=true;$('cancel-delete').disabled=true;$('delete-note').textContent='正在删除…';
 try{
  const result=await api(target.kind==='cleanup'?'/api/faq/cleanup-covered':target.kind==='scene'?'/api/scenes/delete':'/api/faq/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:data.revision,...(target.kind==='cleanup'?{scene_id:target.id,ids:target.ids}:{id:target.id}),confirmed:true})});
  const removed=new Set(result.deleted_ids);
  for(const scene of data.scenes)scene.answers=scene.answers.filter(row=>!removed.has(row.id));
  if(result.deleted_scene_id){data.scenes=data.scenes.filter(scene=>scene.id!==result.deleted_scene_id);if(currentSceneId===result.deleted_scene_id)currentSceneId=null;}
  data.revision=result.revision;if(Array.isArray(result.covered_drafts))data.covered_drafts=result.covered_drafts;deleting=null;$('delete-dialog').close();renderFilters();render();renderDetail();message(result.message);
 }catch(error){$('delete-note').textContent=error.message;}
 finally{$('confirm-delete').disabled=false;$('cancel-delete').disabled=false;}
}
$('cancel-delete').onclick=closeDelete;$('confirm-delete').onclick=confirmDelete;
$('delete-dialog').addEventListener('cancel',event=>{event.preventDefault();closeDelete();});
$('delete-scene').onclick=()=>requestDelete('scene',currentScene());
function coveredFor(sceneId){return (data.covered_drafts||[]).filter(row=>row.scene_id===sceneId);}
function requestCleanup(scene,ids=null){
 const candidates=coveredFor(scene.id).filter(row=>!ids||ids.includes(row.id));if(!candidates.length)return;
 const rows=scene.answers.filter(row=>candidates.some(item=>item.id===row.id));
 deleting={kind:'cleanup',id:scene.id,ids:candidates.map(row=>row.id)};
 $('delete-title').textContent='清理已覆盖的空白草稿？';$('confirm-delete').textContent='确认清理';
 $('delete-summary').textContent=`将清理“${scene.name}”下 ${rows.length} 条空白草稿（${rows.map(rangeLabel).join('；')}）。已启用答案和其他草稿保留。`;
 $('delete-note').textContent='';$('delete-dialog').showModal();
}
function renderReviewQueue(){
 const rows=records().filter(row=>row.status==='needs_review'),covered=new Set((data.covered_drafts||[]).map(row=>row.id));
 $('queue-total').textContent=rows.length;$('queue-ready').textContent=rows.filter(row=>(row.standard_answer||'').trim()).length;$('queue-covered').textContent=rows.filter(row=>covered.has(row.id)).length;
 const old=$('queue-product').value;$('queue-product').replaceChildren(new Option('全部商品',''));for(const product of data.products)$('queue-product').add(new Option(product.name,product.id));$('queue-product').value=old;
 const q=$('queue-search').value.trim().toLowerCase(),product=$('queue-product').value,kind=$('queue-kind').value;
 const pending=rows.filter(row=>(!product||row.scope!=='product'||(row.product_ids||[]).includes(product))&&(!kind||kind==='covered'&&covered.has(row.id)||kind==='ready'&&(row.standard_answer||'').trim()||kind==='empty'&&!(row.standard_answer||'').trim())&&(!q||[row.scene_name,rangeLabel(row),row.standard_answer,row.review_note||''].join(' ').toLowerCase().includes(q)));
 pending.sort((a,b)=>Number(!!(b.standard_answer||'').trim())-Number(!!(a.standard_answer||'').trim()));
 const pages=Math.max(1,Math.ceil(pending.length/pageSize));queuePage=Math.min(queuePage,pages);$('queue-count').textContent=`共 ${pending.length} 条待审核答案 · 每条单独核对`;$('queue-page').textContent=`${queuePage} / ${pages}`;$('queue-prev').disabled=queuePage===1;$('queue-next').disabled=queuePage===pages;
 $('review-tasks').replaceChildren();
 for(const row of pending.slice((queuePage-1)*pageSize,queuePage*pageSize)){
  const card=node('article',undefined,'review-task'),top=node('div',undefined,'card-top'),info=node('div'),badge=node('span',covered.has(row.id)?'已被覆盖':(row.standard_answer||'').trim()?'已填待审':'缺少答案','task-state'+(covered.has(row.id)?' covered':''));
  info.append(node('h2',row.scene_name));top.append(info,badge);card.append(top,node('p',conditionLabels(row).join(' · '),'task-scope'),node('div',row.standard_answer||'尚未填写标准答案。','review-draft-preview'));
  if(covered.has(row.id))card.append(node('p','商品和接待条件已由启用答案覆盖，可清理这条空白草稿。','covered-hint'));
  if(row.sources?.length||row.review_note){const details=node('details');details.append(node('summary','查看来源与核对备注'));if(row.review_note)details.append(node('p',row.review_note));for(const source of row.sources||[])details.append(node('p',[source.file,source.sheet,source.cell].filter(Boolean).join(' · ')));card.append(details);}
  const actions=node('div',undefined,'review-task-actions'),edit=node('button',row.standard_answer?'编辑并审核':'补充答案并审核'),link=node('a','查看同意图答案','quiet');
  edit.type='button';edit.onclick=()=>{currentSceneId=row.scene_id;openEditor(row);};link.href='/knowledge?scene='+encodeURIComponent(row.scene_id);actions.append(edit,link);
  const remove=node('button',covered.has(row.id)?'清理空白草稿':'删除草稿','danger quiet');remove.type='button';remove.onclick=()=>{currentSceneId=row.scene_id;if(covered.has(row.id))requestCleanup(currentScene(),[row.id]);else requestDelete('answer',row);};actions.append(remove);card.append(actions);$('review-tasks').append(card);
 }
 if(!pending.length)$('review-tasks').append(node('div',rows.length?'没有符合筛选条件的审核任务。':'审核队列已清空。已启用答案可在知识库维护。','empty'));
}
$('cleanup-drafts').onclick=()=>requestCleanup(currentScene());
$('product-options').onchange=updateProductSummary;$('product-search').oninput=filterProductChoices;
$('product-binding').ontoggle=()=>{$('product-binding').querySelector('.product-expand-label').textContent=$('product-binding').open?'收起选择':'展开选择';};
$('select-dorm-products').onclick=()=>{for(const input of $('product-options').querySelectorAll('input'))input.checked=['801','802','803','804'].includes(input.value);dirty=true;updateProductSummary();};
$('clear-product-selection').onclick=()=>{for(const input of $('product-options').querySelectorAll('input'))input.checked=false;dirty=true;updateProductSummary();};
for(const id of ['queue-search','queue-product','queue-kind'])$(id).addEventListener(id==='queue-search'?'input':'change',()=>{queuePage=1;renderReviewQueue();});
$('queue-refresh').onclick=load;$('queue-prev').onclick=()=>{queuePage--;renderReviewQueue();};$('queue-next').onclick=()=>{queuePage++;renderReviewQueue();};
load();

if(document.body?.dataset?.knowledgeEmbed==='true')window.addEventListener('message',e=>{
 if(e.origin!==window.location.origin||e.source!==window.parent||e.data?.type!=='pac-editor-close-request')return;
 if($('save').disabled||$('save-scene').disabled){message('正在保存，请稍等。');return;}
 if((dirty&&$('editor').open||sceneDirty&&$('scene-editor').open)&&!confirm('有未保存的修改，确定关闭编辑面板吗？'))return;
 dirty=false;sceneDirty=false;window.parent.postMessage({type:'pac-editor-close'},window.location.origin);
});
