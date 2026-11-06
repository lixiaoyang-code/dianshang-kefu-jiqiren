// 只在同源工作台短时保存测试上下文；URL 中不放客户原话。
const TestContext = {
  prefix:'presales-test:',
  save(result, question, conditions) {
    const key=result.debug?.request_id || crypto.randomUUID();
    try {
      for(let i=localStorage.length-1;i>=0;i--){
        const name=localStorage.key(i);
        if(name?.startsWith(this.prefix)){
          try {if(Date.now()-JSON.parse(localStorage.getItem(name)).created>1800000)localStorage.removeItem(name);}
          catch {localStorage.removeItem(name);}
        }
      }
      localStorage.setItem(this.prefix+key,JSON.stringify({created:Date.now(),question,
        product_id:result.session?.current_product_id||'',...conditions,
        analysis:result.debug?.analysis,previous_status:result.status}));
      return key;
    } catch {return null;}
  },
  saveRag(result, rag) {
    const key=result.uiContext?.key;
    if(!key || !rag?.sources?.length || !rag.can_save_faq)return null;
    try {
      const context=this.read(key);if(!context)return null;
      context.rag={suggestion:rag.suggestion,proposed_intent:rag.proposed_intent,sources:rag.sources.slice(0,3)};
      localStorage.setItem(this.prefix+key,JSON.stringify(context));return key;
    } catch {return null;}
  },
  read(key) {
    try {const v=JSON.parse(localStorage.getItem(this.prefix+key));
      return v && Date.now()-v.created<1800000?v:null;
    } catch {return null;}
  }
};
