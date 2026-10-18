# Equity Lab

Sistema de análise quantitativa e qualitativa de ações brasileiras. Interface em português, API HTTP em Python e persistência em SQLite local ou SQLite/libSQL remoto via Turso. Não precisa de npm, pip ou serviços pagos para iniciar localmente.

## Disponível em:

https://analise-de-acoes-weld.vercel.app/

## Executar no Windows

1. Abra **iniciar.bat** nesta pasta.
2. Mantenha o terminal aberto e acesse **http://127.0.0.1:8765**.
3. Digite o ticker e clique em **Analisar**. Ajuste as premissas em **Dados e premissas**.

Foi disponibilizado Python portátil 3.13.7 em `.runtime/`, baixado de python.org. O script usa esse executável; em outra máquina, use Python 3.11 ou superior e `python server.py`. Todo o código usa a biblioteca padrão. Para encerrar, pressione Ctrl+C no terminal.

No modo local, o banco é criado em `data/equity.sqlite3`. Cada atualização ou salvamento preserva um snapshot dos dados, fontes, premissas, cálculos, checklist e tese. Faça backup da pasta `data` com o servidor desligado. O servidor local escuta somente em loopback. Com Turso configurado, o banco passa a ser remoto, inclusive na execução local; o arquivo existente não é migrado automaticamente.

## Publicar na Vercel

O projeto inclui `api/index.py` e `vercel.json` para encaminhar as páginas e a API à mesma função Python. `.vercelignore` exclui o runtime Windows, banco local e fixtures do pacote publicado.

O rewrite transporta o caminho público no parâmetro interno `__route`. Isso evita **Rota não encontrada** quando a Vercel entrega `/api/index` ao handler em vez da URL original. O mesmo resolvedor é usado para páginas, CSS, JavaScript e operações GET/POST da API. Publique `vercel.json` e `server.py` juntos, com a raiz deste projeto como **Root Directory** na Vercel; depois faça um novo deploy.

O erro **Host inválido** ocorria porque o servidor aceitava apenas `localhost` e `127.0.0.1`. Agora aceita também o domínio informado na conversa, os domínios exatos fornecidos pela Vercel em `VERCEL_URL`, `VERCEL_PROJECT_PRODUCTION_URL` e `VERCEL_BRANCH_URL`, e domínios adicionais em `ALLOWED_HOSTS`. Não é aceita qualquer URL `*.vercel.app` indiscriminadamente.

**A Vercel não oferece persistência de arquivos SQLite locais.** Usar `/tmp` faria as análises desaparecerem ou divergirem entre instâncias. Por isso, esta versão usa Turso (SQLite/libSQL via HTTPS) na Vercel e mantém arquivo SQLite no computador. [Limitação documentada pela Vercel](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel).

1. Crie um banco no [Turso](https://docs.turso.tech/quickstart) e obtenha a URL e um token do banco com permissão de leitura e escrita.
2. Em **Vercel → projeto → Settings → Environment Variables**, cadastre:

   | Variável | Valor |
   |---|---|
   | `TURSO_DATABASE_URL` | URL do banco, por exemplo `libsql://seu-banco-sua-organizacao.turso.io` |
   | `TURSO_AUTH_TOKEN` | Token do banco Turso |
   | `SESSION_SECRET` | Segredo aleatório com pelo menos 32 caracteres, igual entre as instâncias |
   | `ALLOWED_HOSTS` | Opcional: domínio próprio ou hosts adicionais separados por vírgula |
   | `BRAPI_TOKEN` | Opcional: chave do provedor de cotações |

3. Aplique as variáveis aos ambientes que usa, como **Production** e **Preview**. Publique os arquivos atualizados e faça um **novo deploy**. Ao encontrar uma tabela ausente, o aplicativo cria o schema automaticamente e repete a operação. Consultas normais não executam `CREATE`.
4. Confira `/api/health`: após a configuração correta, deve retornar `status: ok`, `database: sqlite` e `storage: turso`.

Para gerar `SESSION_SECRET` no seu computador:

```powershell
.\.runtime\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Não coloque segredos no Git nem no JavaScript da interface. `.env.example` mostra apenas os nomes das variáveis; não é carregado automaticamente. O banco remoto foi testado com simulação do protocolo HTTP e SQLite real, mas não com credenciais reais de Turso neste ambiente. O deploy da sua conta Vercel não foi alterado por este trabalho.

O aplicativo ainda não possui contas de usuário: visitantes com acesso ao site compartilham o mesmo banco e podem ler e editar as análises. Use o controle de acesso da hospedagem se o uso for privado. O token de sessão protege requisições; não é um login.

### Diagnosticar erros no banco remoto

Se uma rota de ação falhar, consulte `/api/health`. Falhas de Turso agora retornam HTTP 502 com `code`, mensagem orientativa e, para erros SQL, `stage` (índice da etapa e operação, por exemplo `0:CREATE`). A resposta não contém tokens, consultas SQL nem dados retornados pelo provedor. Os logs registram o mesmo código e etapa.

- `SQLITE_AUTH` ou `SQLITE_READONLY`: token sem as permissões necessárias. O app cria tabelas e índice automaticamente e precisa de leitura e escrita.
- `BLOCKED`: comando bloqueado por política do servidor Turso. Confira no painel os limites de uso e eventuais bloqueios de leitura/escrita da organização ou do banco. Não é sinônimo de banco ocupado. Se o banco já tem as tabelas, esta versão não envia `CREATE` nas consultas. Se ainda faltam tabelas, é necessário resolver o bloqueio de escrita para inicializá-las.
- `SQLITE_BUSY` ou `SQLITE_LOCKED`: concorrência/ocupação do banco; pode ser temporária.
- `TURSO_HTTP_401` ou `TURSO_HTTP_403`: autenticação ou acesso negado. Confira o token do **banco**, não um token administrativo de organização.
- `TURSO_HTTP_404`: confira a URL do banco, sem sufixos como `/v2/pipeline`.
- `TURSO_RESPONSE_INVALID`: resposta não JSON ou incompatível com o protocolo esperado.
- `SQLITE_ERROR` e outros códigos SQL: consulte a etapa; não significam necessariamente erro de autenticação.

A antiga mensagem “Falha na operação SQLite remota; a transação foi revertida” descartava o erro real do provedor e era imprecisa para leituras. Para erros internos inesperados, a API agora retorna `error_id`; procure o mesmo identificador nos logs da Vercel e consulte o traceback associado. Não envie credenciais ao compartilhar o diagnóstico.

`/api/health` executa apenas `SELECT 1`; ele verifica a conexão/leitura, sem criar tabelas nem comprovar permissão de escrita. A interpretação de `BLOCKED` segue o [protocolo oficial do Turso](https://github.com/tursodatabase/turso/blob/main/serverless/PROTOCOL.md#92-error-codes).

A [documentação de uso e cobrança do Turso](https://docs.turso.tech/help/usage-and-billing) também informa `BLOCKED` ao exceder cotas de leitura, escrita ou armazenamento nos planos sujeitos a esses limites. Confira **Usage/Billing** no painel da organização; o código sozinho não identifica qual limite ou política causou o bloqueio. O aplicativo não consegue remover esse bloqueio do provedor.

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

POST requer `X-Session-Token`, obtido em `GET /api/session`. O token é assinado e expira em 24 horas. Na Vercel, `SESSION_SECRET` permite validar tokens entre instâncias; localmente, sem essa variável, a chave muda ao reiniciar. Esse controle e a restrição de host não substituem autenticação de usuários. `EQUITY_DB` permite outro caminho de banco local e `PORT` outra porta.

## Verificação

```powershell
.\.runtime\python.exe tests/test_models.py
.\.runtime\python.exe tests/test_http.py
# Todos os testes, incluindo Vercel/hosts, sessão e SQLite remoto simulado:
.\.runtime\python.exe -m unittest discover -s tests -p 'test_*.py'
# Com servidor ativo:
.\.runtime\python.exe tests/smoke_http.py
# Consulta real e gravação de WEGE3:
.\.runtime\python.exe tests/smoke_http.py --live
```

Testes cobrem fórmulas, limites, dados ausentes, taxa composta, FCFE, persistência e histórico. O teste de parser real usa o HTML local opcional `investidor10-sample.html`; sem ele, esse caso é ignorado. A API e a coleta real foram verificadas. Não houve verificação visual automatizada em navegador neste ambiente.

Fontes: [Investidor10](https://investidor10.com.br/acoes/wege3/), [API SIDRA do IBGE](https://apisidra.ibge.gov.br/), [SGS 13522](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=13522), [documentação brapi](https://brapi.dev/docs/acoes).
