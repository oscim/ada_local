// ════════════════════════════════════════════════════════════════
//  ADA v3 — Shell JS
//  Chat SSE réel · Auth JWT · Status · UI locale
// ════════════════════════════════════════════════════════════════

// ── Token ──────────────────────────────────────────────────────
function _getToken(){return localStorage.getItem('ada_token');}
function _setToken(t){localStorage.setItem('ada_token',t);}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg){
  const el=document.getElementById('toast');
  if(!el)return;
  el.textContent=msg;
  el.classList.add('on');
  clearTimeout(el._t);
  el._t=setTimeout(()=>el.classList.remove('on'),3000);
}

// ── Auth ───────────────────────────────────────────────────────
async function _checkAuth(){
  try{
    const cfg=await fetch('/api/auth/config').then(r=>r.json());
    if(!cfg.enabled)return true;
  }catch{return true;}
  const token=_getToken();
  if(!token)return false;
  try{
    const r=await fetch('/api/auth/me',{headers:{'Authorization':'Bearer '+token}});
    return r.ok;
  }catch{return false;}
}

async function _showAuth(){
  const screen=document.getElementById('auth-screen');
  const vp=document.getElementById('auth-viewport');
  screen.style.display='block';
  let _authMod=null;
  try{
    _authMod=await import('/static/views/auth/index.js');
    await _authMod.mount(vp);
  }catch(e){
    vp.innerHTML='<div style="color:var(--text);text-align:center;padding:40px"><div style="font-size:32px;margin-bottom:12px">🔒</div><div style="font-size:14px">Connexion requise</div><div style="font-size:11px;color:var(--text-dim);margin-top:6px">Ouvrez ADA depuis l\'appareil enregistré</div></div>';
  }
  // Polling jusqu'à auth OK
  const iv=setInterval(async()=>{
    if(await _checkAuth()){
      clearInterval(iv);
      _authMod?.unmount?.();
      screen.style.display='none';
      await _onAuthenticated();
    }
  },2000);
}

let _activeUni='dash',_activeSub='';
async function _onAuthenticated(){
  _activeUni='dash';_activeSub='';
  const _dashCtx=_UNI_CTX&&_UNI_CTX.dash;
  _activeCtxText=_dashCtx?_dashCtx.text||'':'';
  _activeDomain=_dashCtx?_dashCtx.domain:null;
  const profile=await _fetchProfile();
  _applyProfile(profile);
  await _buildNavFromUniverses();
  await _loadStatus();
  _initChatModelSel();
  // Charger le premier onglet du dashboard (dynamique ou statique)
  const firstDashStab=document.querySelector('#uni-dash .stab');
  const firstDashSubId=firstDashStab?.getAttribute('onclick')?.match(/goSub\(this,'([^']+)'\)/)?.[1];
  if(firstDashSubId&&_VIEW_OVERRIDES[firstDashSubId]){
    const[v,o]=_VIEW_OVERRIDES[firstDashSubId];
    _loadSubView(firstDashSubId,v,o);
  } else {
    _loadSubView('sub-dash-overview','dashboard');
  }
  _renderPluginCtxBar('dash');
}

// ── Construction dynamique de la nav depuis le profil (ou /api/universes en fallback) ────────
async function _buildNavFromUniverses(){
  // Toujours charger la liste globale ordonnée par position (pas de filtre profil)
  let universes=[];
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    const r=await fetch('/api/universes',{headers:h});
    if(r.ok) universes=(await r.json()).universes||[];
  }catch{}
  if(!universes.length)return;

  const content=document.getElementById('content');
  const dynSlot=document.getElementById('dyn-nav-btns');
  if(!content||!dynSlot)return;

  dynSlot.innerHTML='';
  content.querySelectorAll('.uni-panel-dyn').forEach(el=>el.remove());

  for(const u of universes){
    const uId=u.id;
    UNI_LABELS[uId]=u.name;

    const isDash=u.modules&&u.modules.includes('dashboard');
    if(isDash){
      UNI_LABELS['dash']=u.name||'Dashboard';
      // Mettre à jour le texte du bouton statique si renommé
      const staticBtn=document.querySelector('[data-uni="dash"]');
      if(staticBtn){
        const tip=staticBtn.querySelector('.nav-tip');
        const lbl=staticBtn.querySelector('.nav-label');
        if(tip) tip.textContent=u.name;
        if(lbl) lbl.textContent=u.name;
      }
      // Construire les onglets de uni-dash dynamiquement (sub IDs statiques de _MOD_TAB)
      const dashPanel=document.getElementById('uni-dash');
      if(dashPanel){
        const tabs=[];
        for(const modId of (u.modules||[])){
          const def=_MOD_TAB[modId];
          if(!def)continue;
          tabs.push({...def,modId});
        }
        if(tabs.length){
          dashPanel.querySelectorAll('.subtab-bar').forEach(el=>el.remove());
          const tabBar=document.createElement('div');
          tabBar.className='subtab-bar';
          tabBar.innerHTML=tabs.map((t,i)=>
            `<div class="stab${i===0?' on':''}" onclick="goSub(this,'${t.sub}')">${t.label}</div>`
          ).join('');
          dashPanel.insertBefore(tabBar,dashPanel.firstChild);
          tabs.forEach((t,i)=>{
            if(!document.getElementById(t.sub)){
              const sv=document.createElement('div');
              sv.className='subview'+(i===0?' on':'');
              sv.id=t.sub;
              dashPanel.appendChild(sv);
            }
            if(t.view) _VIEW_OVERRIDES[t.sub]=[t.view,t.opts||{}];
            _VIEW_LABELS[t.sub]=t.label;
            // Maintenir _V2U pour adaNavigate
            if(t.modId==='dashboard') _V2U[t.modId]='dash';
            else _V2U[t.modId]=['dash',t.sub];
          });
        }
      }
      continue;
    }

    // Panel dynamique normal
    const sep=document.createElement('div');
    sep.className='nav-sep';
    const btn=document.createElement('div');
    btn.className='nav-btn';
    btn.dataset.uni=uId;
    btn.innerHTML=`${u.icon||'◈'}<span class="nav-tip">${u.name}</span><span class="nav-label">${u.name}</span>`;
    btn.addEventListener('click',()=>goUni(uId,btn));
    dynSlot.appendChild(sep);
    dynSlot.appendChild(btn);

    const panel=document.createElement('div');
    panel.className='uni-panel uni-panel-dyn';
    panel.id='uni-'+uId;
    content.appendChild(panel);

    const tabs=[];
    for(const modId of (u.modules||[])){
      const def=_MOD_TAB[modId];
      if(!def)continue;
      const subId=uId+'-'+modId;
      tabs.push({...def,modId,sub:subId});
    }
    if(!tabs.length)continue;

    const tabBar=document.createElement('div');
    tabBar.className='subtab-bar';
    tabBar.innerHTML=tabs.map((t,i)=>
      `<div class="stab${i===0?' on':''}" onclick="goSub(this,'${t.sub}')">${t.label}</div>`
    ).join('');
    panel.appendChild(tabBar);

    tabs.forEach((t,i)=>{
      const sv=document.createElement('div');
      sv.className='subview'+(i===0?' on':'');
      sv.id=t.sub;
      panel.appendChild(sv);
      if(t.view) _VIEW_OVERRIDES[t.sub]=[t.view,t.opts||{}];
      _VIEW_LABELS[t.sub]=t.label;
      // Maintenir _V2U pour adaNavigate (remplace les anciens IDs statiques)
      _V2U[t.modId]=[uId,t.sub];
    });
  }
}

// ── Module → sous-vue (onglets dynamiques par univers) ──────────
const _MOD_TAB = {
  'home':           {sub:'sub-domo',         label:'Domotique',     view:'page',     opts:{page:'home',hint:'État domotique complet'}},
  'cameras':        {sub:'sub-cameras',      label:'Caméras',       view:'cameras',  opts:{}},
  'senses':         {sub:'sub-senses',       label:'Capteurs',      view:'page',     opts:{page:'senses',hint:'État capteurs'}},
  'music':          {sub:'sub-music',        label:'Musique',       view:'page',     opts:{page:'music',hint:'Lecteur musique'}},
  'infrastructure': {sub:'sub-infra',        label:'Infrastructure',view:'infra',    opts:{}},
  'societe':        {sub:'sub-soc',          label:'Sociétés',      view:'societe',  opts:{}},
  'marketing':      {sub:'sub-mkt',          label:'Marketing',     view:'marketing',opts:{}},
  'planner':        {sub:'sub-agenda',       label:'Agenda',        view:'planner',  opts:{}},
  'briefing':       {sub:'sub-briefing',     label:'Briefing',      view:'briefing', opts:{}},
  'skills':         {sub:'sub-skills',       label:'Compétences',   view:'skills',   opts:{}},
  'memory':         {sub:'sub-mem',          label:'Mémoire',       view:'memory',   opts:{}},
  'settings':       {sub:'sub-settings',     label:'Paramètres',    view:'settings', opts:{}},
  'printers':       {sub:'sub-rmm',          label:'RMM',           view:'page',     opts:{page:'printers',hint:'RMM clients actifs'}},
  'webagent':       {sub:'sub-webagent',     label:'Web Agent',     view:'webagent', opts:{}},
  'dashboard':      {sub:'sub-dash-overview',label:"Vue d'ensemble",view:'dashboard',opts:{}},
};
// Registres des vues dynamiques
const _VIEW_OVERRIDES = {};  // subId → [viewName, opts]
const _VIEW_LABELS    = {};  // subId → label (breadcrumb)

// ── Profil (thème + densité + univers depuis /api/profile) ───────
async function _fetchProfile(){
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    const r=await fetch('/api/profile',{headers:h});
    if(!r.ok)return null;
    const p=await r.json();
    return p.profile||p||null;
  }catch{return null;}
}

function _applyProfile(prof){
  if(!prof)return;
  if(prof.theme){
    document.documentElement.setAttribute('data-theme',prof.theme);
    document.querySelectorAll('.t-dot').forEach(d=>d.classList.toggle('on',d.dataset.t===prof.theme));
    setTimeout(drawSparks,40);
  }
  if(prof.density){
    document.documentElement.setAttribute('data-density',prof.density);
    document.querySelectorAll('.d-btn').forEach(b=>b.classList.toggle('on',b.dataset.d===prof.density));
  }
}

// ── Status pills (/api/dashboard) ───────────────────────────────
function _pctClass(p){ return p>=85?'c-red':p>=65?'c-orange':''; }
async function _loadStatus(){
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    const [st, d] = await Promise.all([
      fetch('/api/status',{headers:h}).then(r=>r.json()).catch(()=>({})),
      fetch('/api/dashboard',{headers:h}).then(r=>r.json()).catch(()=>null),
    ]);
    // LLM pill — modèle chat + modèle embed depuis /api/dashboard
    const llmPill=document.getElementById('pill-llm');
    if(llmPill && d){
      const dot=llmPill.querySelector('.s-dot');
      const ok=st.ollama==='online'||d.ollama==='online';
      if(dot){dot.className='s-dot '+(ok?'dot-g pulse':'dot-r');}
      const vChat=document.getElementById('v-llm-chat');
      const vEmbed=document.getElementById('v-llm-embed');
      if(vChat){vChat.textContent=ok?(d.model||'LLM').replace(':latest',''):'Offline';}
      if(vEmbed){
        const em=(d.embed_model||'').replace(':latest','');
        vEmbed.textContent=em?'· '+em:'';
      }
    }
    // Métriques système
    if(d){
      const cpu=d.cpu_pct??0;
      const ram=d.ram;
      const vram=d.vram;
      const vc=document.getElementById('val-cpu');
      if(vc){vc.textContent=cpu+'%';vc.className=_pctClass(cpu);}
      const vr=document.getElementById('val-ram');
      if(vr && ram){
        vr.textContent=ram.pct+'% ('+ram.used_gb+'/'+ram.total_gb+' GB)';
        vr.className=_pctClass(ram.pct);
      }
      const vg=document.getElementById('val-gpu');
      const vv=document.getElementById('val-vram');
      if(vram){
        const gpuPct=vram.total_gb>0?Math.round(vram.used_gb/vram.total_gb*100):0;
        if(vg){vg.textContent=gpuPct+'%';vg.className=_pctClass(gpuPct);}
        if(vv){vv.textContent=vram.used_gb+'/'+vram.total_gb+' GB';vv.className=_pctClass(gpuPct);}
      } else {
        if(vg){vg.textContent='—';vg.className='';}
        if(vv){vv.textContent='—';vv.className='';}
      }
    }
  }catch{}
}
setInterval(_loadStatus, 10000);

// ── Chat SSE ───────────────────────────────────────────────────
const _chatMsgs=document.getElementById('chat-msgs');
const _chatInput=document.getElementById('chat-input');
const _history=[];

function inject(t){_chatInput.value=t;_chatInput.focus();autoResize(_chatInput);}
function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,80)+'px';}
function handleKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}}

function _appendMsg(t,who){
  const d=document.createElement('div');
  d.className='msg msg-'+who;
  if(who==='ada')d.innerHTML='<div class="from"></div>'+t.replace(/\n/g,'<br>');
  else d.textContent=t;
  _chatMsgs.appendChild(d);
  _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
  return d;
}

function _attachFeedback(bubble, requestId){
  if(!requestId) return;
  const footer=document.createElement('div');
  footer.className='msg-feedback';
  footer.innerHTML=`
    <button class="fb-btn fb-positive" data-request-id="${requestId}" title="Réponse utile">👍</button>
    <button class="fb-btn fb-negative" data-request-id="${requestId}" title="Réponse incorrecte">👎</button>`;
  const commentArea=document.createElement('div');
  commentArea.className='fb-comment-area';
  commentArea.style.display='none';
  commentArea.innerHTML=`
    <textarea class="fb-textarea" maxlength="140" placeholder="Qu'est-ce qui n'allait pas ? (optionnel)"></textarea>
    <div class="fb-comment-actions">
      <button class="fb-send">Envoyer</button>
      <button class="fb-skip">Ignorer</button>
    </div>`;
  bubble.appendChild(footer);
  bubble.appendChild(commentArea);
  const posBtn=footer.querySelector('.fb-positive');
  const negBtn=footer.querySelector('.fb-negative');
  const textarea=commentArea.querySelector('.fb-textarea');
  const sendBtn=commentArea.querySelector('.fb-send');
  const skipBtn=commentArea.querySelector('.fb-skip');
  let sent=false;
  async function _sendSignal(signal,comment){
    if(sent)return; sent=true;
    const summary=bubble.textContent.slice(0,80);
    try{
      await fetch('/api/feedback/response',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:requestId,signal,comment:comment||null,response_summary:summary}),
      });
    }catch{/*silencieux*/}
    posBtn.style.opacity=signal==='positive'?'1':'0.2';
    negBtn.style.opacity=signal==='negative'?'1':'0.2';
    commentArea.style.display='none';
  }
  posBtn.addEventListener('click',()=>_sendSignal('positive'));
  negBtn.addEventListener('click',()=>{if(sent)return;commentArea.style.display='block';textarea.focus();});
  sendBtn.addEventListener('click',()=>_sendSignal('negative',textarea.value.trim()));
  skipBtn.addEventListener('click',()=>_sendSignal('negative',null));
  textarea.addEventListener('keydown',(e)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();_sendSignal('negative',textarea.value.trim());}});
}

async function sendMsg(){
  const t=_chatInput.value.trim();
  if(!t)return;
  _appendMsg(t,'user');
  _history.push({role:'user',content:t});
  _chatInput.value='';_chatInput.style.height='auto';

  const typing=document.getElementById('typing');
  typing.classList.add('on');
  _chatMsgs.scrollTop=_chatMsgs.scrollHeight;

  const histSlice=_history.slice(-10);
  const histForSend=_activeCtxText
    ?[{role:'user',content:`Contexte actif :\n${_activeCtxText}`},{role:'assistant',content:'Contexte pris en compte.'},...histSlice]
    :histSlice;

  const token=_getToken();
  const headers={'Content-Type':'application/json'};
  if(token)headers['Authorization']='Bearer '+token;

  try{
    const r=await fetch('/api/chat',{
      method:'POST',headers,
      body:JSON.stringify({
        message:t,
        history:histForSend,
        company_context:_activeUni==='co'?(_socCtxId||null):null,
        plugin_context:_activePluginCtx||null,
        context_id:_activeCtxId||null,
        context:`Univers: ${_activeUni}${_activeSub?' › '+_activeSub:''}`,
      }),
    });
    typing.classList.remove('on');
    if(!r.ok){_appendMsg('Erreur '+r.status,'ada');return;}

    const msgEl=document.createElement('div');
    msgEl.className='msg msg-ada';
    msgEl.innerHTML='<div class="from"></div><div class="_think" style="font-size:.72rem;color:var(--text-dim,#64748b);margin-bottom:4px;line-height:1.6"></div><span class="_body"></span>';
    _chatMsgs.appendChild(msgEl);
    _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
    const bodyEl=msgEl.querySelector('._body');
    const thinkEl=msgEl.querySelector('._think');

    const reader=r.body.getReader();
    const decoder=new TextDecoder();
    let buf='',fullText='';
    let _thisReqId=null; // A-005 : request_id de cette conversation

    // Rendu markdown avec blocs de code copiables
    const _COPY_ICO=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    function _esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
    function _inlineText(s){
      const parts=[];let last=0;
      for(const m of s.matchAll(/`([^`\n]+)`/g)){
        parts.push(_esc(s.slice(last,m.index)));
        parts.push(`<code class="inline-code">${_esc(m[1])}</code>`);
        last=m.index+m[0].length;
      }
      parts.push(_esc(s.slice(last)));
      return parts.join('').replace(/\n/g,'<br>');
    }
    function _md(t){
      let html='';let last=0;
      for(const m of t.matchAll(/```([\w-]*)\n?([\s\S]*?)```/g)){
        // texte avant le bloc
        html+=_inlineText(t.slice(last,m.index))
          .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
          .replace(/\*([^*\n]+)\*/g,'<em>$1</em>')
          .replace(/^#{1,3} (.+)$/gm,'<strong style="font-size:1.05em;display:block;margin:8px 0 3px">$1</strong>')
          .replace(/^[-•] (.+)$/gm,'• $1');
        const lang=m[1]||'';
        const code=m[2].replace(/\n$/,'');
        html+=`<div class="code-block"><div class="code-header"><span class="code-lang">${_esc(lang)}</span><button class="copy-btn" title="Copier">${_COPY_ICO}</button></div><pre><code>${_esc(code)}</code></pre></div>`;
        last=m.index+m[0].length;
      }
      html+=_inlineText(t.slice(last))
        .replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>')
        .replace(/\*([^*\n]+)\*/g,'<em>$1</em>')
        .replace(/^#{1,3} (.+)$/gm,'<strong style="font-size:1.05em;display:block;margin:8px 0 3px">$1</strong>')
        .replace(/^[-•] (.+)$/gm,'• $1');
      return html;
    }
    function _attachCopyBtns(el){
      el.querySelectorAll('.copy-btn').forEach(btn=>{
        btn.addEventListener('click',async()=>{
          const code=btn.closest('.code-block').querySelector('code').textContent;
          try{await navigator.clipboard.writeText(code);}catch{
            const ta=Object.assign(document.createElement('textarea'),{value:code});
            document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
          }
          btn.innerHTML='✓ Copié';btn.classList.add('copied');
          setTimeout(()=>{btn.innerHTML=_COPY_ICO;btn.classList.remove('copied');},2000);
        });
      });
    }

    while(true){
      const{done,value}=await reader.read();
      if(done)break;
      buf+=decoder.decode(value,{stream:true});
      const lines=buf.split('\n');buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data:'))continue;
        const data=line.slice(5).trim();
        if(data==='[DONE]'){buf='';break;}
        try{
          const j=JSON.parse(data);

          // A-005 : capter le request_id émis en premier chunk meta
          if(j.type==='meta' && j.request_id){
            _thisReqId=j.request_id;
            _radarCurrentReqId=j.request_id;
            _radarScope='conv';
            document.querySelectorAll('.radar-filter-btn').forEach(b=>b.classList.remove('on'));
            document.getElementById('radar-scope-conv')?.classList.add('on');
            continue;
          }

          if(j.__type==='confirm_required'){
            _appendConfirmCard(msgEl,j.func,j.message,JSON.parse(j.params||'{}'),j.cmd||'');
            break;
          }
          if(j.img_url){
            bodyEl.innerHTML+=`<img src="${j.img_url}" style="max-width:100%;border-radius:6px;margin-top:6px;display:block" loading="lazy">`;
            _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
            continue;
          }
          if(j.thinking){
            thinkEl.innerHTML+='<span style="opacity:.7">'+j.thinking+'</span><br>';
            _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
            continue;
          }
          if(j.text){
            // Masquer les étapes de réflexion une fois la réponse réelle arrivée
            if(thinkEl.children.length>0) thinkEl.style.display='none';
            fullText+=j.text;
            bodyEl.innerHTML=_md(fullText);
            _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
          }
        }catch{}
      }
    }
    if(fullText){
      // Rendu final + boutons copier
      bodyEl.innerHTML=_md(fullText);
      _attachCopyBtns(bodyEl);
      _history.push({role:'assistant',content:fullText});
      _speakIfEnabled(fullText);
      // A-004 : indicateur de santé Radar
      if(_thisReqId) _appendRadarHealthDot(msgEl, _thisReqId);
      // Feedback 👍/👎
      _attachFeedback(msgEl, _thisReqId);
    }
  }catch(e){
    typing.classList.remove('on');
    _appendMsg('Erreur réseau : '+e.message,'ada');
  }
}

function confirmAct(btn){
  btn.closest('.action-card').innerHTML='<span style="color:var(--green)">✓ Confirmé — exécution en cours…</span>';
  setTimeout(()=>_appendMsg('Backup lancé ✓ — Job #4821 · durée estimée 12 min.','ada'),1200);
}
function cancelAct(btn){
  btn.closest('.action-card').innerHTML='<span style="color:var(--text-dim)">✕ Action annulée.</span>';
}

// ── TTS / STT ─────────────────────────────────────────────────
let _ttsEnabled = localStorage.getItem('ada-tts') !== 'false';
let _recognition = null;
let _sttInited = false;

function _updateTtsBtn(){
  const btn=document.getElementById('tts-btn');
  const on=document.getElementById('tts-on');
  const off=document.getElementById('tts-off');
  if(!btn)return;
  btn.classList.toggle('active', _ttsEnabled);
  if(on) on.style.display = _ttsEnabled ? '' : 'none';
  if(off) off.style.display = _ttsEnabled ? 'none' : '';
  btn.title = _ttsEnabled ? 'Désactiver la voix' : 'Activer la voix';
}

function toggleTts(){
  _ttsEnabled = !_ttsEnabled;
  localStorage.setItem('ada-tts', _ttsEnabled);
  _updateTtsBtn();
  showToast(_ttsEnabled ? '🔊 Voix activée' : '🔇 Voix désactivée');
}

function _speakIfEnabled(text){
  if(!_ttsEnabled || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const sentences = text.match(/[^.!?]+[.!?]*/g) || [text];
  for(const s of sentences){
    const u = new SpeechSynthesisUtterance(s.trim());
    u.lang = navigator.language || 'fr-FR';
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
  }
}

function _initSTT(){
  if(_sttInited) return;
  _sttInited = true;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const micBtn = document.getElementById('mic-btn');
  if(!SR){ if(micBtn){ micBtn.disabled=true; micBtn.title='Web Speech non supporté'; } return; }
  _recognition = new SR();
  _recognition.lang = navigator.language || 'fr-FR';
  _recognition.interimResults = false;
  _recognition.maxAlternatives = 1;
  _recognition.onresult = (e) => {
    const t = e.results[0][0].transcript;
    const inp = document.getElementById('chat-input');
    inp.value = t; autoResize(inp); sendMsg();
  };
  _recognition.onerror = (e) => {
    if(micBtn) micBtn.classList.remove('listening');
    if(e.error==='not-allowed') showToast('⛔ Accès micro refusé');
    else if(e.error!=='no-speech') showToast('Micro : ' + e.error);
  };
  _recognition.onend = () => { if(micBtn) micBtn.classList.remove('listening'); };
}

function toggleMic(){
  _initSTT();
  const micBtn = document.getElementById('mic-btn');
  if(!micBtn) return;
  if(micBtn.classList.contains('listening')){
    _recognition?.stop();
  } else {
    micBtn.classList.add('listening');
    try { _recognition?.start(); } catch { micBtn.classList.remove('listening'); }
  }
}

// Initialiser les boutons au chargement
document.addEventListener('DOMContentLoaded', () => { _updateTtsBtn(); _initSTT(); });

// ── Select modèle LLM dans le chat header ────────────────────────
async function _initChatModelSel(){
  const sel=document.getElementById('chat-model-sel');
  if(!sel)return;
  const token=_getToken();
  const h=token?{'Authorization':'Bearer '+token}:{};
  try{
    const [models,cfg]=await Promise.all([
      fetch('/api/ollama/models',{headers:h}).then(r=>r.json()).catch(()=>[]),
      fetch('/api/settings',{headers:h}).then(r=>r.json()).catch(()=>({}))
    ]);
    const current=(cfg.models?.chat||'mistral:latest');
    const list=Array.isArray(models)?models:[];
    sel.innerHTML='';
    if(!list.includes(current)){
      const o=document.createElement('option');
      o.value=current;o.textContent=current.replace(':latest','');o.selected=true;
      sel.appendChild(o);
    }
    list.forEach(m=>{
      const o=document.createElement('option');
      o.value=m;o.textContent=m.replace(':latest','');
      if(m===current)o.selected=true;
      sel.appendChild(o);
    });
    // Sync topbar
    const b=document.getElementById('v-llm-chat');
    if(b)b.textContent=current.replace(':latest','');
  }catch{}
  sel.onchange=async()=>{
    const model=sel.value;
    const tok=_getToken();
    const hd=tok?{'Authorization':'Bearer '+tok,'Content-Type':'application/json'}:{'Content-Type':'application/json'};
    await fetch('/api/settings',{method:'POST',headers:hd,body:JSON.stringify({key:'models.chat',value:model})}).catch(()=>{});
    const b=document.getElementById('v-llm-chat');
    if(b)b.textContent=model.replace(':latest','');
  };
}

// ── Clock ──────────────────────────────────────────────────────
function tick(){
  const n=new Date();
  document.getElementById('clock').textContent=
    n.getHours().toString().padStart(2,'0')+':'+n.getMinutes().toString().padStart(2,'0');
  document.getElementById('datestr').textContent=
    n.toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});
}
tick();setInterval(tick,10000);

// ── Thème ──────────────────────────────────────────────────────
function setTheme(el){
  document.documentElement.setAttribute('data-theme',el.dataset.t);
  document.querySelectorAll('.t-dot').forEach(d=>d.classList.remove('on'));
  el.classList.add('on');
  setTimeout(drawSparks,40);
}

// ── Densité ────────────────────────────────────────────────────
document.querySelectorAll('.d-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.documentElement.setAttribute('data-density',btn.dataset.d);
    document.querySelectorAll('.d-btn').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on');
  });
});

// ── Universe nav ───────────────────────────────────────────────
const UNI_LABELS={dash:'Dashboard',home:'Maison',co:'Société',plan:'Planification',tools:'Outils'};
function goUni(id,btn){
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.uni-panel').forEach(p=>p.classList.remove('on'));
  const panel=document.getElementById('uni-'+id);
  if(panel)panel.classList.add('on');
  document.getElementById('bc-uni').textContent=UNI_LABELS[id]||id;
  document.getElementById('bc-sep').style.display='none';
  document.getElementById('bc-sub').style.display='none';
  _activeUni=id;_activeSub='';
  if(panel){
    const firstStab=panel.querySelector('.stab');
    if(firstStab){
      const onclickAttr=firstStab.getAttribute('onclick');
      const match=onclickAttr&&onclickAttr.match(/goSub\(this,'([^']+)'\)/);
      if(match) goSub(firstStab, match[1]);
    } else if(id==='dash'){
      _loadSubView('sub-dash-overview','dashboard');
    }
  }
  _renderPluginCtxBar(id);
}

// ── Sub-tabs ───────────────────────────────────────────────────
function goSub(el,subId){
  const panel=el.closest('.uni-panel');
  panel.querySelectorAll('.stab').forEach(s=>s.classList.remove('on'));
  el.classList.add('on');
  panel.querySelectorAll('.subview').forEach(v=>v.classList.remove('on'));
  const sub=document.getElementById(subId);
  if(sub)sub.classList.add('on');
  const labels={
    'sub-soc':'Sociétés',
    'sub-dash-overview':"Vue d'ensemble",'sub-dash-alerts':'Alertes','sub-dash-scenes':'Scènes rapides',
    'sub-domo':'Domotique','sub-cameras':'Caméras','sub-membres':'Membres','sub-courses':'Courses',
    'sub-infra':'Infrastructure','sub-rmm':'RMM Clients','sub-tel':'Téléphonie','sub-mkt':'Marketing',
    'sub-briefing':'Briefing','sub-agenda':'Agenda',
    'sub-skills':'Compétences','sub-mem':'Mémoire','sub-settings':'Paramètres',
    'sub-senses':'Capteurs','sub-music':'Musique',
    ..._VIEW_LABELS,
  };
  const sep=document.getElementById('bc-sep');
  const sub_el=document.getElementById('bc-sub');
  if(labels[subId]){sep.style.display='';sub_el.style.display='';sub_el.textContent=labels[subId];}
  _activeSub=labels[subId]||subId;
  const _VM={
    'sub-soc':           ['societe',   {}],
    'sub-dash-overview': ['dashboard', {}],
    'sub-cameras':  ['cameras',  {}],
    'sub-mkt':      ['marketing',{}],
    'sub-mem':      ['memory',   {}],
    'sub-briefing': ['briefing', {}],
    'sub-agenda':   ['planner',  {}],
    'sub-skills':   ['skills',   {}],
    'sub-settings': ['settings', {}],
    'sub-domo':     ['page',     {page:'home',           hint:'État domotique complet'}],
    'sub-infra':    ['infra',    {}],
    'sub-rmm':      ['page',     {page:'printers',       hint:'RMM clients actifs'}],
    'sub-senses':   ['page',     {page:'senses',         hint:'État capteurs'}],
    'sub-music':    ['page',     {page:'music',          hint:'Lecteur musique'}],
  };
  const _vmEntry = _VM[subId] || _VIEW_OVERRIDES[subId];
  if(_vmEntry){const[v,o]=_vmEntry;_loadSubView(subId,v,o);}
}

// ── Chat toggle ────────────────────────────────────────────────
let chatHidden=false;
function toggleChat(){
  const app=document.getElementById('app');
  if(window.matchMedia('(max-width:768px)').matches){
    const open=document.documentElement.classList.toggle('chat-open');
    const btn=document.getElementById('chat-toggle-mob');
    if(btn)btn.textContent=open?'✕':'💬';
  }else{
    chatHidden=!chatHidden;
    app.classList.toggle('chat-hidden',chatHidden);
    app.classList.remove('chat-full');
    if(chatHidden){
      app.classList.remove('chat-expanded');
      const eb=document.getElementById('chat-expand-btn');
      if(eb){eb.textContent='⤡';eb.title='Agrandir';}
    }
    const tog=document.getElementById('chat-toggle');
    if(tog)tog.textContent=chatHidden?'▸':'◂';
  }
}

function toggleChatExpand(){
  const app=document.getElementById('app');
  const btn=document.getElementById('chat-expand-btn');
  const expanded=app.classList.toggle('chat-expanded');
  if(expanded){
    app.classList.remove('chat-hidden','chat-full');
    chatHidden=false;
    const tog=document.getElementById('chat-toggle');
    if(tog)tog.textContent='◂';
  }
  if(btn){btn.textContent=expanded?'⤢':'⤡';btn.title=expanded?'Réduire':'Agrandir';}
}

// ── Admin menu ────────────────────────────────────────────────
function toggleAdminMenu(e){
  e.stopPropagation();
  document.getElementById('admin-drop').classList.toggle('show');
}
document.addEventListener('click',()=>document.getElementById('admin-drop')?.classList.remove('show'));
async function adminRestart(){
  document.getElementById('admin-drop').classList.remove('show');
  showToast('Redémarrage en cours…');
  try{
    await fetch('/api/admin/restart',{method:'POST',headers:{'Authorization':'Bearer '+_getToken()}});
    setTimeout(()=>location.reload(),2500);
  }catch{ setTimeout(()=>location.reload(),3000); }
}
async function adminClearCache(){
  document.getElementById('admin-drop').classList.remove('show');
  if('serviceWorker' in navigator && 'caches' in window){
    const keys=await caches.keys();
    await Promise.all(keys.map(k=>caches.delete(k)));
    const reg=await navigator.serviceWorker.getRegistration();
    if(reg) await reg.unregister();
    showToast('Cache vidé — rechargement…');
    setTimeout(()=>location.reload(true),1000);
  }else{ showToast('Cache SW non disponible.'); }
}
function adminLogout(){
  document.getElementById('admin-drop').classList.remove('show');
  localStorage.removeItem('ada_token');
  document.cookie='ada_token=; path=/; SameSite=Strict; Max-Age=0';
  location.reload();
}

// ── Nav expand ─────────────────────────────────────────────────
let _navExpanded=false;
function toggleNav(){
  _navExpanded=!_navExpanded;
  document.getElementById('app').classList.toggle('nav-expanded',_navExpanded);
  const tog=document.getElementById('nav-toggle');
  // Met à jour l'icône (premier nœud texte)
  tog.childNodes[0].textContent=_navExpanded?'✕':'☰';
}

// ── View overlay ───────────────────────────────────────────────
const _viewTitles={'settings':'Paramètres','profile-editor':'Profils & Univers'};
let _viewMounted=null;
async function openView(name){
  const overlay=document.getElementById('view-overlay');
  const body=document.getElementById('view-body');
  const titleEl=document.getElementById('view-title-label');
  body.innerHTML='<p style="padding:24px;color:var(--text-dim);font-size:12px">Chargement…</p>';
  titleEl.textContent=_viewTitles[name]||name;
  overlay.classList.add('show');
  try{
    const {mount}=await import(`/static/views/${name}/index.js`);
    body.innerHTML='';
    _viewMounted=await mount(body,{token:_getToken()});
  }catch(e){
    body.innerHTML=`<p style="padding:24px;color:var(--text-dim);font-size:12px">Vue "${name}" non disponible.</p>`;
    console.error('openView',name,e);
  }
}
function closeView(){
  document.getElementById('view-overlay').classList.remove('show');
  _viewMounted=null;
}

// ── Lazy sub-view loader ──────────────────────────────────────────
async function _loadSubView(subId,viewName,opts={}){
  const el=document.getElementById(subId);
  if(!el||el.dataset.loaded)return;
  el.dataset.loaded='1';
  el.innerHTML='<p style="padding:24px;color:var(--text-dim);font-size:12px">Chargement…</p>';
  try{
    const{mount}=await import(`/static/views/${viewName}/index.js`);
    el.innerHTML='';
    await mount(el,{token:_getToken(),...opts});
  }catch(e){
    el.innerHTML=`<p style="padding:24px;color:var(--text-dim);font-size:12px">Erreur : ${e.message}</p>`;
    el.dataset.loaded='';
    console.error('_loadSubView',viewName,e);
  }
}

// ── adaNavigate — pont pour les vues qui appellent switchView ────
const _V2U={
  dashboard:'dash',
  cameras:  ['home','sub-cameras'],
  marketing:['co','sub-mkt'],
  briefing: ['plan','sub-briefing'],
  planner:  ['plan','sub-agenda'],
  memory:   ['tools','sub-mem'],
  societe:  ['co','sub-soc'],
};
// ── Contextes par univers ─────────────────────────────────────────
const _UNI_CTX={
  dash:{label:'Dashboard',domain:'general',text:null,
    qps:['État général','Alertes actives ?','Résumé du jour','Tâches en cours ?']},
  home:{label:'Maison',domain:'maison',
    text:"L'utilisateur est dans l'univers Maison. Tu es l'assistant domotique de la maison. Oriente tes réponses sur la domotique, les équipements connectés, les caméras, la météo, la musique et les automatisations.",
    qps:['État des lumières','Mode nuit','Température ?','Caméras actives ?']},
  plan:{label:'Planification',domain:'planning',
    text:"L'utilisateur est dans l'univers Planification. Aide-le sur l'agenda, les tâches, les projets et les rappels.",
    qps:['Tâches du jour','Réunions cette semaine ?','Prochaine échéance ?','Résume le planning']},
  tools:{label:'Outils',domain:'tools',
    text:"L'utilisateur est dans l'univers Outils. Aide-le sur les compétences IA, la mémoire, les paramètres et les configurations techniques.",
    qps:["Skills actives ?",'État mémoire','Paramètres actuels','Aide configuration']},
};
// ── Société chat context bridge ─────────────────────────────────
let _socCompanies=[],_socCtxId=null;
let _activeCtxText='',_activeDomain=null;
window.adaSocSetCompanies=function(companies){
  _socCompanies=companies||[];
  if(_activeUni==='co')_renderSocieteCtxBar();
};
function _renderSocieteCtxBar(){
  const bar=document.getElementById('ctx-bar');
  const qbar=document.getElementById('quick-bar');
  if(!bar)return;
  const btns=[{id:null,name:'Tout',color:'rgba(255,255,255,0.4)'},..._socCompanies];
  bar.innerHTML='<span class="ctx-lbl">CONTEXTE ACTIF</span>'+btns.map(c=>
    `<button class="ctx-tag ct-co${c.id===_socCtxId?' on':''}" data-socid="${c.id||''}" onclick="socSetCtx(this,'${c.id||''}')"><span class="ctx-dot" style="background:${c.color||'rgba(255,255,255,0.4)'}"></span>${c.name}</button>`
  ).join('');
  if(qbar){
    const qps=_socCtxId
      ?['Résume la situation','Quels impayés ?','Tickets ouverts ?','Prochain devis ?']
      :['État des sociétés','Alertes en cours ?','Total impayés ?','Tickets ouverts ?'];
    qbar.innerHTML=qps.map(p=>`<button class="qp" onclick="inject('${p}')">${p}</button>`).join('');
  }
}
function _renderUniCtxBar(id){
  const ctx=_UNI_CTX[id]||_UNI_CTX.dash;
  const bar=document.getElementById('ctx-bar');
  const qbar=document.getElementById('quick-bar');
  if(bar)bar.innerHTML='<span class="ctx-lbl">CONTEXTE ACTIF</span><div class="ctx-tag on" style="pointer-events:none">'+ctx.label+'</div>';
  if(qbar)qbar.innerHTML=ctx.qps.map(p=>'<button class="qp" onclick="inject(\''+p+'\')">'+ p+'</button>').join('');
}
function _renderDefaultCtxBar(){_renderPluginCtxBar('dash');}
async function socSetCtx(btn,cid){
  _socCtxId=cid||null;
  _activeCtxText='';
  _activeDomain=_socCtxId||'societe';
  if(_socCtxId){
    try{
      const r=await fetch(`/api/societe/companies/${_socCtxId}/context`,{headers:{'Authorization':'Bearer '+_getToken()}});
      if(r.ok){
        const d=await r.json();
        _activeCtxText=d.context||(typeof d==='string'?d:JSON.stringify(d));
      }
    }catch{}
  }
  _renderSocieteCtxBar();
}

window.adaNavigate=function(viewName){
  if(viewName==='settings'||viewName==='profile-editor'){openView(viewName);return;}
  const t=_V2U[viewName];
  if(!t){try{openView(viewName);}catch(e){}return;}
  if(Array.isArray(t)){
    const[uni,sub]=t;
    const uniBtn=document.querySelector(`[data-uni="${uni}"]`);
    if(uniBtn)goUni(uni,uniBtn);
    setTimeout(()=>{
      const stabEl=document.querySelector(`[onclick*="${sub}"]`);
      if(stabEl)goSub(stabEl,sub);
    },80);
  }else{
    const uniBtn=document.querySelector(`[data-uni="${t}"]`);
    if(uniBtn)goUni(t,uniBtn);
  }
};

// ── Domotique — appareils filtrés ────────────────────────────
let _devShowAll=false;
function _devSw(sw){
  sw.classList.toggle('on');
  const card=sw.closest('.dev-card');
  if(card)card.dataset.active=sw.classList.contains('on')?'1':'0';
  _devFilter(document.getElementById('dev-search')?.value||'');
}
function _devFilter(q){
  const q2=(q||'').toLowerCase().trim();
  let active=0,total=0;
  document.querySelectorAll('#dev-grid .dev-card').forEach(c=>{
    total++;
    const match=!q2||(c.dataset.name||'').toLowerCase().includes(q2);
    const on=c.dataset.active==='1';
    if(on)active++;
    c.hidden=!(match&&(_devShowAll||on));
  });
  const el=document.getElementById('dev-count');
  if(el)el.textContent=active+' actif'+(active>1?'s':'')+' · '+total+' total';
}
function _devToggleAll(){
  _devShowAll=!_devShowAll;
  const btn=document.getElementById('dev-show-all');
  if(btn)btn.textContent=_devShowAll?'Actifs seuls':'Tout afficher';
  _devFilter(document.getElementById('dev-search')?.value||'');
}

// ── Shopping ───────────────────────────────────────────────────
function toggleShop(el){
  const done=el.style.opacity==='.45'||el.style.opacity==='0.45';
  el.style.opacity=done?'1':'.45';
  const chk=el.querySelector('.shop-chk');
  const name=el.querySelector('.ti-n');
  if(!done){
    chk.textContent='✓';
    chk.style.cssText='width:15px;height:15px;border-radius:4px;background:var(--green);border:1px solid var(--green);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:10px;color:#000';
    name.style.textDecoration='line-through';
  }else{
    chk.textContent='';
    chk.style.cssText='width:15px;height:15px;border-radius:4px;border:1px solid var(--border-hi);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:10px';
    name.style.textDecoration='none';
  }
}

// ── Sparklines ─────────────────────────────────────────────────
function drawSpark(id,data,color){
  const c=document.getElementById(id);if(!c)return;
  const ctx=c.getContext('2d');
  const dpr=window.devicePixelRatio||1;
  const r=c.getBoundingClientRect();
  c.width=r.width*dpr;c.height=28*dpr;
  ctx.scale(dpr,dpr);
  const w=r.width,h=28;
  const mx=Math.max(...data),mn=Math.min(...data),rg=mx-mn||1;
  const pts=data.map((v,i)=>({x:(i/(data.length-1))*w,y:h-((v-mn)/rg)*(h-5)-3}));
  ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
  pts.slice(1).forEach(p=>ctx.lineTo(p.x,p.y));
  ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.stroke();
  const g=ctx.createLinearGradient(0,0,0,h);
  g.addColorStop(0,color+'40');g.addColorStop(1,color+'00');
  ctx.lineTo(pts[pts.length-1].x,h);ctx.lineTo(pts[0].x,h);
  ctx.closePath();ctx.fillStyle=g;ctx.fill();
}
function rnd(b,v,n=20){return Array.from({length:n},()=>b+(Math.random()-.5)*v);}
function drawSparks(){
  const s=getComputedStyle(document.documentElement);
  const c1=(s.getPropertyValue('--accent')||'#17c3e8').trim();
  const c2=(s.getPropertyValue('--orange')||'#f59800').trim();
  const c3=(s.getPropertyValue('--green') ||'#22d490').trim();
  drawSpark('sp1',rnd(16,8),c1);
  drawSpark('sp2',rnd(9.4,2),c2);
  drawSpark('sp3',rnd(0.3,.15),c3);
}
setTimeout(drawSparks,100);
window.addEventListener('resize',drawSparks);


// ── Plugin Context Bar ───────────────────────────────────────────
let _activePluginCtx=null,_activeCtxId=null,_pluginUniverses=null;

const _UNI_META={
  home:  {label:'Maison',     color:'#a888ff',bg:'rgba(168,136,255,.1)', border:'rgba(168,136,255,.28)'},
  uscss: {label:'MyCompany',      color:'#22d490',bg:'rgba(34,212,144,.08)',  border:'rgba(34,212,144,.22)'},
  global:{label:'Global',     color:'#8899a8',bg:'rgba(136,153,168,.08)', border:'rgba(136,153,168,.2)'},
};
const _UNI_TO_PLUGIN={home:'home',co:'opent',plan:null,tools:null,dash:null};

async function _fetchPluginUniverses(){
  if(_pluginUniverses)return _pluginUniverses;
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    const r=await fetch('/api/plugins/universes',{headers:h});
    if(r.ok)_pluginUniverses=await r.json();
  }catch{}
  return _pluginUniverses||{};
}

async function _renderPluginCtxBar(uniId){
  const bar=document.getElementById('ctx-bar');
  const qbar=document.getElementById('quick-bar');
  if(!bar)return;
  if(uniId==='co'){_renderSocieteCtxBar();return;}

  const localCtx=_UNI_CTX[uniId];
  if(localCtx){_activeCtxText=localCtx.text||'';_activeDomain=localCtx.domain||uniId;}

  const pluginUni=_UNI_TO_PLUGIN[uniId]||null;
  _activePluginCtx=pluginUni;_activeCtxId=null;

  const universes=await _fetchPluginUniverses();
  let html='<span class="ctx-lbl">CONTEXTE ACTIF</span>';

  if(pluginUni&&universes[pluginUni]){
    const meta=_UNI_META[pluginUni]||_UNI_META.global;
    html+=`<button class="ctx-uni-btn on"
      style="background:${meta.bg};color:${meta.color};border-color:${meta.border}"
      onclick="_togglePluginCtx('${pluginUni}',this)">
      <span class="ctx-uni-dot" style="background:${meta.color}"></span>${meta.label}
    </button>`;
    universes[pluginUni].forEach(p=>{
      html+=`<button class="ctx-tag ct-co" style="font-size:9px" title="${p.label}"
        onclick="inject('${p.label} — état et alertes')">${p.icon}</button>`;
    });
  }else{
    html+=`<div class="ctx-tag on" style="pointer-events:none">${localCtx?localCtx.label:'Dashboard'}</div>`;
  }
  bar.innerHTML=html;

  if(pluginUni&&qbar){
    try{
      const token=_getToken();
      const h=token?{'Authorization':'Bearer '+token}:{};
      const r=await fetch(`/api/plugins/quick-prompts/all?universe=${pluginUni}`,{headers:h});
      if(r.ok){
        const data=await r.json();
        const prompts=data.flatMap(d=>d.prompts||[]).slice(0,5);
        if(prompts.length){
          qbar.innerHTML=prompts.map(p=>`<button class="qp" onclick="inject('${p.replace(/'/g,"\\'")}')">${p}</button>`).join('');
          return;
        }
      }
    }catch{}
  }
  if(qbar&&localCtx&&localCtx.qps){
    qbar.innerHTML=localCtx.qps.map(p=>`<button class="qp" onclick="inject('${p}')">${p}</button>`).join('');
  }
}

function _togglePluginCtx(uni,btn){
  const isOn=btn.classList.contains('on');
  if(isOn){_activePluginCtx=null;btn.classList.remove('on');btn.style.opacity='.42';showToast('Contexte plugin désactivé');}
  else{_activePluginCtx=uni;btn.classList.add('on');btn.style.opacity='1';showToast('Contexte '+(_UNI_META[uni]?.label||uni)+' actif');}
}

// ── Carte de confirmation ────────────────────────────────────────
function _appendConfirmCard(msgEl,func,message,params,cmd){
  const bodyEl=msgEl.querySelector('._body');
  const card=document.createElement('div');
  card.className='confirm-card';
  card.innerHTML=`<div class="cc-lbl">⚠ CONFIRMATION REQUISE</div>
    <div class="cc-msg">${message}</div>
    ${cmd?`<code class="cc-cmd">${cmd}</code>`:''}
    <div class="cc-btns">
      <button class="cc-btn confirm" onclick="executeConfirmed(this)">✓ Confirmer</button>
      <button class="cc-btn cancel" onclick="cancelConfirm(this)">✕ Annuler</button>
    </div>`;
  const confirmBtn=card.querySelector('.cc-btn.confirm');
  confirmBtn.dataset.func=func;
  confirmBtn.dataset.params=JSON.stringify(params);
  (bodyEl||msgEl).appendChild(card);
  _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
}

async function executeConfirmed(btn){
  const card=btn.closest('.confirm-card');
  const func=btn.dataset.func;
  const params=JSON.parse(btn.dataset.params||'{}');
  card.querySelectorAll('.cc-btn').forEach(b=>b.disabled=true);
  card.querySelector('.cc-lbl').textContent='⏳ Exécution en cours…';
  try{
    const token=_getToken();
    const r=await fetch('/api/plugins/confirm',{
      method:'POST',
      headers:{'Content-Type':'application/json',...(token?{'Authorization':'Bearer '+token}:{})},
      body:JSON.stringify({func,params}),
    });
    const result=await r.json();
    if(result.success){
      card.innerHTML=`<span style="color:var(--green)">✓ ${result.message||'Action exécutée.'}</span>`;
      _history.push({role:'assistant',content:`Action ${func} confirmée : ${result.message||'succès'}`});
    }else{
      card.innerHTML=`<span style="color:var(--red)">✗ ${result.message||"Échec de l'action."}</span>`;
    }
  }catch(e){
    card.innerHTML=`<span style="color:var(--red)">✗ Erreur réseau : ${e.message}</span>`;
  }
  _chatMsgs.scrollTop=_chatMsgs.scrollHeight;
}

function cancelConfirm(btn){
  btn.closest('.confirm-card').innerHTML='<span style="color:var(--text-dim)">✕ Action annulée.</span>';
}

// ── Notifications système ──────────────────────────────────────
async function _requestNotifPermission(){
  if(!('Notification' in window)) return;
  if(Notification.permission==='default'){
    await Notification.requestPermission();
  }
}

function _sendNotif(title, body, icon){
  if(!('Notification' in window)||Notification.permission!=='granted') return;
  try{
    const n=new Notification(title,{body:body||'',icon:icon||'/favicon.ico',requireInteraction:false});
    setTimeout(()=>n.close(),8000);
  }catch(e){}
}

// ── Chat tabs : ADA / Radar ────────────────────────────────────
function switchChatTab(tab){
  document.getElementById('pane-ada').classList.toggle('on', tab==='ada');
  document.getElementById('pane-radar').classList.toggle('on', tab==='radar');
  document.getElementById('tab-ada-btn').classList.toggle('on', tab==='ada');
  document.getElementById('tab-radar-btn').classList.toggle('on', tab==='radar');
  if(tab==='radar') radarRefresh();
}

// ── Radar panel ────────────────────────────────────────────────
let _radarScope='all';    // 'conv' | 'all' — bascule sur 'conv' dès réception du request_id
let _radarCurrentReqId=null;
let _radarEvents=[];

function radarSetScope(scope, btn){
  _radarScope=scope;
  document.querySelectorAll('.radar-filter-btn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  radarRefresh();
}

function radarClear(){
  _radarEvents=[];
  _renderRadarList();
}

async function radarRefresh(){
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    let url='/api/radar/events?limit=200&offset=0';
    if(_radarScope==='conv'&&_radarCurrentReqId){
      url=`/api/radar/events/conversation/${_radarCurrentReqId}`;
    }
    const r=await fetch(url,{headers:h});
    if(!r.ok) return;
    const data=await r.json();
    _radarEvents=data.events||[];
    _renderRadarList();
  }catch(e){}
}

function _radarTs(isoStr){
  try{
    const d=new Date(isoStr);
    return d.toTimeString().slice(0,8);
  }catch{return '??:??:??';}
}

// §5.4 — Badge enrichi par type d'événement
function _radarBadge(level){
  const map={info:'badge-info',warning:'badge-warning',error:'badge-error',critical:'badge-critical'};
  return map[level]||'badge-info';
}

function _radarTypeBadge(type, meta){
  meta = meta || {};
  switch(type){
    case 'llm.hallucinated_function':
      return {cls:'badge-warning', label:'⚠ Fonction inconnue'};
    case 'llm.call.completed':
      return {cls:'badge-info', label:`⚡ LLM ${meta.duration_ms ? meta.duration_ms+'ms' : ''}`};
    case 'llm.call.started':
      return {cls:'badge-info', label:'⚡ LLM démarré'};
    case 'n8n.call.success':
      return {cls:'badge-ok', label:'✓ n8n OK'};
    case 'n8n.call.failed':
      return {cls:'badge-error', label:'✗ n8n KO'};
    case 'timer.fired':
      return {cls:'badge-info', label:`⏰ ${meta.label||'Timer'}`};
    case 'autoskills.injected':
      return {cls:'badge-dim', label:`🧠 ${meta.count||''} skills`};
    case 'rag.search.completed':
      return {cls:'badge-dim', label:'📄 RAG'};
    case 'rag.query.received':
      return {cls:'badge-dim', label:'📥 Query'};
    case 'rag.response.sent':
      return {cls:'badge-dim', label:'📤 Réponse'};
    case 'http.400': case 'http.401': case 'http.403': case 'http.404':
      return {cls:'badge-warning', label:type.toUpperCase()};
    case 'http.500': case 'http.502': case 'http.503':
      return {cls:'badge-error', label:type.toUpperCase()};
    default:
      return null; // Pas de badge spécifique → badge level générique
  }
}

function _renderRadarList(){
  const list=document.getElementById('radar-list');
  const empty=document.getElementById('radar-empty');
  if(!list) return;
  if(!_radarEvents.length){
    empty.style.display='flex';
    list.querySelectorAll('.radar-evt').forEach(el=>el.remove());
    return;
  }
  empty.style.display='none';
  list.querySelectorAll('.radar-evt').forEach(el=>el.remove());
  _radarEvents.forEach(evt=>{
    const meta=evt.metadata||{};
    const metaStr=Object.keys(meta).length?JSON.stringify(meta,null,2):'';
    const typeBadge=_radarTypeBadge(evt.type, meta);
    const levelBadge=`<span class="re-badge ${_radarBadge(evt.level)}">${(evt.level||'info').toUpperCase()}</span>`;
    const extraBadge=typeBadge
      ? `<span class="re-badge ${typeBadge.cls}">${typeBadge.label}</span>`
      : '';
    const div=document.createElement('div');
    div.className=`radar-evt lvl-${evt.level||'info'}`;
    div.innerHTML=`
      <div class="re-ts">${_radarTs(evt.timestamp)}</div>
      <div class="re-body">
        <div class="re-type">${evt.module||''}${evt.module?' · ':''}${evt.type||''}</div>
        <div class="re-msg">${evt.message||''}</div>
        ${metaStr?`<div class="re-meta">${metaStr}</div>`:''}
      </div>
      <div class="re-badges">${levelBadge}${extraBadge}</div>`;
    div.onclick=()=>div.classList.toggle('expanded');
    list.appendChild(div);
  });
}

// ── SSE Radar — écoute des événements temps réel ──────────────
let _radarSSE=null;
function _startRadarSSE(){
  if(_radarSSE) return;
  try{
    _radarSSE=new EventSource('/api/radar/events/stream');
    _radarSSE.onmessage=function(e){
      let evt;
      try{evt=JSON.parse(e.data);}catch{return;}
      // timer.fired → notification système
      if(evt.type==='timer.fired'){
        const meta=evt.metadata||{};
        const label=meta.label||'Timer';
        const delay=meta.delay_minutes||'?';
        _sendNotif(`⏰ Timer "${label}" terminé`,`Délai : ${delay} min`,'/favicon.ico');
        showToast(`⏰ Timer "${label}" terminé (${delay} min)`);
      }
      // Injecter dans le panel Radar si ouvert
      const radarOn=document.getElementById('pane-radar')?.classList.contains('on');
      if(radarOn){
        const matchesScope=_radarScope==='all'||
          (_radarScope==='conv'&&(!_radarCurrentReqId||evt.request_id===_radarCurrentReqId));
        if(matchesScope){
          _radarEvents.unshift(evt);
          if(_radarEvents.length>200) _radarEvents.pop();
          _renderRadarList();
        }
      }
    };
    _radarSSE.onerror=function(){
      _radarSSE.close();_radarSSE=null;
      setTimeout(_startRadarSSE,15000);
    };
  }catch(e){}
}

// ── Init ───────────────────────────────────────────────────────
// Initialise le ctx-bar immédiatement (avant l'auth) pour éviter l'affichage des tags statiques
try{_renderPluginCtxBar('dash');}catch(e){}
(async()=>{
  const ok=await _checkAuth();
  if(!ok){await _showAuth();}else{await _onAuthenticated();}
  // Demander la permission notifications après auth
  await _requestNotifPermission();
  // Démarrer l'écoute SSE radar
  _startRadarSSE();
})();

// ── A-004 : Indicateur de santé Radar sur les bulles ADA ──────
async function _appendRadarHealthDot(msgEl, reqId){
  // Attendre 1.5s que les events soient persistés
  await new Promise(r=>setTimeout(r,1500));
  try{
    const token=_getToken();
    const h=token?{'Authorization':'Bearer '+token}:{};
    const r=await fetch(`/api/radar/events/conversation/${reqId}`,{headers:h});
    if(!r.ok) return;
    const data=await r.json();
    const events=data.events||[];
    let level='ok';
    for(const e of events){
      if(e.level==='error'||e.level==='critical'){level='error';break;}
      if(e.level==='warning') level='warn';
    }
    const dot=document.createElement('span');
    dot.className=`radar-health-dot ${level}`;
    dot.title=`Radar · ${events.length} event(s) · Cliquer pour voir`;
    dot.onclick=()=>{
      _radarCurrentReqId=reqId;
      _radarScope='conv';
      document.querySelectorAll('.radar-filter-btn').forEach(b=>b.classList.remove('on'));
      document.getElementById('radar-scope-conv')?.classList.add('on');
      switchChatTab('radar');
      radarRefresh();
    };
    // Insérer après le label "from" dans la bulle ADA
    const fromEl=msgEl.querySelector('.from');
    if(fromEl){
      let row=fromEl.parentElement;
      // Si .from n'est pas dans une row, créer une row
      if(!row.classList.contains('from-row')){
        const newRow=document.createElement('div');
        newRow.className='from-row';
        fromEl.parentNode.insertBefore(newRow,fromEl);
        newRow.appendChild(fromEl);
        row=newRow;
      }
      row.appendChild(dot);
    }
  }catch(e){}
}

