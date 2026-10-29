# Análise automática B3

O módulo descobre ações B3 fora da sua lista e avalia quais atendem aos critérios, sem exigir análises fundamentalistas anteriores. Também permite comparar somente as ações cadastradas. A navegação agrupa Visão geral, Dados e premissas, Qualitativa e Histórico em **Análise fundamentalista**. Depois de Histórico, **Análise automática / Ranking B3** abre um módulo independente da ação selecionada, inclusive em telas pequenas.

## Usar

O menu principal possui dois grupos: **Análise fundamentalista** e **Análise automática**. Passe o mouse para revelar as subopções ou clique no título para selecionar e expandir o grupo. Um novo clique recolhe o grupo; Escape também fecha o submenu. No celular, os mesmos grupos abrem por toque. Os atalhos no topo mostram somente as opções do módulo selecionado.

1. Abra **Ranking B3**, em **Análise automática**. Não é necessário cadastrar ações antes.
2. Mantenha **Descobrir ações B3 fora da minha lista** em **Onde buscar**.
3. Ajuste os critérios e, se necessário, as premissas comuns de valuation. Desmarque um critério para desativá-lo.
4. Clique em **Executar análise**. A busca carrega o catálogo público e percorre os tickers, um por requisição. Ações cadastradas também podem aparecer, mas a busca não depende delas.
5. Os resultados parciais aparecem a cada dez coletas. Os cartões de quantidade funcionam como três abas: **Atende aos critérios**, **Fora dos critérios** e **Dados insuficientes**. Clique em um cartão para exibir somente a tabela e os detalhes daquela categoria. A categoria selecionada permanece durante as atualizações parciais; uma nova execução começa em **Atende aos critérios**. Também é possível navegar pelas abas com as setas do teclado.
6. Use **Pausar busca** e **Continuar busca pendente** quando necessário. O progresso é salvo no banco e pode ser retomado após recarregar a página, inclusive em outra instância da Vercel, com os critérios originais.
7. Clique em um ticker para estudar a oportunidade na análise fundamentalista. Só essa ação explícita adiciona a empresa à lista acompanhada. Uma análise já cadastrada é preservada.

O catálogo principal é a [listagem pública da brapi](https://brapi.dev/docs/acoes/list), filtrada para ações e units com cotação e volume informados positivos. O fallback é a [tabela de ações do Fundamentus](https://www.fundamentus.com.br/resultado.php), filtrada por cotação e liquidez informadas positivas. A origem, data e quantidade de tickers ficam registradas. São catálogos dos provedores, não uma garantia de cobertura integral e instantânea de todos os instrumentos da B3. Códigos com números no prefixo, como B3SA3, são aceitos. Não há lista fixa de tickers embutida no código.

Os indicadores são coletados no Investidor10, com rastreabilidade por campo. Coletas de até 24 horas podem ser reutilizadas; desmarque essa opção para obter dados novos. O IPCA é consultado uma vez por busca, e crescimento, yield desejado, retorno real e margem usam premissas comuns, independentes das suas análises manuais. A varredura não altera seus dados salvos.

Uma empresa sem dados gera uma falha identificada e a busca continua. Bloqueios HTTP 403/429 pausam a varredura sem repetição automática. A interface também pausa após três falhas consecutivas. A consulta pode levar vários minutos; mantenha a página aberta enquanto coleta. Cada passo faz no máximo uma coleta de empresa, para respeitar a duração das funções hospedadas. Uma busca interrompida fica identificada como parcial; somente a busca concluída é adicionada ao histórico de execuções. Uma conclusão com falhas informa explicitamente a cobertura e os tickers sem coleta.

Para usar o modo anterior, escolha **Comparar somente minhas ações cadastradas**. Nele, entradas manuais são preservadas e o limite continua sendo de 200 cadastros por execução. Na descoberta, o limite de proteção do catálogo é de 2.000 tickers; um catálogo maior é rejeitado, sem truncamento silencioso.

## Critérios e interpretação

As listagens e os detalhes das ações compartilham a mesma paginação: **25 ações por página** por padrão, com opções de **10, 25, 50 e 100**. Os controles mostram a faixa atual, o total da categoria e a página selecionada. Ao trocar de categoria ou alterar o tamanho, a exibição volta para a primeira página. Durante atualizações parciais da mesma busca, a página selecionada é preservada quando possível. Os cartões continuam mostrando a quantidade total de ações de cada categoria, independentemente da página.

Os limites iniciais são exemplos configuráveis, não recomendações:

| Critério | Limite inicial |
| --- | --- |
| P/L positivo | Até 15x |
| P/VP positivo | Até 2x |
| Dividend yield publicado | A partir de 4% |
| ROE publicado | A partir de 10% |
| Dívida líquida/EBITDA | Até 3x |
| Potencial da média com margem | A partir de 0% |

Cada critério ativo tem peso igual. A nota é a porcentagem de critérios atendidos, não uma previsão. Primeiro aparecem ações que atendem a todos os critérios, depois as demais em ordem decrescente de aderência. Empates usam o ticker. Uma ação com qualquer critério ativo sem dados fica em **Dados insuficientes**, sem nota; o sistema mostra a cobertura dos dados. P/L e P/VP negativos reprovam seus critérios. Dívida líquida negativa pode representar caixa líquido e não é reprovada por ser negativa.

ROE utiliza o valor publicado, sem substituição por ROE aproximado. O potencial usa os modelos existentes (Bazin, Graham e Gordon). Na descoberta são usadas premissas comuns; no modo de cadastros são usadas as premissas de cada empresa. Diferenças entre setores exigem avaliação. O checklist qualitativo continua manual. As datas de coleta não representam necessariamente o período contábil. Dados com mais de sete dias de coleta geram aviso. Indicadores antigos sem fonte individual precisam ser atualizados para obter rastreabilidade por campo.

O universo considera ações ON/PN (finais 3 a 8) e units (final 11). Units exigem fonte de indicadores na rota de ações, para evitar incluir FIIs e ETFs apenas pelo formato do código. Não são incluídos mercados estrangeiros, FIIs, ETFs, BDRs, opções, execução de ordens ou apuração tributária.

## Organização técnica

- `automatic.py`: motor puro de regras B3, independente de rede e interface.
- `discovery.py`: catálogo, coleta isolada, cache, premissas comuns e progresso persistente.
- `static/automatic.js`: formulário, atualização sequencial, resultado e consulta de execuções.
- `POST /api/automatic/run`: aplica critérios aos dados salvos e persiste o snapshot. Aceita `{"rules": {"max_pe": 15, "min_roe": null}}`; `null` desativa um critério. Exige o token de sessão existente. Esta rota não coleta dados externos.
- `GET /api/automatic/history`: lista as últimas 30 execuções.
- `GET /api/automatic/history/<id>`: retorna uma execução com critérios, valores, fontes e premissas preservados.
- Tabela `automatic_runs`: histórico separado, compatível com SQLite local e Turso. As tabelas existentes são preservadas.
- `POST /api/automatic/discovery/start`: inicia uma busca com `rules`, `assumptions` e `use_cache`.
- `POST /api/automatic/discovery/<id>/step`: coleta a próxima ação pendente. Pode ser retomado em requisições independentes.
- `GET /api/automatic/discovery/<id>`: resultado parcial ou completo e falhas de coleta.
- `GET /api/automatic/discovery/latest`: identifica a busca mais recente para retomada.
- `POST /api/automatic/discovery/<id>/finish`: salva uma única execução ao concluir todos os tickers, mesmo se repetido.
- `POST /api/automatic/discovery/<id>/watch`: abre/adiciona explicitamente uma oportunidade, preservando cadastros existentes.
- Tabelas `discovery_jobs`, `discovery_items` e `discovery_cache`: estado da busca separado das análises fundamentalistas.

O módulo usa a biblioteca padrão Python, sem dependências novas e sem chave de IA. A configuração da Vercel inclui o novo módulo; é necessário publicar o código atualizado para disponibilizá-lo no site. A implementação foi inspirada na proposta de filtragem explicável do trader-skill; não depende da instalação do plugin Claude nem incorpora seus scripts.

## Verificar

Se o modo de descoberta informar que o servidor ainda não possui o módulo, feche a janela antiga do Equity Lab, abra `iniciar.bat` novamente e recarregue a página. O servidor Python mantém o código carregado em memória, enquanto os arquivos da interface são lidos do disco; editar o projeto com o servidor aberto exige reiniciá-lo. Na Vercel, publique novamente o projeto completo para atualizar também as rotas Python.

```powershell
.\.runtime\python.exe -m unittest discover -s tests -v
.\.runtime\python.exe tests/ui_smoke.py 1440
.\.runtime\python.exe tests/ui_smoke.py 390
```

O smoke test de interface exige Microsoft Edge instalado e usa um banco temporário, sem alterar os seus dados. Gera capturas em `.runtime/` e cobre a navegação, execução, justificativas e consulta do histórico no navegador real.
