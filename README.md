# Equity Lab

Sistema local de análise quantitativa e qualitativa de ações brasileiras. Interface em português, API HTTP em Python e persistência real em SQLite. Não precisa de npm, pip ou serviços pagos para iniciar.

## Executar no Windows

1. Abra **iniciar.bat** nesta pasta.
2. Mantenha o terminal aberto e acesse **http://127.0.0.1:8765**.
3. Digite o ticker e clique em **Analisar**. Ajuste as premissas em **Dados e premissas**.

Foi disponibilizado Python portátil 3.13.7 em `.runtime/`, baixado de python.org. O script usa esse executável; em outra máquina, use Python 3.11 ou superior e `python server.py`. Todo o código usa a biblioteca padrão. Para encerrar, pressione Ctrl+C no terminal.

O banco é criado em `data/equity.sqlite3`. Cada atualização ou salvamento preserva um snapshot dos dados, fontes, premissas, cálculos, checklist e tese. Faça backup da pasta `data` com o servidor desligado. Dados são locais, não sincronizados. O servidor escuta somente em loopback; esta entrega não foi publicada na internet. O backend Python com arquivo SQLite não é compatível diretamente com o runtime Workers do Sites.

## Funcionalidades

- Consulta por ticker, lista de ações analisadas e atualização sob demanda.
- Bazin, Graham, Gordon com taxa padrão IPCA + 9 pontos percentuais.
- Opção de composição `(1 + IPCA) × (1 + retorno real) − 1`.
- Todos os 21 campos fornecidos da planilha: categoria, preço, DY, DPS, LPA, VPA, crescimento, IPCA, yield desejado, três preços, menor preço, potencial, sinal, média, margem, média com margem, potencial com margem e sinal definitivo.
- P/L, P/VP, earnings yield, payout, ROE aproximado e DY calculado.
- Preços por múltiplos alvo e fluxo de caixa livre ao acionista (FCFE) descontado em dois estágios. FCFE é entrada manual: não há preenchimento automático confiável desse campo nesta versão.
- Gráfico comparativo e tabela de sensibilidade de Gordon.
- Checklist qualitativo com 11 perguntas: ROE histórico, crescimento de receitas ou lucro, dividendos, pesquisa e inovação, tempo de mercado, liderança no setor, idade do setor, blue chip, gestão e corrupção, controle estatal ou concentração em cliente único e dívida líquida/EBITDA. Respostas: não avaliado, sim ou não; tese e riscos em texto. Setor obsoleto e histórico de corrupção devem receber “Não” nas respectivas perguntas.
- Histórico de até 100 versões por ação na interface; banco conserva todas.
- Exportação CSV com as colunas da planilha, separador ponto e vírgula e números em português.
- Rastreabilidade por campo, inclusive dados manuais.

## Coleta e limites

**Investidor10:** leitura das páginas públicas de ações, sem contornar bloqueios. Coleta cotação, DY, LPA, VPA e indicadores publicados no HTML. Mudanças de layout, indisponibilidade ou restrições do site podem interromper a coleta. O DPS automático é **estimado por preço × DY / 100**, não uma soma auditada de eventos: o arredondamento e a metodologia da fonte podem produzir diferenças. Para dividendos recorrentes normalizados, informe seu DPS e registre a justificativa.

**IPCA:** IBGE SIDRA, tabela 1737, variável 2265, acumulado em 12 meses. Banco Central SGS 13522 é fallback. A referência mensal aparece junto da origem. A série do IBGE foi consultada com sucesso no teste real; o BCB apresentou timeout no ambiente.

**brapi:** cotação e LPA como fonte alternativa. Integração com o endpoint v1 ainda suportado. Para tickers que exigem autenticação, configure `BRAPI_TOKEN` no ambiente antes de iniciar. Não grave tokens no código. Sem token, essa tentativa fica restrita aos tickers de demonstração documentados pelo provedor. A chamada externa nunca envia a chave à interface.

```powershell
$env:BRAPI_TOKEN = 'seu-token'
.\iniciar.ps1
```

Dados coletados possuem datas e períodos próprios. A data de coleta não representa necessariamente a data de fechamento da bolsa ou a data das demonstrações. Valores ausentes não viram zero. Entradas manuais são preservadas nas atualizações automáticas; para um fundamento ou IPCA voltar à coleta automática, use **Usar automático** na tabela de rastreabilidade. Se a fonte não retornar o campo, sua entrada é preservada.

Crescimento, yield desejado, margem e múltiplos alvo são premissas do analista. Não podem ser inferidos automaticamente como fatos. A avaliação qualitativa também permanece manual. Os valores iniciais são sugestões editáveis, não recomendações.

## Fórmulas e comparação com a planilha

Taxas são digitadas em pontos percentuais, por exemplo `8` para 8%. Valores monetários são por ação em reais.

| Modelo / coluna | Fórmula |
|---|---|
| Bazin | DPS / (yield desejado / 100) |
| Graham | √(22,5 × LPA × VPA), apenas com LPA e VPA positivos |
| Gordon | DPS × (1 + g) / (k − g), taxas fracionárias e k > g |
| Menor teto | mínimo de Bazin, Graham e Gordon |
| Potencial | (preço estimado / cotação − 1) × 100 |
| Média | média aritmética dos três modelos |
| Média com margem | média × (1 − margem / 100) |
| Sinais | abaixo do teto / no teto / cara, pela comparação com a cotação |
| FCFE | soma dos fluxos projetados descontados + perpetuidade descontada |

O menor teto e a média exigem os três modelos válidos. Na ausência de algum, os sinais ficam **SEM DADOS**. O sinal “ABAIXO DO TETO” não é recomendação de compra. Os cálculos usam precisão completa; a interface arredonda apenas para exibir.

Na linha fornecida de WEGE3, LPA de 1,49 e VPA de 4,49 produzem **Graham de R$ 12,27**, e não R$ 10,02. Com DPS de 1,85, crescimento de 5% e IPCA de 4,9%, Gordon resulta em **R$ 21,83**. Essas divergências propagam para média, mínimo e sinais. O sistema reproduz as fórmulas declaradas, sem forçar os números inconsistentes da linha. A planilha privada não pôde ser aberta; o mapeamento usa os cabeçalhos enviados na conversa.

## API local

| Método | Rota | Uso |
|---|---|---|
| GET | `/api/health` | Estado do servidor |
| GET | `/api/assets` | Ações salvas |
| GET | `/api/assets/WEGE3` | Dados e cálculos |
| GET | `/api/assets/WEGE3/history` | Histórico |
| GET | `/api/assets/WEGE3/export` | CSV |
| POST | `/api/assets/WEGE3/refresh` | Coletar e salvar |
| POST | `/api/assets/WEGE3/save` | Salvar campos alterados |
| POST | `/api/assets/WEGE3/simulate` | Calcular sem gravar |

POST requer `X-Session-Token`, obtido em `GET /api/session`. O token muda a cada execução. Esse controle e a restrição de host protegem o uso local; não substituem autenticação de usuários numa instalação pública. `EQUITY_DB` permite outro caminho de banco e `PORT` outra porta.

## Verificação

```powershell
.\.runtime\python.exe tests/test_models.py
.\.runtime\python.exe tests/test_http.py
# Com servidor ativo:
.\.runtime\python.exe tests/smoke_http.py
# Consulta real e gravação de WEGE3:
.\.runtime\python.exe tests/smoke_http.py --live
```

Testes cobrem fórmulas, limites, dados ausentes, taxa composta, FCFE, persistência e histórico. O teste de parser real usa o HTML local opcional `investidor10-sample.html`; sem ele, esse caso é ignorado. A API e a coleta real foram verificadas. Não houve verificação visual automatizada em navegador neste ambiente.

Fontes: [Investidor10](https://investidor10.com.br/acoes/wege3/), [API SIDRA do IBGE](https://apisidra.ibge.gov.br/), [SGS 13522](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=13522), [documentação brapi](https://brapi.dev/docs/acoes).
