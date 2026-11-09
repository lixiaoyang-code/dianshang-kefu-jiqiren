const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/knowledge.js'),'utf8');
const controls=Object.fromEntries(['edit-status','approve-answer','save','save-note','editor','scope','owner','product-options','valid-from','valid-until','reception','stage-options','keywords','keyword-mode','priority'].map(id=>[id,{value:'',disabled:false,classList:{toggle(){}},querySelectorAll:()=>[],close(){}}]));
controls['edit-status'].value='needs_review';controls.scope.value='product';controls.owner.value='801';
controls['product-options'].querySelectorAll=()=>[{value:'801'}];controls['stage-options'].querySelectorAll=()=>[{value:'presales'}];
controls.reception.value='presales';controls['keyword-mode'].value='any';
let submitted,notice,handler;
const original={id:'one',status:'needs_review',standard_answer:'reviewed wording',product_ids:['801']};
const context=vm.createContext({$:id=>controls[id],document:{querySelector:()=>({value:'all'})},
 editing:original,selectedImages:[],data:{revision:'r1'},dirty:false,
 answerParts:()=>['reviewed wording'],currentScene:()=>({id:'scene.one'}),lines:()=>[],
 api:async(_url,options)=>{submitted=JSON.parse(options.body);return {record:submitted.record,revision:'r2'};},
 applySavedAnswer:()=>true,load:async()=>{},message:text=>{notice=text;}});
vm.runInContext(source.slice(source.indexOf('function updateReviewActions(){'),source.indexOf('function openEditor(row){')),context);
controls['edit-form']={addEventListener:(_event,callback)=>{handler=callback;}};
const start=source.indexOf("$('edit-form').addEventListener('submit'");
vm.runInContext(source.slice(start,source.indexOf("\nfor(const id of ['search'",start)),context);
(async()=>{
 context.updateReviewActions();
 assert.equal(controls['approve-answer'].hidden,false);assert.equal(controls.save.textContent,'保存为待审核');
 await handler({preventDefault(){},submitter:{id:'save'}});
 assert.equal(submitted.record.status,'needs_review');assert.match(notice,/尚未启用/);
 await handler({preventDefault(){},submitter:{id:'approve-answer'}});
 assert.equal(submitted.record.status,'active');assert.equal(submitted.record.standard_answer,original.standard_answer);
 assert.deepEqual(submitted.record.product_ids,['801']);assert.match(notice,/答案已启用/);
 assert.equal(original.status,'needs_review');assert.equal(controls.save.disabled,false);assert.equal(controls['approve-answer'].disabled,false);
 controls['edit-status'].value='disabled';context.updateReviewActions();
 assert.equal(controls['approve-answer'].hidden,true);assert.equal(controls.save.textContent,'保存并停用');
 await handler({preventDefault(){},submitter:{id:'save'}});assert.equal(submitted.record.status,'disabled');assert.match(notice,/已停用/);
 console.log('PASS: draft save preserves pending status; explicit approval enables the reviewed answer; labels and notices reflect actual status');
})().catch(error=>{console.error(error);process.exitCode=1;});
