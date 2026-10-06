# Carteira de Cobrança

## O que é
App da cobrança para a faixa de **16 a 60 dias de atraso**. Gera a carteira do mês
dividida entre os cobradores (quantidade de clientes e valor proporcionais, lojas
críticas espalhadas entre todos) e acompanha a meta de **6 contatos por cliente**
usando as ligações que os cobradores já registram na cobrança do SIAC.

Perfis (tela **Entrar**):
- **Cobrador**: escolhe o nome e vê **somente a própria carteira**: cartões (clientes, em
  aberto na faixa, recuperado e % recuperado), tabela de clientes com contatos "x de 6",
  todos os telefones, débitos e último contato, além da **Rotina do dia** (lista de quem
  ligar, com campo para escrever a anotação de cada cliente).
- **Gestora** (Ana, Angélica ou Carla — na tela de entrada todos escolhem o próprio nome numa lista só, sem senha; gestoras em `config.GESTORES`): Visão geral, carteira de qualquer
  cobrador, Gerar carteira e Cobradores.

## Regras de negócio (todas em `config.py`)
| Regra | Valor |
|---|---|
| Quem entra | cliente com pelo menos 1 título vencido entre 16 e 60 dias |
| Débito considerado | contas 0001 (venda faturada) e 0021 (Serasa automático), em aberto |
| Lojas e prioridade | Goiânia (08 Parque Oeste) → Planaltina → Ceilândia → Gama → SOF → Asa Norte → Recife |
| Pesos | integral = 1 · parcial = 0,75 |
| Equilíbrio do valor | débito 16–60 dias (e, com peso menor, o débito total) |
| Contato | ligação registrada no SIAC **ou** anotação feita no app (exceto "só anotação"), no máximo 1 por dia por cliente |
| Recuperado | valor pago dos títulos que estavam na faixa 16–60 dias quando o cliente entrou na carteira |
| Rotina do dia | acordos do cobrador com parcela vencida primeiro → sem contato → menos contatos → contato mais antigo → loja crítica → maior débito na faixa |
| Contato efetivo | exclui 03 ocupado, 04 não atende, 05 número errado, 06/07 responsável ausente/ocupado |
| Ciclo | mensal; quem entra na faixa no meio do mês é encaixado sem mexer nos demais |

## Como rodar localmente
```bash
uv sync
cp .env.example .env   # e preencha as credenciais
uv run streamlit run app.py
```
Abre em http://localhost:8501 (precisa estar na rede da empresa ou VPN).

## Acesso aos dados
- **Leitura**: réplica do SIAC (PostgreSQL, schema `public`, somente leitura):
  `lanca` (títulos), `cobranca`/`cobratxt`/`cobtpneg` (ligações), `cliente`.
- **Gravação**: a carteira gerada, o cadastro de cobradores, as anotações e as rotinas ficam num arquivo SQLite
  local (`CARTEIRA_DB_PATH`). **No servidor, essa pasta precisa ser persistente e ter backup.**

## Estrutura
- `data/`: conexão com pool, consultas ao SIAC (com cache) e o arquivo da carteira
- `domain/`: regra de distribuição, cálculo de progresso e orquestração (Polars)
- `views/` + `ui/`: telas e componentes
- `config.py`: todas as regras ajustáveis
- `tests/`: testes (inclui os 151 clientes reais de 06/10/2026, só código, loja e valores)

## Testes
```bash
uv run pytest
uv run ruff check .
```

## Repositório
https://github.com/Dados-Pecista/carteira-cobranca
