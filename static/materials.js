const $=id=>document.getElementById(id);
const stageLabels={presales:'售前',shipping:'发货中',received:'发货后',aftersales:'售后'};
let snapshot=null,editing=null,dirty=false,saving=false;
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
async function api(path,data){const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.detail||result.answer||'请求未完成，请稍后重试。');return result;}
function notice(text){$('notice').textContent=text;}
function renderList(){
 const list=$('documents');list.replaceChildren();if(!snapshot)return;
 const q=$('search').value.trim().toLowerCase();const docs=snapshot.documents.filter(d=>(d.title+' '+d.content).toLowerCase().includes(q));
 $('document-count').textContent=snapshot.documents.length;
 for(const doc of docs){const button=node('button',undefined,'document-card'+(editing?.id===doc.id?' selected':''));button.type='button';button.append(node('strong',doc.title),node('small',({active:'已启用',needs_review:'待核实',disabled:'已停用'}[doc.status]||'待核实')+' · '+(doc.product_ids?.length?doc.product_ids.map(id=>snapshot.products.find(p=>p.id===id)?.name||id).join('、'):'店铺通用')));button.onclick=()=>openEditor(doc);list.append(button);}
 if(!docs.length)list.append(node('p',q?'没有匹配资料。':'还没有资料，点击新增开始。','muted'));
}
function localTime(value){if(!value)return '';const date=new Date(value);if(Number.isNaN(date.getTime()))return '';return new Date(date.getTime()+8*60*60*1000).toISOString().slice(0,16);}
function openEditor(doc){
 if(dirty&&!window.confirm('有未保存的资料修改，确定放弃吗？'))return;
 editing=doc?structuredClone(doc):null;dirty=false;$('document-form').hidden=false;$('editor-empty').hidden=true;$('editor-title').textContent=doc?'编辑资料':'新增资料';
 $('title').value=doc?.title||'';$('content').value=doc?.content||'';$('source').value=typeof doc?.source==='string'?doc.source:'';$('document-status').value=doc?.status||'needs_review';$('confirmed-date').value=doc?.date||new Date(Date.now()+8*60*60*1000).toISOString().slice(0,10);$('reception').value=doc?.conditions?.reception||'presales';
 $('valid-from').value=localTime(doc?.conditions?.valid_from);$('valid-until').value=localTime(doc?.conditions?.valid_until);$('updated-at').textContent=doc?.updated_at?'更新于 '+doc.updated_at.slice(0,10):'';
 $('product-options').replaceChildren();for(const product of snapshot.products){const label=node('label'),input=node('input');input.type='checkbox';input.value=product.id;input.checked=!!doc?.product_ids?.includes(product.id);label.append(input,document.createTextNode(product.name));$('product-options').append(label);}
 for(const input of $('stage-options').querySelectorAll('input'))input.checked=(doc?.conditions?.stages||['presales']).includes(input.value);
 $('save-note').textContent='仅录入已确认资料，缺少依据的内容请先核实。';renderList();
}
async function load(){
 if(saving)return;
 if(dirty&&!window.confirm('有未保存的修改，确定刷新吗？'))return;
 try{snapshot=await api('/api/materials');editing=null;dirty=false;$('document-form').hidden=true;$('editor-empty').hidden=false;renderList();notice('');}
 catch(error){notice(error.message);$('documents').replaceChildren(node('p','资料读取失败，请确认管理权限后刷新。','muted'));}
}
$('new-document').onclick=()=>{if(snapshot)openEditor(null);};$('refresh').onclick=load;$('search').oninput=renderList;
$('document-form').addEventListener('input',()=>{dirty=true;});$('document-form').addEventListener('change',()=>{dirty=true;});
$('document-form').addEventListener('submit',async event=>{
 event.preventDefault();if(saving||!snapshot)return;
 const from=$('valid-from').value,until=$('valid-until').value;if(from&&until&&from>=until){$('save-note').textContent='结束时间需要晚于开始时间。';return;}
 const document={...(editing||{}),date:$('confirmed-date').value,title:$('title').value.trim(),content:$('content').value.trim(),source:$('source').value.trim(),status:$('document-status').value,product_ids:[...$('product-options').querySelectorAll('input:checked')].map(input=>input.value),conditions:{reception:$('reception').value,stages:[...$('stage-options').querySelectorAll('input:checked')].map(input=>input.value),valid_from:from?from+':00+08:00':null,valid_until:until?until+':00+08:00':null}};
 saving=true;$('save-document').disabled=true;$('save-note').textContent='正在保存资料…';
 try{const result=await api('/api/materials',{revision:snapshot.revision,document});snapshot.revision=result.revision;snapshot.documents=snapshot.documents.filter(item=>item.id!==result.document.id).concat(result.document);dirty=false;openEditor(result.document);$('save-note').textContent='资料已保存，下一次检索会使用新内容。';notice('');}
 catch(error){$('save-note').textContent=error.message;}
 finally{saving=false;$('save-document').disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
load();
