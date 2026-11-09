/* A brief brand greeting, never a simulated loading screen. */
(() => {
  if(location.pathname!=='/'||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  try{if(sessionStorage.getItem('pac-welcome-seen'))return;sessionStorage.setItem('pac-welcome-seen','1');}catch{return;}
  const overlay=document.createElement('div');overlay.className='pac-welcome';overlay.setAttribute('aria-hidden','true');
  const lockup=document.createElement('div');lockup.className='pac-welcome-lockup';
  const mark=document.createElement('div');mark.className='pac-welcome-mark';
  const logo=document.createElement('img');logo.src='/static/pac-logo.svg';logo.alt='';mark.append(logo);
  const text=document.createElement('div'),name=document.createElement('strong'),caption=document.createElement('p');
  name.textContent='PAC';caption.textContent='让每一次接待，更有依据';text.append(name,caption);lockup.append(mark,text);overlay.append(lockup);document.body.append(overlay);
  function dismiss(){overlay.remove();document.removeEventListener('keydown',dismiss);}
  overlay.addEventListener('click',dismiss,{once:true});document.addEventListener('keydown',dismiss,{once:true});setTimeout(dismiss,1150);
})();
