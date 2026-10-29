(async () => {
  const waitFor = async (condition, label) => {
    for (let attempt=0;attempt<200;attempt++) {
      if(condition())return;
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    throw new Error('Tempo excedido: '+label);
  };
  const assert = (condition, label) => {if(!condition)throw new Error(label);};
  try {
    await waitFor(()=>!busy&&token&&asset,'inicialização');
    const shortcuts=module=>document.querySelector(`[data-shortcuts="${module}"]`);
    const group=module=>document.querySelector(`[data-nav-group="${module}"]`);
    const toggle=module=>document.querySelector(`[data-nav-toggle="${module}"]`);
    assert(document.querySelectorAll('[data-nav-toggle]').length===2,'Duas opções principais no menu');
    assert(!shortcuts('fundamental').hidden&&shortcuts('automatic').hidden,'Atalhos iniciais do módulo fundamentalista');
    if(matchMedia('(hover: hover)').matches){group('fundamental').dispatchEvent(new MouseEvent('mouseenter'));assert(!$('menu-fundamental').hidden,'Submenu abre ao passar o mouse');group('fundamental').dispatchEvent(new MouseEvent('mouseleave'));assert($('menu-fundamental').hidden,'Submenu recolhe após sair');}
    toggle('automatic').click();
    assert(toggle('automatic').getAttribute('aria-expanded')==='true'&&!$('menu-automatic').hidden,'Clique abre grupo automático');
    const rankOption=$('menu-automatic').querySelector('[data-tab]');rankOption.focus();
    assert(document.activeElement===rankOption&&!$('menu-automatic').hidden,'Submenu permanece aberto durante navegação por teclado');
    document.querySelector('.page-heading h1').click();
    assert($('menu-automatic').hidden&&toggle('automatic').getAttribute('aria-expanded')==='false','Clique fora recolhe o grupo');
    toggle('automatic').click();assert(!$('menu-automatic').hidden,'Grupo pode ser reaberto após clicar fora');
    rankOption.click();
    assert($('menu-automatic').hidden&&toggle('automatic').getAttribute('aria-expanded')==='false','Selecionar submenu fecha imediatamente');
    assert(activeTab==='automatic','Opção selecionada continua ativa após fechar o menu');
    toggle('automatic').click();
    assert(shortcuts('fundamental').hidden&&!shortcuts('automatic').hidden,'Atalhos exclusivos do módulo automático');
    toggle('automatic').click();assert($('menu-automatic').hidden,'Segundo clique recolhe o grupo');
    toggle('automatic').focus();
    toggle('automatic').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    assert($('menu-automatic').hidden,'Escape recolhe o submenu');
    assert(!$('automatic').hidden&&$('asset').hidden,'Módulo automático independente');
    if(location.search.includes('legacy=1')){
      await waitFor(()=>$('message').textContent.includes('iniciar.bat'),'Orientação para servidor desatualizado');
      assert($('message').textContent.includes('servidor em execução'),'Diagnóstico do servidor antigo');
      document.documentElement.dataset.smoke='passed';return;
    }
    $('automatic-scope').value='saved';$('automatic-scope').dispatchEvent(new Event('change'));
    $('automatic-refresh').checked=false;
    $('automatic-form').requestSubmit();
    await waitFor(()=>!busy&&$('automatic-results').querySelectorAll('[role="tab"]').length===3,'ranking');
    if(location.search.includes('pagination=1')){
      const assertPage=count=>{
        const tickers=[...$('automatic-list').querySelectorAll('[data-open-stock]')].map(button=>button.dataset.openStock);
        const details=[...$('automatic-results').querySelectorAll('.automatic-detail summary b')].map(element=>element.textContent);
        assert(tickers.length===count,'Quantidade de ações por página');
        assert(JSON.stringify(tickers)===JSON.stringify(details),'Tabela e detalhes usam os mesmos tickers e ordem');
        return tickers;
      };
      const changeSize=size=>{$('automatic-page-size').value=String(size);$('automatic-page-size').dispatchEvent(new Event('change'));};
      assert($('automatic-page-size').value==='25','Padrão de 25 ações');
      assert([...$('automatic-page-size').options].map(option=>option.value).join(',')==='10,25,50,100','Opções de tamanho');
      const firstPage=assertPage(25);
      $('automatic-results').querySelector('[data-page="next"]').click();
      const secondPage=assertPage(25);
      assert(!secondPage.some(ticker=>firstPage.includes(ticker)),'Página seguinte sem repetição');
      assert($('automatic-page-info').textContent==='Página 2 de 5','Indicador da página');
      $('automatic-results').querySelector('[data-page="previous"]').click();
      assert(JSON.stringify(assertPage(25))===JSON.stringify(firstPage),'Página anterior restaura os mesmos dados');
      for(const size of [10,50,100]){changeSize(size);assertPage(size);assert($('automatic-page-info').textContent.startsWith('Página 1 de'),'Tamanho retorna à primeira página');}
      $('automatic-results').querySelector('[data-page="last"]').click();assertPage(1);
      assert($('automatic-results').querySelector('[data-page="next"]').disabled,'Fim da listagem');
      $('automatic-status-failed').click();assertPage(1);
      assert($('automatic-page-size').value==='100'&&$('automatic-page-info').textContent==='Página 1 de 1','Troca de aba preserva tamanho e reinicia página');
      $('automatic-status-insufficient').click();assertPage(1);
      $('automatic-status-passed').click();changeSize(25);assertPage(25);
      $('automatic-results').querySelector('[data-page="last"]').click();assertPage(1);
      $('automatic-results').querySelector('[data-page="first"]').click();assertPage(25);
      assert(document.body.scrollWidth<=innerWidth,'Paginação cabe na tela');
      document.documentElement.dataset.smoke='passed';return;
    }
    const text=$('automatic-results').textContent;
    assert(text.includes('Atende aos critérios')&&text.includes('Dados insuficientes'),'Classificações');
    const assertCategory=(status,ticker)=>{
      assert($('automatic-status-'+status).getAttribute('aria-selected')==='true','Aba selecionada');
      assert($('automatic-list').querySelectorAll('tbody tr').length===1,'Tabela da categoria');
      assert($('automatic-list').textContent.includes(ticker),'Ação correta na tabela');
      const details=$('automatic-results').querySelectorAll('.automatic-detail');
      assert(details.length===1&&details[0].textContent.includes(ticker),'Detalhes da mesma categoria');
    };
    assert(!$('automatic-only-passed'),'Filtro antigo removido');
    assertCategory('passed','GOOD3');
    $('automatic-status-passed').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
    assertCategory('failed','LOSS4');
    $('automatic-status-insufficient').click();assertCategory('insufficient','MISS3');
    assert($('automatic-results').textContent.includes('Dado ausente'),'Justificativa do dado ausente');
    $('automatic-status-passed').click();
    const first=$('automatic-results').querySelector('[data-open-stock]');
    assert(first.dataset.openStock==='GOOD3','Ordenação do ranking');
    assert($('automatic-history').options.length===2,'Histórico da execução');
    first.click();
    await waitFor(()=>!busy&&activeTab==='overview','Abrir fundamentalista');
    assert(!$('asset').hidden&&$('automatic').hidden&&asset.ticker==='GOOD3','Navegação para ação');
    assert(!shortcuts('fundamental').hidden&&shortcuts('automatic').hidden,'Atalhos acompanham retorno à análise fundamentalista');
    toggle('fundamental').click();
    $('menu-fundamental').querySelector('[data-tab="inputs"]').click();
    assert($('menu-fundamental').hidden&&activeTab==='inputs','Selecionar opção fundamentalista também fecha o grupo');
    document.querySelector('[data-tab="automatic"]').click();
    await waitFor(()=>$('automatic-history').options.length===2,'Lista histórica');
    $('automatic-history').selectedIndex=1;
    $('automatic-load').click();
    await waitFor(()=>!busy&&$('automatic-progress').textContent.includes('Execução histórica'),'Snapshot histórico');
    $('automatic-results').querySelector('details').open=true;
    $('automatic-scope').value='discovery';$('automatic-scope').dispatchEvent(new Event('change'));
    $('automatic-form').requestSubmit();
    await waitFor(()=>$('automatic-progress').textContent.includes('1 de 3'),'Progresso da descoberta');
    $('discovery-pause').click();
    await waitFor(()=>!busy&&!$('discovery-resume').hidden,'Pausar descoberta');
    assert($('automatic-results').textContent.includes('Resultado parcial'),'Resultado parcial identificado');
    $('automatic-status-failed').click();
    assert(!$('automatic-list').querySelector('tbody tr')&&!$('automatic-results').querySelector('.automatic-detail'),'Categoria vazia sem detalhes de outras abas');
    assert($('automatic-list').textContent.includes('Nenhuma ação na categoria'),'Mensagem da categoria vazia');
    $('discovery-resume').click();
    await waitFor(()=>!busy&&$('automatic-progress').textContent.includes('Busca concluída'),'Continuar descoberta');
    assertCategory('failed','NEWL4');
    $('automatic-status-passed').click();
    assert($('automatic-results').querySelectorAll('.automatic-detail').length===1,'Filtro de oportunidades aprovadas');
    assert($('automatic-results').textContent.includes('Nova na sua lista'),'Oportunidade fora dos cadastros');
    assert($('watchlist').querySelectorAll('button').length===3,'Descoberta não cadastra todos os ativos');
    assertCategory('passed','NEWC3');
    $('automatic-status-failed').click();assertCategory('failed','NEWL4');
    $('automatic-status-insufficient').click();assertCategory('insufficient','NEWM3');
    $('automatic-status-passed').click();
    $('automatic-results').querySelector('[data-open-stock="NEWC3"]').click();
    await waitFor(()=>!busy&&asset.ticker==='NEWC3'&&activeTab==='overview','Estudar oportunidade nova');
    assert($('watchlist').querySelectorAll('button').length===4,'Adição explícita da oportunidade');
    document.querySelector('[data-tab="automatic"]').click();
    assert(document.body.scrollWidth<=innerWidth,'Conteúdo deve caber na largura da tela');
    document.documentElement.dataset.smoke='passed';
  } catch(error) {
    document.documentElement.dataset.smoke='failed';
    document.body.appendChild(document.createElement('pre')).textContent='SMOKE ERROR: '+error.message;
  }
})();
