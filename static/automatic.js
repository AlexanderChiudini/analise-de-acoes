/* Módulo de análise automática. Compartilha apenas API, sessão e formatação. */
window.Automatic = (() => {
  const definitions = [
    ['max_pe','P/L positivo até (x)',15], ['max_pb','P/VP positivo até (x)',2],
    ['min_dy','Dividend yield mínimo (%)',4], ['min_roe','ROE publicado mínimo (%)',10],
    ['max_debt','Dívida líquida/EBITDA máxima (x)',3],
    ['min_potential','Potencial mínimo com margem (%)',0]
  ];
  const statuses = {passed:'Atende aos critérios',failed:'Fora dos critérios',insufficient:'Dados insuficientes'};
  let running = false, pauseRequested = false, discoveryId = null, lastResult = null, selectedStatus = 'passed';
  let pageSize = 25, currentPage = 1;
  async function discoveryApi(path, body){
    try{return await api(path,body);}catch(error){
      if(error.message==='Rota não encontrada.'){
        const local=['127.0.0.1','localhost'].includes(location.hostname);
        throw new Error(local?'O servidor em execução ainda não tem o módulo de descoberta B3. Feche a janela antiga do Equity Lab, abra iniciar.bat novamente e recarregue esta página.':'A versão publicada do servidor ainda não tem o módulo de descoberta B3. Publique novamente o projeto completo e recarregue esta página.');
      }
      throw error;
    }
  }
  const premiseDefinitions=[['growth','Crescimento nominal (%)',5],['desired_yield','Yield desejado (%)',8],['real_return','Retorno real desejado (%)',9],['safety_margin','Margem de segurança (%)',15]];
  $('discovery-assumptions').innerHTML=premiseDefinitions.map(([key,label,value])=>`<label>${label}<input id="discovery-${key}" type="number" step="any" value="${value}" required></label>`).join('');
  function scopeChanged(){const discover=$('automatic-scope').value==='discovery';$('automatic-discovery-options').hidden=!discover;$('automatic-saved-options').hidden=discover;$('discovery-assumptions').querySelectorAll('input').forEach(input=>input.disabled=!discover);}
  $('automatic-scope').onchange=scopeChanged;
  scopeChanged();
  $('automatic-rules').innerHTML = definitions.map(([key,label,value]) => `<div class="automatic-rule"><label><input type="checkbox" data-rule="${key}" checked> ${label}</label><input id="rule-${key}" aria-label="${label}" type="number" step="any" min="-100000" max="100000" value="${value}" required></div>`).join('');
  $('automatic-rules').querySelectorAll('[data-rule]').forEach(input => input.onchange = () => { $('rule-'+input.dataset.rule).disabled = !input.checked; });

  async function history() {
    const selected = $('automatic-history').value;
    const rows = await api('/api/automatic/history');
    $('automatic-history').innerHTML = '<option value="">Selecione uma execução</option>' + rows.map(row => `<option value="${row.id}">${escape(date(row.created_at))} · #${row.id}</option>`).join('');
    if (rows.some(row => String(row.id) === selected)) $('automatic-history').value = selected;
  }

  function render(result) {
    const resultKey=value=>value.discovery?.id||value.created_at;
    if(lastResult&&resultKey(lastResult)!==resultKey(result)){selectedStatus='passed';currentPage=1;}
    lastResult=result;
    const categoryRows=result.rows.filter(row=>row.status===selectedStatus);
    const totalPages=Math.max(1,Math.ceil(categoryRows.length/pageSize));
    currentPage=Math.max(1,Math.min(currentPage,totalPages));
    const offset=(currentPage-1)*pageSize;
    const shown=categoryRows.slice(offset,offset+pageSize);
    const counts = result.counts;
    const rules = definitions.filter(([key]) => result.rules[key] != null).map(([key,label]) => `${label}: ${number(result.rules[key])}`).join(' · ');
    $('automatic-results').innerHTML = `<div class="section-title"><div><h3>Resultado de ${escape(date(result.created_at))}</h3><p>${escape(rules)}</p></div></div>
      ${result.discovery?`<div class="notice"><b>${result.discovery.remaining?'Resultado parcial':'Varredura concluída'}</b> · ${result.discovery.processed} de ${result.discovery.total} ações processadas · ${result.discovery.failed} falhas de coleta.<br>Catálogo: ${escape(result.discovery.catalog.source)} · ${escape(date(result.discovery.catalog.fetched_at))}. ${result.discovery.warnings.map(escape).join(' ')}<br>Premissas comuns: ${premiseDefinitions.map(([key,label])=>`${label}: ${number(result.discovery.assumptions[key])}`).join(' · ')}</div>`:''}
      <div class="metrics automatic-summary" role="tablist" aria-label="Resultado das ações">${['passed','failed','insufficient'].map(status=>`<button type="button" class="automatic-status" id="automatic-status-${status}" role="tab" data-status="${status}" aria-selected="${status===selectedStatus}" aria-controls="automatic-list" tabindex="${status===selectedStatus?0:-1}"><span>${statuses[status]}</span><strong>${counts[status]}</strong></button>`).join('')}</div>
      ${result.excluded.length ? `<div class="notice">Fora do universo de ações B3 verificado: ${escape(result.excluded.join(', '))}. Para units (final 11), atualize os dados pela fonte de ações antes de analisar.</div>` : ''}
      <div id="automatic-list" class="panel table-wrap" role="tabpanel" aria-labelledby="automatic-status-${selectedStatus}" tabindex="0"><h3>${statuses[selectedStatus]} · ${shown.length} ações</h3><table><thead><tr><th>Ação</th><th>Resultado</th><th>Aderência</th><th>Cotação</th><th>Preço com margem</th><th>Potencial</th><th>Dados coletados / salvos em</th></tr></thead><tbody>${shown.map(row => `<tr><td><button type="button" class="text-button" data-open-stock="${escape(row.ticker)}">${escape(row.ticker)} ↗</button>${row.is_new?'<small class="pill">Nova na sua lista</small>':''}</td><td>${statuses[row.status]}</td><td>${row.score == null?'—':number(row.score)+' / 100'}</td><td>${money(row.price)}</td><td>${money(row.safe_price)}</td><td>${pct(row.metrics.potential)}</td><td>${escape(date(row.updated_at))}</td></tr>`).join('')}</tbody></table>${!shown.length?`<p>Nenhuma ação na categoria “${statuses[selectedStatus]}” nesta execução.</p>`:''}</div>
      <div class="automatic-pagination"><label for="automatic-page-size">Ações por página <select id="automatic-page-size">${[10,25,50,100].map(size=>`<option value="${size}" ${size===pageSize?'selected':''}>${size}</option>`).join('')}</select></label><p id="automatic-page-range" aria-live="polite">${categoryRows.length?`Exibindo ${offset+1}–${offset+shown.length} de ${categoryRows.length} ações`:'Nenhuma ação nesta categoria'}</p><div class="automatic-page-buttons" role="group" aria-label="Paginação das ações"><button type="button" class="secondary" data-page="first" ${currentPage===1?'disabled':''}>Primeira</button><button type="button" class="secondary" data-page="previous" ${currentPage===1?'disabled':''}>Anterior</button><span id="automatic-page-info" tabindex="-1">Página ${currentPage} de ${totalPages}</span><button type="button" class="secondary" data-page="next" ${currentPage===totalPages?'disabled':''}>Próxima</button><button type="button" class="secondary" data-page="last" ${currentPage===totalPages?'disabled':''}>Última</button></div></div>
      ${result.discovery?.failures.length?`<details class="panel"><summary>Falhas de coleta (${result.discovery.failed})</summary><ul>${result.discovery.failures.map(item=>`<li>${escape(item.ticker)}: ${escape(item.error)}</li>`).join('')}</ul></details>`:''}
      ${shown.map(row => `<details class="panel automatic-detail"><summary><b>${escape(row.ticker)}</b> · ${statuses[row.status]} · Cobertura ${pct(row.coverage)}</summary><p>${escape(row.name)}</p><div class="table-wrap"><table><thead><tr><th>Critério</th><th>Valor</th><th>Limite</th><th>Leitura</th></tr></thead><tbody>${row.checks.map(check=>`<tr><td>${escape(check.label)}</td><td>${number(check.value)}${check.value==null?'':check.unit}</td><td>${number(check.limit)}${check.unit}</td><td>${{pass:'Atende',fail:'Não atende',missing:'Dado ausente'}[check.status]}</td></tr>`).join('')}</tbody></table></div>
      ${row.warnings.map(w=>`<p class="notice">${escape(w)}</p>`).join('')}
      <h3>Fontes e datas da execução</h3><ul>${Object.entries(row.sources).map(([key,source])=>`<li>${escape(labels[key]||key)}: ${escape(source.source)} · ${escape(date(source.fetched_at))}${source.as_of?' · Referência: '+escape(source.as_of):''}${source.url&&/^https:\/\//.test(source.url)?` · <a href="${escape(source.url)}" target="_blank" rel="noopener noreferrer">Consultar fonte ↗</a>`:''}</li>`).join('')}</ul><p>ROE e dívida/EBITDA: últimos indicadores importados. ${Object.keys(row.extra).length?'Consulte o período contábil na fonte de fundamentos.':'Nenhum indicador adicional importado.'}</p></details>`).join('')}`;
    $('automatic-page-size').onchange=event=>{
      const size=Number(event.target.value);if(![10,25,50,100].includes(size))return;
      pageSize=size;currentPage=1;render(lastResult);$('automatic-page-size').focus({preventScroll:true});
    };
    $('automatic-results').querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>{
      const action=button.dataset.page;
      currentPage={first:1,previous:currentPage-1,next:currentPage+1,last:totalPages}[action];
      render(lastResult);
      const target=$('automatic-results').querySelector(`[data-page="${action}"]`);
      (target.disabled?$('automatic-page-info'):target).focus({preventScroll:true});
    });
    const selectStatus=status=>{selectedStatus=status;currentPage=1;render(lastResult);$('automatic-status-'+status).focus({preventScroll:true});};
    $('automatic-results').querySelectorAll('[data-status]').forEach(button=>{
      button.onclick=()=>selectStatus(button.dataset.status);
      button.onkeydown=event=>{
        const keys=['passed','failed','insufficient'],index=keys.indexOf(selectedStatus);
        const next={ArrowRight:keys[(index+1)%keys.length],ArrowLeft:keys[(index+keys.length-1)%keys.length],Home:keys[0],End:keys[keys.length-1]}[event.key];
        if(next){event.preventDefault();selectStatus(next);}
      };
    });
    $('automatic-results').querySelectorAll('[data-open-stock]').forEach(button => button.onclick = () => task(async () => {
      asset = result.discovery ? await discoveryApi(`/api/automatic/discovery/${result.discovery.id}/watch`,{ticker:button.dataset.openStock}) : await api('/api/assets/'+button.dataset.openStock); activeTab='overview'; renderAsset();
      await watchlist(); message('Dados atuais carregados na análise fundamentalista.');
    }));
  }
  // Evita colisão com o renderizador local deste módulo.
  const renderAsset = () => window.render();

  $('automatic-form').onsubmit = event => {
    event.preventDefault();
    if (running || busy) return;
    const rules = Object.fromEntries(definitions.map(([key]) => [key,document.querySelector(`[data-rule="${key}"]`).checked?Number($('rule-'+key).value):null]));
    if (!Object.values(rules).some(value => value !== null)) {message('Ative pelo menos um critério.',true);return;}
    if($('automatic-scope').value==='discovery'){runDiscovery(rules);return;}
    task(async () => {
      running=true;
      const controls=[...document.querySelectorAll('.automatic-controls input,.automatic-controls button,.automatic-controls select')];
      const disabled=controls.map(control=>control.disabled);controls.forEach(control=>control.disabled=true);
      $('automatic-results').innerHTML='';
      try {
        const allSaved=await api('/api/assets');
        if(!allSaved.length)throw new Error('Cadastre e salve pelo menos uma ação B3 na análise fundamentalista.');
        if(allSaved.length>200)throw new Error('O limite desta versão é de 200 ações por análise.');
        const saved=allSaved.filter(row=>/^[A-Z][A-Z0-9]{3}[3-8]$/.test(row.ticker)||(/^[A-Z][A-Z0-9]{3}11$/.test(row.ticker)&&Object.values(row.sources||{}).some(source=>source.source==='Investidor10'&&source.url===`https://investidor10.com.br/acoes/${row.ticker.toLowerCase()}/`)));
        if($('automatic-refresh').checked){
          for(let i=0;i<saved.length;i++){
            const ticker=saved[i].ticker;
            $('automatic-progress').textContent=`Atualizando ${ticker} · ${i+1} de ${saved.length}. Mantenha a página aberta.`;
            const updated=await api(`/api/assets/${ticker}/refresh`,{});
            if(asset?.ticker===ticker)asset=updated;
            if(updated.warnings?.length)throw new Error(`${ticker}: atualização parcial. ${updated.warnings.join(' ')} Confira as fontes ou execute com os dados salvos, desmarcando a atualização.`);
          }
        }
        $('automatic-progress').textContent='Aplicando critérios e salvando a execução…';
        const result=await api('/api/automatic/run',{rules});render(result);
        $('automatic-progress').textContent='Análise concluída e salva. Confira as datas das fontes antes de comparar.';
        message('Ranking B3 concluído.');await history();await watchlist();
      } finally {
        running=false;controls.forEach((control,i)=>control.disabled=disabled[i]);
        if($('automatic-progress').textContent.includes('Atualizando')||$('automatic-progress').textContent.includes('Aplicando'))$('automatic-progress').textContent='Execução interrompida. Nenhum novo ranking foi apresentado; confira a mensagem acima.';
      }
    });
  };
  $('automatic-load').onclick=()=>task(async()=>{
    const id=$('automatic-history').value;if(!id){message('Selecione uma execução salva.',true);return;}
    render(await api('/api/automatic/history/'+id));$('automatic-progress').textContent='Execução histórica. Os dados abaixo são os preservados naquela data.';
    message('Execução histórica carregada. Os critérios do formulário continuam disponíveis para uma nova análise.');
  });
  function runDiscovery(rules=null){
    if(running||busy)return;
    task(async()=>{
      running=true;pauseRequested=false;
      const controls=[...document.querySelectorAll('.automatic-controls input,.automatic-controls button,.automatic-controls select')];
      const disabled=controls.map(control=>control.disabled);
      const assumptions=Object.fromEntries(premiseDefinitions.map(([key])=>[key,Number($('discovery-'+key).value)]));
      const useCache=$('discovery-cache').checked;
      controls.forEach(control=>control.disabled=true);
      $('discovery-pause').hidden=false;$('discovery-pause').disabled=false;$('discovery-resume').hidden=true;
      try{
        if(rules){
          discoveryId=null;
          $('automatic-results').innerHTML='';$('automatic-progress').textContent='Obtendo o catálogo público de ações B3 e o IPCA…';
          const started=await discoveryApi('/api/automatic/discovery/start',{rules,assumptions,use_cache:useCache});discoveryId=started.id;
        }
        if(!discoveryId)throw new Error('Nenhuma busca pendente para continuar.');
        let progress=null, steps=0, streak=0, previousFailures=0;
        while(!pauseRequested){
          progress=await discoveryApi(`/api/automatic/discovery/${discoveryId}/step`,{});steps++;
          streak=progress.failed>previousFailures?streak+1:0;previousFailures=progress.failed;
          $('automatic-progress').textContent=`${progress.processed} de ${progress.total} ações processadas · ${progress.failed} falhas · ${progress.ticker||''}${progress.cached?' (cache de até 24h)':''}.`;
          if(!progress.remaining)break;
          if(steps%10===0)render(await discoveryApi('/api/automatic/discovery/'+discoveryId));
          if(streak>=3){pauseRequested=true;message('Busca pausada após falhas consecutivas de coleta. Confira as falhas e tente continuar mais tarde.',true);}
          if(!pauseRequested)await new Promise(resolve=>setTimeout(resolve,400));
        }
        const complete=progress&&!progress.remaining;
        render(await discoveryApi(`/api/automatic/discovery/${discoveryId}${complete?'/finish':''}`,complete?{}:undefined));
        $('automatic-progress').textContent=complete?`Busca concluída: ${progress.processed} ações processadas, ${progress.failed} falhas de coleta. Execução salva no histórico.`:'Busca pausada. O resultado é parcial; continue para avaliar as ações restantes com os critérios originais.';
        $('discovery-resume').hidden=!!complete;
        if(complete){message('Descoberta B3 concluída. As oportunidades ainda não acompanhadas estão identificadas.');await history();}
      }catch(error){
        $('automatic-progress').textContent='Busca interrompida. O progresso já coletado foi preservado; você pode continuar com os critérios originais.';
        if(discoveryId){$('discovery-resume').hidden=false;try{render(await discoveryApi('/api/automatic/discovery/'+discoveryId));}catch{}}
        throw error;
      }finally{
        running=false;controls.forEach((control,i)=>control.disabled=disabled[i]);$('discovery-pause').hidden=true;
      }
    });
  }
  $('discovery-pause').onclick=()=>{pauseRequested=true;$('discovery-pause').disabled=true;$('automatic-progress').textContent+=' Pausando após a coleta atual…';};
  $('discovery-resume').onclick=()=>{if(busy)return;$('automatic-scope').value='discovery';scopeChanged();runDiscovery();};
  return {open:async()=>{try{await history();if(!running){const latest=await discoveryApi('/api/automatic/discovery/latest');if(latest&&latest.status!=='completed'){discoveryId=latest.id;$('discovery-resume').hidden=false;}else{$('discovery-resume').hidden=true;}}}catch(error){message(error.message,true);}}};
})();
