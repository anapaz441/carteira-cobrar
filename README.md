# Carteira de Cobrança

## O que é
App da cobrança para a faixa de **16 a 60 dias de atraso**. Gera a carteira do mês
dividida entre os cobradores (quantidade de clientes e valor proporcionais, lojas
críticas espalhadas entre todos) e acompanha a meta de **6 contatos por cliente**
usando as ligações que os cobradores já registram na cobrança do SIAC.

Telas:
- **Minha carteira**: o cobrador escolhe o nome e vê os clientes dele, com barra de
  contatos (x de 6), telefone/WhatsApp, débito, último contato e quem falou.
- **Visão geral**: painel da gestão com débito, recuperado e progresso por cobrador e por loja.
- **Gerar carteira**: prévia e geração da carteira do mês, encaixe de clientes novos e
  troca manual de cobrador.
- **Cobradores**: nome, código do SIAC e integral/parcial.

## Regras de negócio (todas em `config.py`)
| Regra | Valor |
|---|---|
| Quem entra | cliente com pelo menos 1 título vencido entre 16 e 60 dias |
| Débito considerado | contas 0001 (venda faturada) e 0021 (Serasa automático), em aberto |
| Lojas e prioridade | Goiânia (08 Parque Oeste) → Planaltina → Ceilândia → Gama → SOF → Asa Norte → Recife |
| Pesos | integral = 1 · parcial = 0,75 |
| Equilíbrio do valor | débito 16–60 dias (e, com peso menor, o débito total) |
| Contato | cada ligação registrada no SIAC, no máximo 1 por dia por cliente |
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
- **Gravação**: a carteira gerada e o cadastro de cobradores ficam num arquivo SQLite
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
