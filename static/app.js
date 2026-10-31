(() => {
  const root = document.documentElement;
  let theme = 'light';
  try { theme = localStorage.getItem('equitylab-theme') === 'dark' ? 'dark' : 'light'; } catch {}
  root.dataset.theme = theme;

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme-toggle');
    const update = () => {
      const dark = root.dataset.theme === 'dark';
      const label = dark ? 'Tema claro' : 'Tema escuro';
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', 'Ativar ' + label.toLowerCase());
      button.title = 'Ativar ' + label.toLowerCase();
      button.querySelector('.theme-icon').textContent = dark ? '☀' : '☾';
      button.querySelector('.theme-label').textContent = label;
    };
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('equitylab-theme', root.dataset.theme); } catch {}
      update();
    });
    update();
  });
})();

const $ = id => document.getElementById(id);
const money = v => v == null ? '—' : new Intl.NumberFormat('pt-BR', {style:'currency',currency:'BRL'}).format(v);
const number = v => v == null ? '—' : new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2}).format(v);
const pct = v => v == null ? '—' : number(v) + '%';
const date = v => v ? new Date(v).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo',dateStyle:'short',timeStyle:'short'}) : 'Ainda não salvo';
const escape = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let asset = null, token = '', activeTab = 'overview', busy = false;
const basics = [['price','Preço atual (R$)'],['dy','Dividend yield (%)'],['dps','DPS dos últimos 12 meses (R$)'],['eps','LPA (R$)'],['bvps','VPA (R$)'],['fcf_per_share','FCFE por ação (R$)']];
const assumptions = [['category','Categoria'],['growth','Crescimento nominal (%)'],['ipca','IPCA em 12 meses (%)'],['desired_yield','Yield desejado · Bazin (%)'],['real_return','Retorno real desejado (%)'],['rate_mode','Taxa de desconto · Gordon / FCFE'],['safety_margin','Margem de segurança (%)'],['target_pe','P/L alvo'],['target_pb','P/VP alvo'],['terminal_growth','Crescimento terminal · FCFE (%)'],['dcf_years','Horizonte FCFE (anos)']];
const labels = Object.fromEntries([...basics,...assumptions]);
const qualityItems = [
  ['historical_roe_above_5', 'O retorno sobre o patrimônio (ROE) supera 5% no histórico da companhia? Avalie os anos anteriores.'],
  ['revenue_or_profit_growth_above_5', 'Nos últimos cinco anos, a receita ou o lucro apresentou crescimento acima de 5%?'],
  ['dividend_payment_history', 'A trajetória da companhia inclui distribuição de dividendos aos acionistas?'],
  ['research_and_innovation', 'Há investimento expressivo em pesquisa e inovação? Se o setor estiver obsoleto, marque “Não”.'],
  ['founded_over_30_years', 'Já se passaram mais de 30 anos desde a fundação da companhia?'],
  ['national_or_world_sector_leader', 'A companhia ocupa o primeiro lugar em seu setor no Brasil ou no mundo? Considere apenas a liderança, não as demais posições.'],
  ['sector_over_100_years', 'O segmento de atuação da companhia existe há mais de um século?'],
  ['blue_chip', 'A companhia se enquadra na categoria de blue chips?'],
  ['good_management_no_corruption', 'Você avalia a gestão da companhia como boa? Caso haja histórico de corrupção, marque “Não”.'],
  ['free_of_state_control_or_single_customer', 'A companhia atua sem controle estatal e sem concentrar seus negócios em um único cliente?'],
  ['net_debt_ebitda_below_2_last_5_years', 'Ao longo dos últimos cinco anos, a relação entre dívida líquida e EBITDA ficou abaixo de 2 vezes?']
];
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error||'Não foi possível concluir a operação.');return d;}
async function task(fn){if(busy)return;busy=true;document.querySelectorAll('#search button,#refresh,.save-bar button,#manual-start').forEach(b=>b.disabled=true);try{await fn();}catch(e){message(e.message,true);}finally{busy=false;document.querySelectorAll('#search button,#refresh,.save-bar button,#manual-start').forEach(b=>b.disabled=false);}}
function tab(name){activeTab=name;updateModuleNavigation(name);const auto=name==='automatic';$('asset').hidden=auto||!asset;$('empty').hidden=auto||!!asset;$('search').hidden=auto;document.querySelector('.breadcrumb').textContent='Laboratório / '+(auto?'Análise automática':'Análise fundamentalista');document.querySelector('.page-heading h1').textContent=auto?'Um panorama das suas ações B3.':'Quanto vale uma boa empresa?';document.querySelector('.page-heading p').textContent=auto?'Ranking por critérios, com dados e justificativas para conferir.':'Transforme os fundamentos em uma análise que você pode acompanhar.';document.querySelectorAll('.tab-panel').forEach(e=>e.hidden=e.id!==name);document.querySelectorAll('[data-tab]').forEach(e=>{e.classList.toggle('active',e.dataset.tab===name);e.setAttribute('aria-pressed',String(e.dataset.tab===name));});if(auto)window.Automatic?.open();if(name==='history'&&asset)loadHistory().catch(e=>message(e.message,true));}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>tab(b.dataset.tab)));
function field(key,label){const v=asset.data[key],source=asset.sources[key];let input='';if(key==='category'){input=`<input name="${key}" value="${escape(v)}" placeholder="Dividendos, Growth, Valor…">`;}else if(key==='rate_mode'){input=`<select name="${key}"><option value="additive" ${v!=='compound'?'selected':''}>IPCA + retorno real (soma)</option><option value="compound" ${v==='compound'?'selected':''}>(1 + IPCA) × (1 + retorno real) − 1</option></select>`;}else{input=`<input type="number" step="${key==='dcf_years'?'1':'any'}" name="${key}" value="${escape(v??'')}" placeholder="Sem dados" ${key==='safety_margin'?'min="0" max="99.99"':''} ${key==='dcf_years'?'min="1" max="30"':''}>`;}
return `<label>${escape(label)}${input}<small class="field-source">${escape(source?.source||(key==='ipca'||basics.some(x=>x[0]===key)?'Pendente':'Premissa inicial · editável'))}</small></label>`;}
function setMenuOpen(group,open){group.querySelector('.nav-submenu').hidden=!open;group.querySelector('[data-nav-toggle]').setAttribute('aria-expanded',String(open));}
function closeMenus(){document.querySelectorAll('[data-nav-group]').forEach(group=>{delete group.dataset.pinned;setMenuOpen(group,false);});}
function openMenu(group,pinned=false){document.querySelectorAll('[data-nav-group]').forEach(other=>{if(other!==group){delete other.dataset.pinned;setMenuOpen(other,false);}});if(pinned)group.dataset.pinned='true';setMenuOpen(group,true);}
function updateModuleNavigation(name){
  const module=name==='automatic'?'automatic':'fundamental';
  document.querySelectorAll('[data-shortcuts]').forEach(block=>block.hidden=block.dataset.shortcuts!==module);
  document.querySelectorAll('[data-nav-group]').forEach(group=>{
    const selected=group.dataset.navGroup===module;group.classList.toggle('selected',selected);
    if(!selected){delete group.dataset.pinned;setMenuOpen(group,false);}
  });
}
document.querySelectorAll('[data-nav-group]').forEach(group=>{
  const toggle=group.querySelector('[data-nav-toggle]');
  group.addEventListener('mouseenter',()=>{if(matchMedia('(hover: hover)').matches)openMenu(group,group.dataset.pinned==='true');});
  group.addEventListener('mouseleave',()=>{if(!group.dataset.pinned&&!group.contains(document.activeElement))setMenuOpen(group,false);});
  group.addEventListener('focusin',()=>openMenu(group,group.dataset.pinned==='true'));
  group.addEventListener('focusout',()=>queueMicrotask(()=>{if(!group.dataset.pinned&&!group.contains(document.activeElement)&&!group.matches(':hover'))setMenuOpen(group,false);}));
  toggle.addEventListener('click',()=>{
    if(group.dataset.pinned){delete group.dataset.pinned;setMenuOpen(group,false);return;}
    const automatic=group.dataset.navGroup==='automatic';
    if(automatic&&activeTab!=='automatic')tab('automatic');
    if(!automatic&&activeTab==='automatic')tab('overview');
    openMenu(group,true);
  });
  group.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();toggle.focus();delete group.dataset.pinned;setMenuOpen(group,false);}});
});
document.addEventListener('click',event=>{if(event.target.closest('[data-tab]')||!event.target.closest('[data-nav-group]'))closeMenus();});
function signClass(v){return v==null?'':v>=0?'positive':'negative';}
function render(){if(!asset)return;$('empty').hidden=true;$('asset').hidden=false;const d=asset.data,a=asset.analysis,v=a.values,p=a.potential,i=a.indicators;
$('ticker').value=asset.ticker;$('asset-ticker').textContent=asset.ticker;$('ticker-logo').textContent=asset.ticker[0];$('company-name').textContent=d.company_name||'Empresa listada na B3';$('category-pill').textContent=d.category||'Sem categoria';$('updated').textContent='Salvo em '+date(asset.updated_at);$('export').href=`/api/assets/${asset.ticker}/export`;
for(const key of ['price','eps','bvps'])$(key).textContent=money(d[key]);$('dy').textContent=pct(d.dy);
$('warning-list').innerHTML=[...(asset.warnings||[]),...a.warnings].map(w=>`<div class="notice">${escape(w)}</div>`).join('');
const models=[['bazin','Décio Bazin','Foco em dividendos','DPS ÷ yield desejado'],['graham','Benjamin Graham','Lucro e patrimônio','√(22,5 × LPA × VPA)'],['gordon','Gordon','Dividendos e crescimento','DPS × (1 + g) ÷ (k − g)']];
$('valuation-cards').innerHTML=models.map(([key,title,desc,formula],idx)=>`<article class="valuation-card"><div class="model-top"><div><h3>${title}</h3><small>${desc}</small></div><span class="model-number">0${idx+1} ↗</span></div><div class="model-label">${key==='bazin'?'PREÇO TETO':'VALOR ESTIMADO'}</div><div class="model-value">${money(v[key])}</div><div class="model-bottom"><span>Potencial vs. cotação</span><b class="${signClass(p[key])}">${pct(p[key])}</b></div><div class="model-formula">${escape(a.reasons[key]||formula)}</div></article>`).join('');
const max=Math.max(d.price||0,...models.map(x=>v[x[0]]||0),1)*1.18;
$('comparison-chart').innerHTML=models.map(([key,title])=>`<div class="chart-row"><span>${title.split(' ').at(-1)}</span><div class="track"><div class="bar" style="width:${v[key]==null?0:Math.max(0,v[key]/max*100)}%"></div>${d.price?`<div class="price-marker" style="left:${d.price/max*100}%"></div>`:''}</div><b>${money(v[key])}</b></div>`).join('');
$('final-signal').textContent=a.final_signal;$('final-signal').className='signal '+signClass(p.safe_average);$('safe-price').textContent=money(v.safe_average);$('safe-potential').textContent=pct(p.safe_average);$('safe-potential').className=signClass(p.safe_average);$('conservative').textContent=money(v.conservative);$('conservative-potential').textContent=pct(p.conservative);$('conservative-signal').textContent=a.signal;$('average').textContent=money(v.average);$('margin').textContent=pct(d.safety_margin);
const inds=[['P/L',i.pe,'x'],['P/VP',i.pb,'x'],['Earnings yield',i.earnings_yield,'%'],['Payout · DPS/LPA',i.payout,'%'],['ROE aproximado',i.roe_approx,'%'],['Taxa de desconto (k)',i.discount_rate,'%'],['DY calculado · DPS/preço',i.dy_calculated,'%'],['Preço por P/L alvo',v.pe_target,'R$'],['Preço por P/VP alvo',v.pb_target,'R$'],['FCFE descontado',v.dcf,'R$'],...Object.entries(asset.extra||{}).map(([key,val])=>[({'roe':'ROE publicado','roic':'ROIC publicado','ev_ebitda':'EV/EBITDA','net_debt_ebitda':'Dívida líquida/EBITDA','net_margin':'Margem líquida'})[key]||key,val,['roe','roic','net_margin'].includes(key)?'%':'x'])];
$('indicators').innerHTML=inds.map(([label,value,unit])=>`<article class="indicator"><span>${escape(label)}</span><strong>${unit==='R$'?money(value):number(value)+(value==null?'':unit)}</strong></article>`).join('');
renderSensitivity();$('fundamentals-fields').innerHTML=basics.map(x=>field(...x)).join('');$('assumption-fields').innerHTML=assumptions.map(x=>field(...x)).join('');
$('sources').innerHTML='<table><thead><tr><th>Dado</th><th>Fonte</th><th>Coleta</th><th>Base / referência</th><th></th></tr></thead><tbody>'+Object.entries(asset.sources).map(([key,s])=>`<tr><td>${escape(labels[key]||key)}</td><td>${s.url&&/^https:\/\//.test(s.url)?`<a href="${escape(s.url)}" target="_blank" rel="noopener noreferrer">${escape(s.source)} ↗</a>`:escape(s.source)}</td><td>${date(s.fetched_at)}</td><td>${escape(s.basis||'')}${s.as_of?' · '+escape(s.as_of):''}</td><td>${s.source==='Manual'&&['price','dy','dps','eps','bvps','ipca'].includes(key)?`<button class="text-button" type="button" data-auto="${key}">Usar automático ↻</button>`:''}</td></tr>`).join('')+'</tbody></table>';
$('sources').querySelectorAll('[data-auto]').forEach(b=>b.onclick=()=>task(async()=>{message('Buscando o campo na fonte…');asset=await api(`/api/assets/${asset.ticker}/refresh`,{automatic_fields:[b.dataset.auto]});render();await watchlist();message('Campo devolvido à coleta automática.');}));
$('checklist').innerHTML=qualityItems.map(([key,title])=>`<label class="quality-item"><span>${escape(title)}</span><select name="${key}" aria-label="${escape(title)}">${[['unknown','Não avaliado'],['yes','Sim'],['no','Não']].map(([value,label])=>`<option value="${value}" ${(d.quality?.[key]||'unknown')===value?'selected':''}>${label}</option>`).join('')}</select></label>`).join('');$('notes').value=d.notes||'';qualityScore();tab(activeTab);}
function qualityScore(){const values=[...$('checklist').querySelectorAll('select')].map(s=>s.value);$('quality-score').textContent=`${values.filter(v=>v==='yes').length} respostas positivas · ${values.filter(v=>v!=='unknown').length} de ${values.length} questões avaliadas`;} $('checklist').addEventListener('change',qualityScore);
function renderSensitivity(){const d=asset.data,k=asset.analysis.indicators.discount_rate,g=d.growth;let html='<div class="table-wrap"><table><thead><tr><th>g ↓ / k →</th>';for(const delta of [-1,0,1])html+=`<th>${pct(k==null?null:k+delta)}</th>`;html+='</tr></thead><tbody>';for(const dg of [-1,0,1]){html+=`<tr><th>${pct(g==null?null:g+dg)}</th>`;for(const dk of [-1,0,1]){const val=k!=null&&g!=null&&d.dps!=null&&k+dk>g+dg?d.dps*(1+(g+dg)/100)/((k+dk-g-dg)/100):null;html+=`<td>${money(val)}</td>`;}html+='</tr>';} $('sensitivity').innerHTML=html+'</tbody></table></div>';}
async function watchlist(){const rows=await api('/api/assets');$('asset-count').textContent=rows.length;$('watchlist').innerHTML=rows.map(row=>`<button class="watch-item ${row.ticker===asset?.ticker?'active':''}" data-ticker="${escape(row.ticker)}"><b>${escape(row.ticker)}</b><small>${money(row.data.price)}</small></button>`).join('');$('watchlist').querySelectorAll('button').forEach(b=>b.onclick=()=>task(async()=>{asset=await api('/api/assets/'+b.dataset.ticker);activeTab='overview';render();await watchlist();message('Análise salva carregada.');}));}
async function loadHistory(){const requested=asset.ticker;const rows=await api(`/api/assets/${requested}/history`);if(asset.ticker!==requested)return;$('history-detail').innerHTML='';$('history-content').innerHTML=rows.length?'<table><thead><tr><th>Data</th><th>Preço</th><th>Média com margem</th><th>Potencial</th><th>Sinal</th><th></th></tr></thead><tbody>'+rows.map(row=>`<tr><td>${date(row.created_at)}</td><td>${money(row.asset.data.price)}</td><td>${money(row.asset.analysis.values.safe_average)}</td><td>${pct(row.asset.analysis.potential.safe_average)}</td><td>${escape(row.asset.analysis.final_signal)}</td><td><button class="text-button" data-id="${row.id}">Ver dados ↗</button></td></tr>`).join('')+'</tbody></table>':'<p>Salve uma análise para começar seu histórico.</p>';$('history-content').querySelectorAll('button').forEach(b=>b.onclick=()=>{const row=rows.find(r=>r.id===Number(b.dataset.id));$('history-detail').innerHTML=`<article class="panel history-preview"><h3>Versão de ${date(row.created_at)}</h3><pre>${escape(JSON.stringify(row.asset,null,2))}</pre></article>`;});}
$('search').onsubmit=e=>{e.preventDefault();task(async()=>{const ticker=$('ticker').value.trim().toUpperCase();activeTab='overview';asset=await api('/api/assets/'+ticker);render();message('Buscando cotação, fundamentos e IPCA…');try{asset=await api(`/api/assets/${ticker}/refresh`,{});render();await watchlist();message('Coleta concluída. Confira as fontes e as premissas antes de usar os resultados.');}catch(err){activeTab='inputs';render();throw err;}});};
$('manual-start').onclick=()=>task(async()=>{const ticker=$('ticker').value.trim().toUpperCase()||'WEGE3';asset=await api('/api/assets/'+ticker);activeTab='inputs';render();message('Preencha os fundamentos ou use “Atualizar dados” para buscar automaticamente.');});
$('refresh').onclick=()=>task(async()=>{message('Atualizando fontes externas…');asset=await api(`/api/assets/${asset.ticker}/refresh`,{});render();await watchlist();message('Dados atualizados. Entradas manuais foram preservadas.');});
$('data-form').onsubmit=e=>{e.preventDefault();task(async()=>{const updates={};for(const [key,raw] of new FormData(e.target)){const value=['category','rate_mode'].includes(key)?raw:raw===''?null:Number(raw);if(value!==asset.data[key]&&!(value==null&&asset.data[key]==null))updates[key]=value;}asset=await api(`/api/assets/${asset.ticker}/save`,updates);activeTab='overview';render();await watchlist();message('Análise salva no SQLite. Uma nova versão foi adicionada ao histórico.');});};
$('quality-form').onsubmit=e=>{e.preventDefault();task(async()=>{asset=await api(`/api/assets/${asset.ticker}/save`,{quality:Object.fromEntries(new FormData(e.target)),notes:$('notes').value});render();message('Avaliação qualitativa salva.');});};
task(async()=>{const session=await api('/api/session');token=session.token;$('storage-label').textContent=session.storage==='turso'?'SQLite na nuvem':'SQLite local';$('storage-description').textContent=session.storage==='turso'?'Histórico salvo na nuvem.':'Seus estudos, no seu computador.';const saved=await api('/api/assets');if(saved.length){asset=saved[0];render();}await watchlist();});
