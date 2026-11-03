'use strict';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)],enc=encodeURIComponent;
const reduced=matchMedia('(prefers-reduced-motion:reduce)').matches;
const DEF={theme:'dark',fs:20,lh:1.8,speed:1,voice:'',prefetch:true,autoTranslate:true,key:''};
let settings={...DEF};try{Object.assign(settings,JSON.parse(localStorage.getItem('vr.s')||'{}'))}catch{}
const saveS=()=>{try{localStorage.setItem('vr.s',JSON.stringify(settings))}catch{}};
function applyS(){const r=document.documentElement;r.dataset.theme=settings.theme;r.style.setProperty('--fs',settings.fs+'px');r.style.setProperty('--lh',settings.lh);
 $('meta[name=theme-color]').content={dark:'#0c0f12',sepia:'#eee2c6',light:'#f2f0eb'}[settings.theme];$('#speed').textContent=settings.speed+'x'}
/* ---------- IndexedDB ---------- */
const idb=(()=>{let p;const open=()=>p??=new Promise((res,rej)=>{const r=indexedDB.open('viberead',1);
 r.onupgradeneeded=()=>['progress','novels','chapters'].forEach(n=>r.result.createObjectStore(n,{keyPath:'url'}));r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)});
 const tx=async(s,m,f)=>{try{const d=await open();return await new Promise((res,rej)=>{const t=d.transaction(s,m);const q=f(t.objectStore(s));t.oncomplete=()=>res(q.result);t.onerror=()=>rej(t.error)})}catch{return undefined}};
 return{get:(s,k)=>tx(s,'readonly',o=>o.get(k)),put:(s,v)=>tx(s,'readwrite',o=>o.put(v)),all:s=>tx(s,'readonly',o=>o.getAll())}})();
async function api(path,opt){const r=await fetch(path,opt);if(!r.ok){let m=r.statusText;try{const j=await r.json();m=typeof j.detail==='string'?j.detail:j.message||m}catch{}throw new Error(m)}return r}
const post=(p,b,h={})=>api(p,{method:'POST',headers:{'Content-Type':'application/json',...h},body:JSON.stringify(b)});
let tt;function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(tt);tt=setTimeout(()=>t.classList.remove('on'),4000)}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* ---------- Hero Three.js (có fallback CSS) ---------- */
const hero=(()=>{let R,scene,cam,mesh,pts,raf=0,on=false,mx=0,my=0,sx=0,sy=0,U,t0=performance.now();
 function init(){try{if(!window.THREE)throw 0;const c=$('#hero');R=new THREE.WebGLRenderer({canvas:c,antialias:true,alpha:true});if(!R.getContext())throw 0;
  R.setPixelRatio(Math.min(devicePixelRatio,2));scene=new THREE.Scene();cam=new THREE.PerspectiveCamera(40,1,.1,50);cam.position.z=5;
  U={t:{value:0}};mesh=new THREE.Mesh(new THREE.IcosahedronGeometry(1.35,24),new THREE.ShaderMaterial({uniforms:U,
   vertexShader:'uniform float t;varying vec3 n;varying vec3 v;void main(){vec3 p=position;float d=sin(p.x*2.1+t*.6)*sin(p.y*2.3-t*.5)*sin(p.z*1.9+t*.4)+.4*sin(p.y*5.+t);p+=normal*d*.22;n=normalize(normalMatrix*normal);vec4 m=modelViewMatrix*vec4(p,1.);v=-m.xyz;gl_Position=projectionMatrix*m;}',
   fragmentShader:'varying vec3 n;varying vec3 v;void main(){vec3 N=normalize(n),V=normalize(v);float f=pow(1.-max(dot(N,V),0.),2.2);float l=max(dot(N,normalize(vec3(.6,.7,.5))),0.);vec3 mint=vec3(.49,.88,.76),em=vec3(.95,.65,.37);vec3 c=vec3(.05,.065,.08)+l*.16*mint+f*mix(mint,em,smoothstep(.1,.9,1.-N.y*.5-.5+f*.3))*.95;gl_FragColor=vec4(c,1.);}'}));
  scene.add(mesh);const g=new THREE.BufferGeometry(),n=700,a=new Float32Array(n*3);
  for(let i=0;i<n;i++){const r=2.1+Math.random()*1.8,th=Math.random()*6.283,ph=Math.acos(2*Math.random()-1);a.set([r*Math.sin(ph)*Math.cos(th),r*Math.cos(ph),r*Math.sin(ph)*Math.sin(th)],i*3)}
  g.setAttribute('position',new THREE.BufferAttribute(a,3));pts=new THREE.Points(g,new THREE.PointsMaterial({size:.018,color:0x7ce0c3,transparent:true,opacity:.55}));scene.add(pts);
  addEventListener('resize',size);addEventListener('pointermove',e=>{mx=e.clientX/innerWidth-.5;my=e.clientY/innerHeight-.5});size();draw(0)}catch{document.body.classList.add('nogl')}}
 function size(){if(!R)return;const w=innerWidth,h=innerHeight;R.setSize(w,h,false);cam.aspect=w/h;const wide=w>800;mesh.position.set(wide?1.7:0,wide?0:1.5,0);pts.position.copy(mesh.position);cam.updateProjectionMatrix();draw(0)}
 function draw(t){if(!R)return;U.t.value=t;sx+=(mx-sx)*.05;sy+=(my-sy)*.05;mesh.rotation.set(sy*.6+t*.05,sx*.8+t*.08,0);pts.rotation.y=t*.02+sx*.3;R.render(scene,cam)}
 function loop(){if(!on)return;draw((performance.now()-t0)/1000);raf=requestAnimationFrame(loop)}
 return{init,active(b){document.body.classList.toggle('home',b);on=b&&!reduced&&!document.hidden;cancelAnimationFrame(raf);if(on)loop();else draw(1)}}})();
document.addEventListener('visibilitychange',()=>hero.active(document.body.classList.contains('home')));

/* ---------- State & player ---------- */
const A=new Audio();A.preservesPitch=true;
const S={ch:null,chunks:[],i:0,playing:false,tok:0,novel:null,list:null,cd:null,cache:new Map(),ac:new Map(),local:true,ready:true,pf:false,resumable:false,pend:null,orig:false};
const curTitle=()=>S.ch?.vi?.title||S.ch?.title||'';
const readHash=(u,n)=>'#/read?url='+enc(u)+(n?'&novel='+enc(n):'');
const nextUrl=()=>{const l=S.list,i=l?l.indexOf(S.ch?.url):-1;return i>=0?l[i+1]||null:S.ch?.next_url||null};
const prevUrl=()=>{const l=S.list,i=l?l.indexOf(S.ch?.url):-1;return i>0?l[i-1]:i<0?S.ch?.prev_url||null:null};
/* nút play morph: tam giác ⇄ hai thanh */
const PLAY=[9,6,16,10,16,22,9,26,16,10,25,16,25,16,16,22],PAUSE=[8,6,13,6,13,26,8,26,19,6,24,6,24,26,19,26];
const path=p=>{const a=PLAY.map((v,i)=>(v+(PAUSE[i]-v)*p).toFixed(2));return[0,8].map(k=>`M${a[k]} ${a[k+1]}L${a[k+2]} ${a[k+3]}L${a[k+4]} ${a[k+5]}L${a[k+6]} ${a[k+7]}Z`).join('')};
let mp=0,mt=0,mv=0,mr=0;$('#morph').setAttribute('d',path(0));
function morphTo(t){mt=t;if(reduced){mp=t;$('#morph').setAttribute('d',path(t));return}if(!mr)mr=requestAnimationFrame(function s(){mv=(mv+(mt-mp)*.2)*.7;mp+=mv;$('#morph').setAttribute('d',path(mp));if(Math.abs(mt-mp)<.002&&Math.abs(mv)<.002){mp=mt;$('#morph').setAttribute('d',path(mp));mr=0}else mr=requestAnimationFrame(s)})}
const C=169.65;const ring=p=>$('#ring').style.strokeDashoffset=C*(1-Math.max(0,Math.min(1,p)));
function paint(){const n=S.chunks.length,d=$('#dock');d.hidden=!S.ch;$('#d-title').textContent=curTitle()||'—';
 if(S.cd){d.classList.add('cd');$('#d-sub').textContent=`Chương sau sau ${S.cd.left}s`;$('#stay').hidden=false}
 else{d.classList.remove('cd');$('#stay').hidden=true;$('#d-sub').textContent=S.playing&&!S.ready?'Đang nạp giọng đọc… (chỉ lần đầu)':n?`Đoạn ${S.i+1}/${n}${S.playing?'':' · tạm dừng'}`:'Đang tải…';
  ring(n?(S.i+(A.duration&&S.playing?A.currentTime/A.duration:0))/n:0)}}
function setPlaying(b){S.playing=b;morphTo(b?1:0);$('#dock').classList.toggle('playing',b);if('mediaSession'in navigator)navigator.mediaSession.playbackState=b?'playing':'paused';paint()}
const WIN=()=>S.local?2:1;
async function ttsPost(text,signal){
 const r=await api('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice:settings.voice||undefined}),signal});
 if(!r.ok){let d='';try{const j=await r.json();d=typeof j.detail==='string'?j.detail:JSON.stringify(j.detail||j)}catch{try{d=await r.text()}catch{}}const err=new Error(d||('TTS HTTP '+r.status));err.status=r.status;throw err}
 return r.blob()
}
function fetchChunk(i){if(i<0||i>=S.chunks.length)return Promise.resolve(null);
 if(!S.cache.has(i)){const ac=new AbortController(),p=(async()=>{
  let last;
  for(let a=0;a<8;a++){
   try{const b=await ttsPost(S.chunks[i],ac.signal);return URL.createObjectURL(b)}
   catch(e){last=e;if(e.name==='AbortError')throw e;
    const m=String(e.message||'');
    if(e.status===503||/dang nap|dang tai|chua san sang|503/i.test(m)){if(a===0)toast('Đang nạp model…');await new Promise(r=>setTimeout(r,1200));continue}
    if(/os error 2|cannot find the file/i.test(m) && a<3){await new Promise(r=>setTimeout(r,300*(a+1));continue}
    throw e}
  }
  throw last||new Error('TTS timeout khi nạp model');
 })();p.catch(()=>{S.cache.delete(i);S.ac.delete(i)});S.cache.set(i,p);S.ac.set(i,ac)}return S.cache.get(i)}
async function playAt(i){if(!S.chunks.length)return;cancelCd();const tok=++S.tok;S.i=Math.max(0,Math.min(i,S.chunks.length-1));
 for(const[k,v]of[...S.cache]){if(k<S.i-1){v.then(u=>u&&URL.revokeObjectURL(u),()=>{});S.cache.delete(k);S.ac.delete(k)}else if(k>S.i+WIN()){S.ac.get(k)?.abort();S.cache.delete(k);S.ac.delete(k)}}
 setPlaying(true);markActive();saveProgress();
 try{const src=await fetchChunk(S.i);if(tok!==S.tok)return;A.src=src;A.playbackRate=settings.speed;await A.play();if(tok!==S.tok)return;S.resumable=true;for(let k=1;k<=WIN();k++)fetchChunk(S.i+k);maybePrefetch()}
 catch(e){if(tok!==S.tok)return;
  if(e.name==='NotAllowedError'){setPlaying(false);toast('Nhấn ▶ để tiếp tục nghe');return}
  const msg=e.message||String(e);
  // Transient os error 2: retry same segment once, then skip (model is loaded if other segs work)
  if(/os error 2|file specified|VieNeu/i.test(msg) && !S._retried){
   S._retried=true;S.cache.delete(S.i);toast('Đoạn lỗi tạm thời, thử lại…');
   setTimeout(()=>playAt(S.i),600);return}
  S._retried=false;
  if(/thieu file|chua cai|chua san sang|model loi/i.test(msg) && !/os error 2/i.test(msg)){
   setPlaying(false);S.cache.delete(S.i);
   toast(msg.slice(0,160)+' — mở Cài đặt → Tải gói giọng đọc');
   try{openSheet()}catch{};return}
  if(S.i+1<S.chunks.length){toast('Đoạn '+(S.i+1)+' lỗi, bỏ qua');S.cache.delete(S.i);playAt(S.i+1)}
  else{setPlaying(false);toast(msg)}
 }}
function toggle(){if(S.cd){cancelCd();return}if(S.playing){A.pause();setPlaying(false)}else if(S.resumable&&A.src&&!A.ended){A.play().then(()=>setPlaying(true)).catch(e=>toast(e.message))}else playAt(S.i)}
function stopAudio(){S.tok++;A.pause();A.removeAttribute('src');S.resumable=false;S.ac.forEach(a=>a.abort());S.ac.clear();S.cache.forEach(v=>v.then(u=>u&&URL.revokeObjectURL(u),()=>{}));S.cache.clear();cancelCd();S.pf=false;setPlaying(false)}
A.onended=()=>S.i+1<S.chunks.length?playAt(S.i+1):chapterEnd();
A.ontimeupdate=()=>{if(S.playing&&!S.cd)ring((S.i+(A.currentTime/(A.duration||1)))/S.chunks.length)};
function chapterEnd(){const n=nextUrl();saveProgress(true);if(!n){setPlaying(false);toast('Hết truyện — chưa có chương sau');return}
 S.cd={left:3};paint();ring(1);S.cd.t=setInterval(()=>{S.cd.left--;paint();if(S.cd.left<=0){cancelCd();gotoChapter(n,{autoplay:true,translate:!!S.ch.vi})}},1000)}
function cancelCd(){if(S.cd){clearInterval(S.cd.t);S.cd=null;paint()}}
function gotoChapter(u,o){S.pend=o||null;location.hash=readHash(u,S.novel)}
function saveProgress(done){if(!S.ch?.url)return;idb.put('progress',{url:S.ch.url,title:curTitle(),novel:S.novel,novelTitle:S.novelTitle||'',chunk:done?S.chunks.length-1:S.i,total:S.chunks.length,t:Date.now()})}
function maybePrefetch(){const n=nextUrl();if(!settings.prefetch||S.pf||!n||S.i<S.chunks.length*.6)return;S.pf=true;
 api('/api/chapter?url='+enc(n)).then(r=>r.json()).then(c=>{c.url=n;idb.put('chapters',c);if(c.lang==='vi')post('/api/prefetch',{urls:[n],voice:settings.voice||undefined})}).catch(()=>{})}
function setMedia(){if(!('mediaSession'in navigator))return;navigator.mediaSession.metadata=new MediaMetadata({title:curTitle(),artist:S.novelTitle||'VibeRead'});const h=(a,f)=>{try{navigator.mediaSession.setActionHandler(a,f)}catch{}};
 h('play',()=>{if(!S.playing)toggle()});h('pause',()=>{if(S.playing)toggle()});h('nexttrack',()=>step(1));h('previoustrack',()=>step(-1))}
function step(d){const u=d>0?nextUrl():prevUrl();if(!u)return toast(d>0?'Chưa có chương sau':'Chưa có chương trước');gotoChapter(u,{autoplay:S.playing,translate:!!S.ch.vi})}

/* ---------- Reader ---------- */
function markActive(){$$('#text p.on').forEach(p=>p.classList.remove('on'));const p=$(`#text p[data-i="${S.i}"]`);if(p){p.classList.add('on');if(S.playing)p.scrollIntoView({block:'center',behavior:reduced?'auto':'smooth'})}}
function renderText(){const src=S.orig&&S.ch.vi?S.ch.vi.original_chunks:S.chunks;$('#text').replaceChildren(...src.map((t,i)=>{const p=document.createElement('p');p.textContent=t;p.dataset.i=i;p.onclick=()=>{if(!(S.orig&&S.ch.vi))playAt(i)};return p}));markActive()}
function renderBanner(){const b=$('#banner'),ch=S.ch;if(!ch||ch.loading||ch.lang==='vi'){b.hidden=true;return}b.hidden=false;
 const L={zh:'tiếng Trung',ja:'tiếng Nhật',ko:'tiếng Hàn',en:'tiếng Anh'}[ch.lang]||ch.lang;
 b.innerHTML=ch.vi?`<span>Đã dịch từ ${L}.</span><button class="pill" id="b-orig">${S.orig?'Xem bản dịch':'Xem bản gốc'}</button>`:`<span>Chương này viết bằng ${L}. Dịch sang tiếng Việt để nghe.</span><button class="pill hot" id="b-tr">Dịch &amp; nghe</button>`;
 $('#b-tr')&&($('#b-tr').onclick=()=>translateChapter(true));$('#b-orig')&&($('#b-orig').onclick=()=>{S.orig=!S.orig;renderText();renderBanner()})}
function skeleton(){$('#ch-kicker').textContent='';$('#ch-title').textContent='';$('#banner').hidden=true;$('#text').replaceChildren();$('#state').innerHTML=Array.from({length:9},(_,i)=>`<div class="sk" style="width:${i%4==3?'60':'100'}%"></div>`).join('')}
function applyText(t){S.chunks=t.chunks;$('#ch-title').textContent=t.title||S.ch.title;$('#ch-kicker').textContent=S.novelTitle||(()=>{try{return new URL(S.ch.url).hostname}catch{return''}})()}
async function translateChapter(play){const ch=S.ch;$('#b-tr')&&($('#b-tr').textContent='Đang dịch…');
 const hdr={};if(settings.key){hdr['X-Api-Key']=settings.key;if(/^sk-ant-/.test(settings.key))hdr['X-Anthropic-Key']=settings.key;else hdr['X-OpenAI-Key']=settings.key}
 try{const r=await post('/api/translate',{url:ch.url,novel_key:S.novel||ch.url},hdr);const j=await r.json();if(S.ch!==ch)return;
  ch.vi={title:j.title,chunks:j.chunks,original_chunks:j.original_chunks||[]};idb.put('chapters',ch);applyText(ch.vi);renderText();renderBanner();paint();setMedia();if(play)playAt(0)}
 catch(e){toast(e.message);renderBanner();if(/key/i.test(e.message))openSheet()}}
async function openChapter(url,o={}){stopAudio();S.novel=o.novel||null;S.list=null;S.novelTitle='';S.orig=false;S.ch={url,loading:true};S.chunks=[];S.i=0;skeleton();paint();
 try{let ch=await idb.get('chapters',url);if(!ch||!ch.chunks)ch=await(await api('/api/chapter?url='+enc(url))).json();ch.url=url;idb.put('chapters',ch);if(S.ch?.url!==url)return;
  S.ch=ch;if(S.novel){const n=await idb.get('novels',S.novel);S.list=n?.chapters?.map(c=>c.url)||null;S.novelTitle=n?.title||''}
  $('#state').innerHTML='';
  if(ch.lang!=='vi'&&!ch.vi){applyText(ch);renderText();renderBanner();paint();setMedia();
   const wantTr=o.translate||settings.autoTranslate;
   if(wantTr){translateChapter(!!(o.autoplay||settings.autoTranslate));return}
   if(o.autoplay){setPlaying(false)}return}
  applyText(ch.vi||ch);const pr=await idb.get('progress',url);S.i=pr&&pr.chunk<S.chunks.length-1?pr.chunk:0;
  renderText();renderBanner();paint();setMedia();if(o.autoplay)playAt(0);else if(S.local){fetchChunk(S.i);fetchChunk(S.i+1)}}
 catch(e){if(S.ch?.url!==url)return;S.ch=null;paint();$('#state').innerHTML=`<div class="err"><strong>Không tải được chương</strong><p>${esc(e.message)}</p><button class="pill hot" id="retry">Thử lại</button></div>`;$('#retry').onclick=()=>openChapter(url,o)}}

/* ---------- Novel & Home ---------- */
async function openNovel(url){const head=$('#novel-head'),ol=$('#chapters');head.innerHTML='<div class="sk" style="width:60%;height:3rem"></div>';ol.replaceChildren();
 try{const n=await(await api('/api/novel?url='+enc(url))).json();n.url=url;idb.put('novels',n);const prog=new Map((await idb.all('progress')||[]).map(p=>[p.url,p]));
  head.innerHTML=`${n.cover?`<img src="${esc(n.cover)}" alt="">`:''}<div><p class="kicker">${n.chapters.length} chương</p><h1>${esc(n.title)}</h1></div>`;
  if(!n.chapters.length){ol.innerHTML='<li class="empty">Chưa nhận diện được mục lục. Dán link một chương để nghe.</li>';return}
  let shown=0;const more=()=>{n.chapters.slice(shown,shown+300).forEach(c=>{const p=prog.get(c.url),li=document.createElement('li');li.innerHTML=`<button class="${p&&p.chunk>=p.total-1?'done':p?'cur':''}"><span>${esc(c.title)}</span><span>${p?(p.chunk>=p.total-1?'✓':Math.round(p.chunk/p.total*100)+'%'):''}</span></button>`;li.firstChild.onclick=()=>go(readHash(c.url,url));ol.append(li)});shown+=300;if(shown<n.chapters.length){const li=document.createElement('li');li.innerHTML='<button><span>Hiện thêm…</span></button>';li.firstChild.onclick=()=>{li.remove();more()};ol.append(li)}};more()}
 catch(e){head.innerHTML=`<div class="err"><strong>Không đọc được trang truyện</strong><p>${esc(e.message)}</p></div>`}}
async function renderRecent(){const all=((await idb.all('progress'))||[]).sort((a,b)=>b.t-a.t).slice(0,8),box=$('#recent');
 if(!all.length){box.innerHTML='<div class="empty"><i class="eq"><b></b><b></b><b></b><b></b></i><span>Chưa có gì để nghe. Dán link chương bạn đang đọc ở trên — app sẽ nhớ đến từng đoạn.</span></div>';return}
 box.replaceChildren(...all.map(p=>{const b=document.createElement('button');b.className='card';b.innerHTML=`<small>${esc(p.novelTitle||'Đang nghe')}</small><strong>${esc(p.title||p.url)}</strong><i style="transform:scaleX(${p.total?p.chunk/p.total:0})"></i>`;b.onclick=()=>go(readHash(p.url,p.novel));return b}))}
$('#add').onsubmit=async e=>{e.preventDefault();const u=$('#url').value.trim(),b=$('#go');b.classList.add('busy');b.firstChild.textContent='…';
 try{const r=await(await api('/api/resolve?url='+enc(u))).json();go((r.kind==='novel'?'#/novel?url=':'#/read?url=')+enc(u))}catch(e){toast(e.message)}finally{b.classList.remove('busy');b.firstChild.textContent='Nghe'}};

/* ---------- Router ---------- */
function go(h){location.hash===h?route():location.hash=h}
function show(n){$$('.view').forEach(v=>v.hidden=v.id!=='v-'+n);hero.active(n==='home');scrollTo(0,0)}
function route(){const[p,qs]=(location.hash.slice(1)||'/').split('?'),q=new URLSearchParams(qs||''),u=q.get('url');
 const run=f=>document.startViewTransition&&!reduced?document.startViewTransition(f):f();
 if(p==='/read'&&u)run(()=>{show('read');if(S.ch?.url!==u){const o={novel:q.get('novel'),...(S.pend||{})};S.pend=null;openChapter(u,o)}else{renderText();renderBanner()}});
 else if(p==='/novel'&&u)run(()=>{show('novel');openNovel(u)});
 else run(()=>{show('home');renderRecent()})}
addEventListener('hashchange',route);

/* ---------- Settings sheet ---------- */
let voicesLoaded=false;
async function openSheet(){$('#sheet').hidden=false;$$('#s-theme button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===settings.theme));
 $('#s-fs').value=settings.fs;$('#o-fs').textContent=settings.fs+'px';$('#s-lh').value=settings.lh;$('#o-lh').textContent=settings.lh;$('#s-pf').checked=settings.prefetch;$('#s-autotr')&&($('#s-autotr').checked=!!settings.autoTranslate);$('#s-key').value=settings.key;
 if(!voicesLoaded){voicesLoaded=true;try{const h=await(await api('/api/health')).json();$('#s-info').textContent=`TTS: ${h.tts}${h.tts_key?'':' · chưa có key'} · dịch: ${h.translate_key?'key server OK':'nhập key bên trên'}${h.playwright?' · Playwright: sẵn sàng':''}`;
  let v=await(await api('/api/voices')).json();v=Array.isArray(v)?v:v.voices||[];const s=$('#s-voice');v.forEach(x=>{const id=typeof x==='string'?x:x.id||x.name,o=new Option(typeof x==='string'?x:x.name||id,id);s.add(o)});s.value=settings.voice}catch(e){$('#s-info').textContent+=' · không tải được danh sách giọng'}}}
const closeSheet=()=>$('#sheet').hidden=true;
$('#open-settings').onclick=openSheet;$$('[data-close]').forEach(b=>b.onclick=closeSheet);addEventListener('keydown',e=>{if(e.key==='Escape')closeSheet()});
$$('#s-theme button').forEach(b=>b.onclick=()=>{settings.theme=b.dataset.v;saveS();applyS();openSheet()});
const bind=(id,k,f=v=>v,after)=>$(id).oninput=e=>{settings[k]=f(e.target.type==='checkbox'?e.target.checked:e.target.value);saveS();applyS();after&&after()};
bind('#s-fs','fs',Number,()=>$('#o-fs').textContent=settings.fs+'px');bind('#s-lh','lh',Number,()=>$('#o-lh').textContent=settings.lh);bind('#s-pf','prefetch');
 if($('#s-autotr'))$('#s-autotr').onchange=()=>{settings.autoTranslate=$('#s-autotr').checked;saveS()};
 bind('#s-key','key',v=>v.trim());
$('#s-voice').onchange=e=>{settings.voice=e.target.value;saveS();S.ac.forEach(a=>a.abort());S.ac.clear();S.cache.clear()};

/* ---------- Dock & phím tắt ---------- */
$('#play').onclick=toggle;$('#stay').onclick=cancelCd;$('#next').onclick=()=>step(1);$('#prev').onclick=()=>step(-1);
$('#meta').onclick=()=>S.ch&&go(readHash(S.ch.url,S.novel));
$('#speed').onclick=()=>{const L=[.75,1,1.25,1.5,1.75];settings.speed=L[(L.indexOf(settings.speed)+1)%L.length];saveS();applyS();A.playbackRate=settings.speed};
addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if(e.code==='Space'&&S.ch){e.preventDefault();toggle()}if(e.key==='ArrowRight')playAt(S.i+1);if(e.key==='ArrowLeft')playAt(S.i-1)});
if('serviceWorker'in navigator)addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
applyS();addEventListener('DOMContentLoaded',()=>{});hero.init();route();

function updateModelUI(h){
 const st=$('#s-model-status'),btn=$('#s-dl-model');
 if(!st)return;
 if(h.tts_downloading){st.textContent='Đang tải model… '+ (h.tts_download_msg||'');if(btn){btn.disabled=true;btn.classList.add('busy');btn.textContent='Đang tải…'}}
 else if(h.tts_ready){st.textContent='Model giọng đọc: sẵn sàng'+(h.tts_cached?' (đã cache/bundle)':'');if(btn){btn.disabled=false;btn.classList.remove('busy');btn.textContent='Tải lại gói giọng đọc'}}
 else if(h.tts_error){st.textContent='Model lỗi: '+h.tts_error;if(btn){btn.disabled=false;btn.classList.remove('busy');btn.textContent='Tải gói giọng đọc'}}
 else{st.textContent='Model chưa sẵn sàng — bấm tải nếu nghe lỗi';if(btn){btn.disabled=false;btn.classList.remove('busy');btn.textContent='Tải gói giọng đọc'}}
}
async function pollTTS(){try{const h=await(await api('/api/health')).json(),c=$('#tts-chip');S.local=h.tts!=='cloud';
 updateModelUI(h);
 if(h.tts_downloading){S.ready=false;c.hidden=false;c.className='chip';c.textContent='Đang tải model…';setTimeout(pollTTS,2000);paint();return}
 if(h.tts_error){S.ready=false;c.hidden=false;c.className='chip';c.textContent='Giọng đọc lỗi — mở Cài đặt để tải model';toast('VieNeu: '+h.tts_error);paint();return}
 S.ready=h.tts_ready;c.hidden=false;
 if(!h.tts_ready){c.className='chip';c.textContent='Đang nạp giọng đọc…';setTimeout(pollTTS,1500)}
 else{c.className='chip ok';c.textContent='Giọng sẵn sàng';setTimeout(()=>c.hidden=true,2500)}paint()}catch{setTimeout(pollTTS,3000)}}
pollTTS();

$('#s-dl-model')?.addEventListener('click',async()=>{
 const btn=$('#s-dl-model');btn.disabled=true;btn.classList.add('busy');btn.textContent='Đang tải…';
 $('#s-model-status').textContent='Đang tải model giọng đọc (có thể vài phút, cần mạng)…';
 try{
  const r=await api('/api/tts/download-model',{method:'POST'});
  const j=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(j.detail||j.message||r.statusText);
  toast('Đã tải model xong');
  pollTTS();
 }catch(e){toast('Tải model thất bại: '+e.message);$('#s-model-status').textContent='Lỗi: '+e.message;btn.disabled=false;btn.classList.remove('busy');btn.textContent='Tải gói giọng đọc'}
});
