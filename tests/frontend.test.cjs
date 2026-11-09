// 启动真实脚本，DOM ID 来自实际 HTML：捕获页面/脚本不配套导致的空节点错误。
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'static/index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'static/app.js'),'utf8');

class Element{
 constructor(tag,id=''){this.tagName=tag;this.id=id;this.children=[];this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.scrollHeight=0;this.style={};}
 setAttribute(name,value){this[name]=value;}
 after(node){this.afterNode=node;}
 append(...nodes){this.children.push(...nodes);for(const node of nodes)node.parentNode=this;}
 replaceChildren(...nodes){this.children=[...nodes];this.value='';}
 remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(node=>node!==this);}
 showModal(){this.open=true;}
 close(){this.open=false;}
}
function setup(options={}){
 const controls=new Map();
 for(const m of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g))controls.set(m[2],new Element(m[1],m[2]));
 controls.get('reception-type').value='presales';controls.get('business-stage').value='presales';
 if(options.noCandidate){controls.delete('send-card');controls.delete('candidate-select');}
 const calls=[];let n=0,session;
 const document={getElementById:id=>controls.get(id)||null,createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text}),
  querySelectorAll:selector=>selector==='[data-question]'?[]:[...controls.values()].filter(e=>['button','select'].includes(e.tagName))};
 const fetch=async(url,init)=>{
  const payload=init?.body?JSON.parse(init.body):null;calls.push({url,payload});let data;
  if(url==='/api/products'){
   if(options.failProducts)throw new Error('测试连接中断');
   data=['801','802','803','804'].map((id,i)=>({id,name:['纯色款','全伸缩款','小狗联名款','免安装款'][i]}));
  }else if(url==='/api/health'){
   if(options.failHealth)throw new Error('测试状态接口不可用');
   data={mode:'mock',semantic:'ready',deployment:{public_demo:!!options.publicDemo,can_manage:!options.publicDemo}};
  }else if(/^\/api\/sessions\/[^/]+$/.test(url)){
   if(options.expiredSession)return {ok:false,status:404,json:async()=>({detail:'会话不存在'})};
   data=session={session_id:url.split('/').at(-1),current_product_id:'801',recent_product_ids:[]};
  }else if(url==='/api/sessions')data=session={session_id:'test-'+(++n),current_product_id:null,recent_product_ids:[]};
  else if(url.endsWith('/reset')){
   const prior=session;session={session_id:prior.session_id,current_product_id:payload.mode==='memory'?prior.current_product_id:null,recent_product_ids:[],reception_type:payload.mode==='memory'?payload.reception_type:'presales',business_stage:payload.mode==='memory'?payload.business_stage:'presales'};data=session;
  }else if(url.endsWith('/events')){
   if(payload.type==='customer_select')session.current_product_id=payload.product_id;
   if(payload.type==='agent_card')session.recent_product_ids=[payload.product_id];
   if(payload.type==='customer_link'){session.current_product_id=payload.product_id;data={session:{...session},link:{url:payload.url,product_id:payload.product_id},status:payload.product_id?'linked':'product_required',message:payload.product_id?'已关联商品':'请确认商品'};}else data={...session};
  }else if(url==='/api/rag/assist'){
   data=options.ragDeferred?await options.ragDeferred:{status:'extractive',generation_status:options.ragGeneration||'mock',retrieval_method:options.ragMethod||'hybrid',suggestion:'这是只给测试者的资料建议',proposed_intent:'比较调节范围',can_save_faq:true,sources:[{id:'doc-802',title:'全伸缩尺寸说明',excerpt:'宽度65–90厘米。',source:'商家确认'}]};
  }else if(url==='/api/chat'){
   if(options.failChat)throw new Error('测试请求失败');
   session={...session,reception_type:payload.reception_type,business_stage:payload.business_stage};
   data={status:'answered',send_to_customer:true,answer:'批准的测试回复',images:[],session,
         debug:{elapsed_ms:1,model:'mock',request_id:'feedback-test',analysis:{status:'unrecognized',intents:[],method:'语义向量检索',outcome:'没有可用答案',knowledge_url:'/knowledge',candidates:[]}}};
   if(options.editable){data.answer_parts=['第一条\n保留分行','第二条'];data.answer=data.answer_parts.join('\n\n');data.images=[{url:'/static/images/test.png',alt:'测试配图'}];data.debug.editable_answer_ids=['test-answer'];data.debug.analysis.knowledge_url=options.missingTarget?'/knowledge':'/knowledge?scene=height&answer=stale-answer';}
   if(options.multiSource)data.debug.editable_answer_ids=['source-a','source-b'];
   if(options.suppressed){data.status='suppressed';data.send_to_customer=false;data.answer='';}
  }else throw new Error('Unexpected API '+url);
  return {ok:true,json:async()=>data};
 };
 const saved=new Map();const localStorage={get length(){return saved.size;},key:i=>[...saved.keys()][i],getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
 const context=vm.createContext({document,fetch,AbortController,URL,URLSearchParams,crypto:require('node:crypto').webcrypto,window:{sessionStorage:options.storage||localStorage,location:{origin:'http://localhost',search:''},confirm:()=>true},localStorage,setTimeout:()=>1,clearTimeout:()=>{}});
 vm.runInContext(fs.readFileSync(path.join(root,'static/test-context.js'),'utf8'),context);
 vm.runInContext(script,context);
 return {controls,calls,context,options,state:()=>vm.runInContext('({ready,busy,sid})',context),run:code=>vm.runInContext(code,context)};
}
async function settle(app){for(let i=0;i<30;i++)await new Promise(resolve=>setImmediate(resolve));}

(async()=>{
 let app=setup();await settle(app);
 assert.equal(app.state().ready,true);assert.equal(app.state().busy,false);
 assert.equal(app.controls.get('product-select').children.length,5);
 assert.equal(app.controls.get('product-select').disabled,false);
 for(const id of ['801','802','803','804']){
  await app.run(`event('customer_select','${id}')`);
  assert.equal(app.controls.get('product-select').value,id);
 }
 await app.run("event('customer_select',null)");assert.equal(app.controls.get('product-select').value,'');
 await app.run("event('customer_select','801')");await app.run("event('agent_card','804')");
 assert.equal(app.controls.get('product-select').value,'801');
 app.controls.get('reception-type').value='aftersales';app.controls.get('business-stage').value='received';
 await app.run("send('测试问题')");
 const sent=app.calls.find(c=>c.url==='/api/chat').payload;
 assert.equal(sent.reception_type,'aftersales');assert.equal(sent.business_stage,'received');
 await app.run('newSession()');assert.equal(app.controls.get('product-select').value,'801');
 assert.equal(app.controls.get('business-stage').value,'received');
 await app.run("event('agent_card','804')");
 await app.run("resetTest('memory')");
 assert.equal(app.controls.get('product-select').value,'801');
 assert.equal(app.controls.get('reception-type').value,'aftersales');
 assert.equal(app.controls.get('business-stage').value,'received');
 assert.equal(app.controls.get('messages').children.length,1);
 assert.match(app.controls.get('messages').children[0].children[0].textContent,/记忆已清除/);
 await app.run("resetTest('test')");
 assert.equal(app.controls.get('product-select').value,'');
 assert.equal(app.controls.get('reception-type').value,'presales');
 assert.equal(app.controls.get('business-stage').value,'presales');
 assert.equal(app.controls.get('debug').textContent,'尚无检索记录');
 console.log('PASS: bootstrap, four product choices, clear, card isolation, conditions, clear memory and reset test');

 app=setup({failHealth:true,noCandidate:true});await settle(app);
 assert.equal(app.state().ready,true);assert.equal(app.controls.get('product-select').disabled,false);
 assert.equal(app.controls.get('product-select').children.length,5);
 console.log('PASS: optional card widget and health failure do not break product selection');

 app=setup({failProducts:true});await settle(app);
 assert.equal(app.state().ready,false);assert.equal(app.controls.get('reconnect').hidden,false);
 assert.equal(app.controls.get('reconnect').disabled,false);assert.equal(app.controls.get('send').disabled,true);
 app.options.failProducts=false;await app.run('connect()');await settle(app);
 assert.equal(app.state().ready,true);assert.equal(app.controls.get('product-select').children.length,5);
 await app.run('connect()');await settle(app);
 assert.equal(app.controls.get('product-select').children.length,5);
 console.log('PASS: failed bootstrap can reconnect without duplicate options');
 app=setup({suppressed:true});await settle(app);await app.run("send('一个未知问题')");
 let user=app.controls.get('messages').children.find(e=>e.className.startsWith('bubble user '));
 assert.equal(user.afterNode.className,'intent-feedback');
 assert.match(user.afterNode.children[0].children[0].textContent,/未识别/);
 const href=user.afterNode.children[0].children[1].href;
 assert.match(href,/test=feedback-test/);assert.ok(!href.includes('一个未知问题'));
 assert.equal(app.run("TestContext.read('feedback-test').question"),'一个未知问题');
 assert.equal(app.run("TestContext.read('feedback-test').business_stage"),'presales');
 assert.equal(user.afterNode.children.length,1); // 聊天区只保留意图和优化入口。
 assert.equal(app.controls.get('assist-question').textContent,'一个未知问题');
 assert.equal(app.controls.get('evidence-details').open,false);
 assert.match(app.controls.get('assist-action').href,/action=new/);
 await app.run("send('第二个未知问题')");
 user.onclick();assert.equal(app.controls.get('assist-question').textContent,'一个未知问题');
 assert.equal(app.controls.get('assist-empty').hidden,true);
 await app.run("resetTest('memory')");
 assert.equal(app.controls.get('assist-content').hidden,true);
 assert.equal(app.controls.get('evidence-details').open,false);
 app=setup({failChat:true});await settle(app);await app.run("send('失败测试')");
 user=app.controls.get('messages').children.find(e=>e.className.startsWith('bubble user '));
 assert.equal(user.afterNode.children.length,1);
 assert.match(app.controls.get('trace-summary').textContent,/请求失败/);
 assert.equal(app.controls.get('assist-action').textContent,'重新测试本条');
 console.log('PASS: unanswered and failed requests have intent feedback and contextual optimization links');
 app=setup({editable:true});await settle(app);await app.run("event('customer_select','801')");
 app.controls.get('reception-type').value='aftersales';app.controls.get('business-stage').value='received';
 await app.run("send('高度是多少')");
 let replies=app.controls.get('messages').children.filter(e=>e.className.startsWith('bubble assistant '));
 assert.equal(replies.length,2);assert.equal(replies[0].children[1].textContent,'第一条\n保留分行');
 assert.equal(replies[0].children.filter(e=>e.tagName==='a').length,0);assert.equal(replies[1].children.filter(e=>e.tagName==='a').length,2);
 const edit=replies[1].children.find(e=>e.className==='answer-inline-edit');assert.ok(edit);
 assert.equal(edit.tagName,'a');assert.equal(edit.target,'_self');assert.equal(edit.rel,'noopener');
 const target=new URL(edit.href,'http://localhost');assert.equal(target.pathname,'/knowledge');
 assert.equal(target.searchParams.get('scene'),'height');assert.equal(target.searchParams.get('answer'),'test-answer');
 assert.equal(target.searchParams.get('action'),'answer');assert.equal(target.searchParams.get('test'),'feedback-test');
 assert.ok(!edit.href.includes('高度是多少'));
 // 后续更换测试条件不能影响旧答复的知识入口及原问题复测条件。
 await app.run("event('customer_select','803')");app.controls.get('reception-type').value='presales';app.controls.get('business-stage').value='presales';
 const context=app.run("TestContext.read('feedback-test')");
 assert.equal(context.question,'高度是多少');assert.equal(context.product_id,'801');
 assert.equal(context.reception_type,'aftersales');assert.equal(context.business_stage,'received');
 assert.equal(edit.href,target.pathname+target.search);
 let stopped=false;edit.onclick({preventDefault(){},stopPropagation(){stopped=true;}});assert.ok(stopped);
 assert.equal(app.controls.has('answer-editor'),false);
 assert.equal(app.calls.filter(c=>c.url==='/api/faq'||c.url==='/api/scenes').length,0);
 assert.equal(app.calls.filter(c=>c.url==='/api/sessions').length,1);
 assert.equal(app.calls.filter(c=>c.url==='/api/chat').length,1);
 app=setup({editable:true,missingTarget:true});await settle(app);await app.run("send('来源不明')");
 replies=app.controls.get('messages').children.filter(e=>e.className.startsWith('bubble assistant '));assert.ok(replies.every(reply=>!reply.children.some(e=>e.className==='answer-inline-edit')));
 app=setup({multiSource:true});await settle(app);await app.run("send('综合问题')");
 replies=app.controls.get('messages').children.filter(e=>e.className.startsWith('bubble assistant '));assert.ok(replies.every(reply=>!reply.children.some(e=>e.className==='answer-inline-edit')));
 console.log('PASS: multipart replies link to the exact knowledge source and preserve original test conditions; ambiguous sources cannot be overwritten');

 app=setup({editable:true});await settle(app);await app.run("send('复杂尺寸比较')");
 assert.equal(app.calls.filter(call=>call.url==='/api/rag/assist').length,0); // 已命中 FAQ 不额外生成。
 await app.run('loadRag(selectedResult)');
 assert.equal(app.controls.get('rag-status').textContent,'资料摘录');
 assert.equal(app.controls.get('rag-generation-note').hidden,false);
 assert.match(app.controls.get('rag-generation-note').textContent,/当前未启用生成/);
 assert.match(app.controls.get('rag-retrieval-method').textContent,/混合检索/);
 assert.match(app.controls.get('rag-generation-status').textContent,/mock/);
 assert.equal(app.controls.get('rag-suggestion').textContent,'这是只给测试者的资料建议');
 assert.equal(app.controls.get('rag-sources').children.length,1);
 assert.equal(app.controls.get('rag-save').hidden,false);
 assert.match(app.controls.get('rag-save').href,/action=rag-draft/);
 assert.equal(app.run("TestContext.read('feedback-test').rag.sources[0].id"),'doc-802');
 assert.ok(app.controls.get('messages').children.filter(item=>item.className.startsWith('bubble assistant')).every(item=>!item.children.some(child=>child.textContent==='这是只给测试者的资料建议')));
 app=setup({suppressed:true});await settle(app);await app.run("send('复杂问题')");await settle(app);
 assert.equal(app.calls.filter(call=>call.url==='/api/rag/assist').length,1);
 assert.equal(app.controls.get('rag-status').textContent,'资料摘录');
 let resolveRag;const ragDeferred=new Promise(resolve=>resolveRag=resolve);
 app=setup({suppressed:true,ragDeferred});await settle(app);await app.run("send('等待资料的旧问题')");
 await app.run("resetTest('memory')");resolveRag({status:'generated',suggestion:'过期建议',sources:[],can_save_faq:false});await settle(app);
 assert.equal(app.controls.get('assist-content').hidden,true);assert.equal(app.controls.get('rag-panel').hidden,true);
 app=setup({editable:true,publicDemo:true});await settle(app);await app.run("send('访客测试')");
 assert.equal(app.controls.get('knowledge-nav').hidden,true);assert.equal(app.controls.get('materials-nav').hidden,true);
 replies=app.controls.get('messages').children.filter(item=>item.className.startsWith('bubble assistant'));
 assert.ok(replies.every(reply=>!reply.children.some(child=>child.className==='answer-inline-edit')));
 user=app.controls.get('messages').children.find(item=>item.className.startsWith('bubble user'));
 assert.equal(user.afterNode.children[0].children[1].hidden,true);
 await app.run('loadRag(selectedResult)');assert.equal(app.controls.get('rag-save').hidden,true);
 app=setup({ragGeneration:'failed',ragMethod:'keyword_fallback'});await settle(app);await app.run("send('资料比较')");await app.run('loadRag(selectedResult)');
 assert.match(app.controls.get('rag-generation-note').textContent,/生成暂不可用/);assert.match(app.controls.get('rag-retrieval-method').textContent,/关键词检索/);assert.match(app.controls.get('rag-generation-status').textContent,/调用失败.*failed/);
 app=setup({ragGeneration:'generated'});await settle(app);await app.run("send('资料比较')");await app.run('loadRag(selectedResult)');assert.equal(app.controls.get('rag-generation-note').hidden,true);
 console.log('PASS: RAG only assists, sources and drafts are visible, expired responses cannot revive reset conversations, public visitors cannot edit');
 app=setup();await settle(app);await app.run("send('第一条咨询')");
 app.controls.get('tab-diagnostic').onclick();
 assert.equal(app.controls.get('advice-panel').hidden,true);assert.equal(app.controls.get('diagnostic-panel').hidden,false);
 assert.equal(app.controls.get('evidence-details').open,true);assert.equal(app.controls.get('tab-diagnostic')['aria-selected'],'true');
 app.controls.get('tab-advice').onclick();assert.equal(app.controls.get('advice-panel').hidden,false);
 assert.ok(!app.controls.get('messages').children.some(v=>v.className.startsWith('bubble pending')));
 app.controls.get('input').value='新的原声';app.controls.get('input').oninput();assert.equal(app.controls.get('input-count').textContent,'4 / 2000');
 console.log('PASS: blue workbench advice/diagnostic tabs, loading cleanup and input feedback');

 app=setup();await settle(app);
 app.run('openProductLink()');assert.equal(app.controls.get('product-link-dialog').open,true);
 assert.equal(app.controls.get('product-link-product').children.length,5);
 app.controls.get('product-link-url').value='javascript:alert(1)';await app.run('sendProductLink()');
 assert.equal(app.calls.filter(c=>c.payload?.type==='customer_link').length,0);
 assert.equal(app.controls.get('product-link-error').hidden,false);
 app.controls.get('product-link-url').value='https://example.com/item/803';app.controls.get('product-link-product').value='802';await app.run('sendProductLink()');
 assert.equal(app.controls.get('product-select').value,'802');
 assert.equal(app.calls.at(-1).payload.type,'customer_link');assert.equal(app.calls.at(-1).payload.product_id,'802');
 assert.equal(app.controls.get('product-link-dialog').open,false);
 const card=app.controls.get('messages').children.find(c=>c.className.includes('product-link-card'));
 assert.equal(card.children[2].href,'https://example.com/item/803');assert.equal(card.children[2].rel,'noopener noreferrer');
 app.run('openProductLink()');app.controls.get('product-link-url').value='https://example.com/item/801';app.controls.get('product-link-product').value='';await app.run('sendProductLink()');
 assert.equal(app.controls.get('product-select').value,'');
 assert.equal(app.calls.filter(c=>c.url==='/api/chat'||c.url==='/api/rag/assist').length,0);
 app.run('openProductLink()');app.controls.get('product-link-url').value='';app.controls.get('product-link-product').value='803';await app.run('sendProductLink()');
 assert.equal(app.controls.get('product-select').value,'803');
 assert.equal(app.controls.get('product-link-dialog').open,false);
 const cards=app.controls.get('messages').children.filter(c=>c.className.includes('product-link-card'));
 assert.equal(cards.at(-1).children[2].textContent,'已关联 · 后续咨询按此商品回答');
 console.log('PASS: product cards send without URLs and links validate safely without model calls');
 const history=app.controls.get('messages');history.scrollHeight=1200;history.clientHeight=400;history.scrollTop=100;
 app.run("bubble('新的答复','assistant')");assert.equal(history.scrollTop,100);assert.equal(app.controls.get('new-replies').hidden,false);
 app.controls.get('new-replies').onclick();assert.equal(history.scrollTop,1200);assert.equal(app.controls.get('new-replies').hidden,true);
 history.scrollTop=780;app.run("bubble('继续答复','assistant')");assert.equal(history.scrollTop,1200);
 app.controls.get('business-stage').value='aftersales';app.controls.get('business-stage').onchange();assert.ok(app.controls.get('toast').textContent.includes('售后'));
 console.log('PASS: reading history is preserved, new replies can be reached explicitly and condition changes are acknowledged');
 const sourceBubble=app.run("bubble('请稍等','assistant',{status:'handoff',send_to_customer:false,session:{current_product_id:'802'},debug:{question:'旧问题的尺寸'},uiContext:{question:'旧问题的尺寸'}},{waiting:true,images:false,edit:false})");
 const source=sourceBubble.children[0];assert.equal(source.children[0].textContent,'等待提示');
 const ragLink=source.children[1];assert.equal(ragLink.textContent,'查看 RAG 建议 ↗');
 ragLink.onclick({stopPropagation(){}});await settle(app);
 assert.equal(app.controls.get('assist-question').textContent,'旧问题的尺寸');
 assert.equal(app.calls.filter(c=>c.url==='/api/rag/assist').at(-1).payload.message,'旧问题的尺寸');
 assert.equal(app.controls.get('advice-panel').hidden,false);assert.equal(app.controls.get('rag-panel').hidden,false);
 const ragCalls=app.calls.filter(c=>c.url==='/api/rag/assist').length;ragLink.onclick({stopPropagation(){}});await settle(app);
 assert.equal(app.calls.filter(c=>c.url==='/api/rag/assist').length,ragCalls);
 assert.ok(!sourceBubble.children.some(c=>c.textContent==='这是只给测试者的资料建议'));
 console.log('PASS: waiting labels open the original question RAG panel, reuse suggestions and never send RAG to chat');
 app=setup({editable:true});await settle(app);await app.run("event('customer_select','801')");await app.run("send('长宽能调吗')");
 const cache=app.run('window.sessionStorage');const originalSid=app.state().sid;
 app=setup({storage:cache});await settle(app);
 assert.equal(app.state().sid,originalSid);assert.equal(app.calls.filter(c=>c.url==='/api/sessions').length,0);
 assert.ok(app.controls.get('messages').children.some(c=>c.children.some(n=>n.textContent==='长宽能调吗')));
 assert.equal(app.controls.get('assist-question').textContent,'长宽能调吗');
 assert.equal(app.controls.get('assist-action').target,'_self');
 assert.equal(app.calls.filter(c=>c.url==='/api/chat').length,0,'restore must never resend a customer question');
 const expired=setup({storage:cache,expiredSession:true});await settle(expired);
 assert.equal(expired.calls.filter(c=>c.url==='/api/sessions').length,1);
 assert.ok(expired.controls.get('messages').children.some(c=>c.children.some(n=>String(n.textContent).includes('历史对话已保留'))));
 await app.run("resetTest('test')");
 const reset=JSON.parse(cache.getItem('pac-chat-resume-v1'));assert.equal(reset.entries.some(e=>e.text==='长宽能调吗'),false);
 assert.equal(app.run("ragPresentation({generation_status:'unsupported_numbers',sources:[{}]},false).state"),'excerpt');
 assert.equal(app.run("ragPresentation({generation_status:'generated',sources:[{}]},false).title"),'AI 建议回复');
 const beforeOpen=app.controls.get('messages').children.length;const beforeSid=app.state().sid;app.run("openKnowledgeEditor('/knowledge?scene=test&action=answer')");assert.equal(app.controls.get('knowledge-workspace').open,true);assert.match(app.controls.get('knowledge-workspace-frame').src,/embed=1/);assert.equal(app.state().sid,beforeSid);assert.equal(app.controls.get('messages').children.length,beforeOpen);
 console.log('PASS: refresh resumes the same session and transcript without resending; expiry preserves history and reset removes it; RAG labels distinguish generated from rejected output');
})().catch(error=>{console.error(error);process.exitCode=1;});
