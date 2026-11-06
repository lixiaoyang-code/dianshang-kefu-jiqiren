const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
class Element{
 constructor(tag,id=''){this.tagName=tag;this.id=id;this.children=[];this.value='';this.textContent='';this.hidden=false;this.handlers={};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];}
 addEventListener(event,handler){this.handlers[event]=handler;}
 querySelectorAll(selector){const inputs=[];function visit(node){if(node.tagName==='input'&&(!selector.endsWith(':checked')||node.checked))inputs.push(node);for(const child of node.children||[])visit(child);}visit(this);return inputs;}
}
const controls=new Map();
const html=fs.readFileSync(path.join(root,'static/materials.html'),'utf8');
for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g))controls.set(match[2],new Element(match[1],match[2]));
for(const stage of ['presales','shipping','received','aftersales']){const input=new Element('input');input.value=stage;controls.get('stage-options').append(input);}
const document={getElementById:id=>controls.get(id),createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})};
const doc={id:'802-size',title:'全伸缩款尺寸',content:'宽度65–90厘米。',product_ids:['802'],date:'2026-10-22',source:'商家确认',status:'active',topics:['dimensions'],conditions:{reception:'presales',stages:['presales'],valid_from:null,valid_until:null}};
let revision='v1',saved=null,conflict=false;
const fetch=async(url,init)=>{
 assert.equal(url,'/api/materials');
 if(init.method==='GET')return {ok:true,json:async()=>({revision,documents:[doc],products:[{id:'801',name:'纯色款'},{id:'802',name:'全伸缩款'}]})};
 saved=JSON.parse(init.body);if(conflict)return {ok:false,json:async()=>({detail:'资料已更新，请刷新后保存。'})};
 revision='v2';return {ok:true,json:async()=>({revision,document:{...saved.document,id:saved.document.id||'new-doc'}})};
};
const context=vm.createContext({document,fetch,structuredClone,Date,window:{confirm:()=>true,addEventListener(){}}});
vm.runInContext(fs.readFileSync(path.join(root,'static/materials.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
(async()=>{
 for(let i=0;i<20;i++)await new Promise(resolve=>setImmediate(resolve));
 assert.equal(controls.get('documents').children.length,1);
 controls.get('documents').children[0].onclick();
 assert.equal(controls.get('title').value,doc.title);
 assert.equal(controls.get('confirmed-date').value,'2026-10-22');
 assert.equal(controls.get('product-options').querySelectorAll('input:checked')[0].value,'802');
 controls.get('content').value='修改后的资料';
 await controls.get('document-form').handlers.submit({preventDefault(){}});
 assert.equal(saved.document.content,'修改后的资料');assert.deepEqual(saved.document.topics,['dimensions']);
 assert.equal(saved.document.date,'2026-10-22');assert.deepEqual(saved.document.product_ids,['802']);
 assert.equal(saved.document.conditions.reception,'presales');assert.deepEqual(saved.document.conditions.stages,['presales']);
 assert.equal(run('snapshot.revision'),'v2');
 conflict=true;controls.get('content').value='不能覆盖他人的新资料';
 await controls.get('document-form').handlers.submit({preventDefault(){}});
 assert.equal(run('snapshot.revision'),'v2');assert.match(controls.get('save-note').textContent,/资料已更新/);
 controls.get('new-document').onclick();assert.equal(controls.get('document-status').value,'needs_review');
 assert.equal(controls.get('product-options').querySelectorAll('input:checked').length,0);
 console.log('PASS: material editor preserves scope, confirmation date and metadata; revision conflicts cannot overwrite; new sources default to review');
})().catch(error=>{console.error(error);process.exitCode=1;});
