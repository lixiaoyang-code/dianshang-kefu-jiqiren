const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.style={};this.value='';this.checked=false;this.textContent='';}
 append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}
 setAttribute(k,v){this[k]=v;}querySelectorAll(tag){return this.children.flatMap(v=>[...(v.tagName===tag?[v]:[]),...(v.querySelectorAll?.(tag)||[])]);}
}
const controls=new Map();
for(const m of fs.readFileSync('static/statistics.html','utf8').matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"[^>]*>/g))controls.set(m[2],new Element(m[1]));
controls.get('days').value='7';let verdict=null,fail=false;const calls=[];
const document={getElementById:id=>controls.get(id),createElement:tag=>new Element(tag)};
const fetch=async(url,init)=>{
 calls.push({url,init});
 if(url==='/api/products')return {ok:true,json:async()=>[{id:'801',name:'纯色款'}]};
 if(url==='/api/statistics/review'){verdict=JSON.parse(init.body).verdict;return {ok:true,json:async()=>({status:'saved'})};}
 if(fail)throw Error('网络暂不可用');
 return {ok:true,json:async()=>({counts:{total:2,responded:1,manual:1,recognized:1,reviewed:verdict?1:0,correct:verdict==='correct'?1:0,partial:0,duplicates:1,errors:0,clarifications:0},rates:{response:50,handoff:50,intent:50,accuracy:verdict==='correct'?100:null,review_coverage:verdict?100:0},trend:[{day:'2026-11-04',total:2,responded:1}],reasons:[{reason:'insufficient_evidence',count:1}],records:[{id:'r1',status:'answered',responded:1,question:'<script>不执行</script>',answer:'业务答案',review:verdict,elapsed:10}],record_total:1})};
};
const context=vm.createContext({document,fetch,Date,URLSearchParams,console});
vm.runInContext(fs.readFileSync('static/statistics.js','utf8'),context);
const tick=async()=>{for(let i=0;i<10;i++)await new Promise(setImmediate);};
(async()=>{
 await tick();assert.equal(controls.get('response').textContent,'50.0%');assert.equal(controls.get('accuracy').textContent,'—');
 const row=controls.get('records').children[0];assert.equal(row.children[1].textContent,'<script>不执行</script>');
 await row.children.at(-1).children[1].onclick();assert.equal(controls.get('accuracy').textContent,'100.0%');
 controls.get('days').value='0';controls.get('interactions').checked=true;controls.get('days').onchange();await tick();
 assert.ok(calls.at(-1).url.includes('days=0'));assert.ok(calls.at(-1).url.includes('include_interactions=true'));
 fail=true;controls.get('refresh').onclick();await tick();assert.equal(controls.get('error').hidden,false);assert.equal(controls.get('refresh').disabled,false);
 console.log('PASS: statistics filters, honest empty accuracy, review updates, safe question rendering and retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
