/* Shared mobile drawer: navigation never takes space from the conversation. */
(() => {
  const rail=document.querySelector('.pac-shell'), toggle=document.querySelector('#pac-nav-toggle');
  if(!rail||!toggle)return;
  const backdrop=document.querySelector('.pac-nav-backdrop'), close=rail.querySelector('.pac-nav-close');
  const bar=document.querySelector('.pac-mobile-bar'), main=document.querySelector('body>main');
  const mobile=matchMedia('(max-width:850px)');
  let opened=false, origin=null, touch=null;
  function setOpen(value,restore=true){
    opened=mobile.matches&&value;
    document.body.classList.toggle('pac-nav-open',opened);
    toggle.setAttribute('aria-expanded',String(opened));
    backdrop.hidden=!opened;
    rail.inert=mobile.matches&&!opened;
    if(main)main.inert=opened;
    bar.inert=opened;
    if(opened){origin=document.activeElement;close.focus();}
    else if(restore&&origin){origin.focus();origin=null;}
  }
  toggle.addEventListener('click',()=>setOpen(!opened));
  close.addEventListener('click',()=>setOpen(false));
  backdrop.addEventListener('click',()=>setOpen(false));
  rail.addEventListener('click',e=>{if(e.target.closest('a'))setOpen(false,false);});
  document.addEventListener('keydown',e=>{
    if(!opened)return;
    if(e.key==='Escape'){e.preventDefault();setOpen(false);}
    if(e.key==='Tab'){
      const controls=[...rail.querySelectorAll('a,button')].filter(el=>!el.hidden&&el.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    }
  });
  rail.addEventListener('touchstart',e=>{const t=e.touches[0];touch={x:t.clientX,y:t.clientY};},{passive:true});
  rail.addEventListener('touchend',e=>{
    if(!touch||!opened)return;
    const t=e.changedTouches[0];
    if(t.clientX-touch.x < -60&&Math.abs(t.clientY-touch.y)<55)setOpen(false);
    touch=null;
  },{passive:true});
  mobile.addEventListener('change',()=>setOpen(false));
  setOpen(false,false);
  const filters=document.querySelector('body[data-pac-shell="page"] .workspace>aside');
  if(filters){
    const details=document.createElement('details'),summary=document.createElement('summary'),content=document.createElement('div');
    details.className='pac-mobile-filters';summary.textContent='筛选条件 · 商品 / 接待 / 状态';
    content.className='pac-filter-content';
    while(filters.firstChild)content.append(filters.firstChild);
    details.append(summary,content);filters.append(details);details.open=!mobile.matches;
    mobile.addEventListener('change',()=>{details.open=!mobile.matches;});
  }
  function fitKeyboard(){
    const viewport=window.visualViewport;
    const editing=document.activeElement?.matches('textarea,input:not([type=checkbox]):not([type=radio])');
    const keyboard=mobile.matches&&viewport&&editing&&innerHeight-viewport.height>140;
    document.body.classList.toggle('pac-keyboard-open',!!keyboard);
    if(viewport)document.documentElement.style.setProperty('--pac-visible-height',viewport.height+'px');
  }
  window.visualViewport?.addEventListener('resize',fitKeyboard);
  document.addEventListener('focusin',fitKeyboard);
  document.addEventListener('focusout',()=>queueMicrotask(fitKeyboard));
  const assistant=document.querySelector('.inspect');
  if(assistant){
    assistant.id='pac-mobile-assistant';
    const button=document.createElement('button');button.type='button';button.className='pac-assistant-toggle';
    button.setAttribute('aria-controls',assistant.id);button.setAttribute('aria-expanded','false');
    const label=document.createElement('span');label.textContent='接待助手';
    const hint=document.createElement('span');hint.textContent='查看建议与诊断';
    button.append(label,hint);assistant.before(button);
    button.addEventListener('click',()=>{
      const expanded=button.getAttribute('aria-expanded')!=='true';
      button.setAttribute('aria-expanded',String(expanded));assistant.classList.toggle('pac-assistant-open',expanded);
      hint.textContent=expanded?'收起助手 ↑':'查看建议与诊断 ↓';
    });
    const content=document.querySelector('#assist-content');
    if(content)new MutationObserver(()=>{
      button.classList.toggle('has-advice',!content.hidden);
      if(button.getAttribute('aria-expanded')!=='true')hint.textContent=content.hidden?'查看建议与诊断':'本条建议已就绪 ↓';
    }).observe(content,{attributes:true,attributeFilter:['hidden']});
  }
})();
