# Carteira de Cobrança

## Sobre o projeto
Streamlit da cobrança (faixa 16–60 dias). Gera a carteira mensal dividida entre
cobradores e acompanha a meta de 6 contatos por cliente a partir das ligações do SIAC.

## Usuário
A responsável é Ana Paz, da cobrança. Não é da área de tecnologia: explique os passos
com clareza e paciência.

## Como rodar localmente
```bash
uv sync
uv run streamlit run app.py
```

## Decisões importantes
- SIAC em `public` (réplica em tempo real). Nunca D-1/H-1.
- Títulos: `lanca` tipo 'R', `pagamento IS NULL`, codcon 0001/0021, lojas 03,04,05,06,07,08,10.
- Ligações: `cobranca` (cd_usuario = cobrador, cd_negocia = resultado) + `cobratxt` (texto,
  join por cd_loja + sq_cobran) + `cobtpneg` (descrição). `cobranca` não tem índice além da
  PK (~0,6 s por consulta), por isso o cache.
- A carteira salva fica em SQLite (`data/carteira_store.py`), não no SIAC (somente leitura).
- Distribuição: `domain/distribuicao.py` (guloso por loja/valor + ajuste fino por trocas na
  mesma loja). Testado com os clientes reais em `tests/fixtures`.
- Perfis: `ui/sessao.py` + `app.py` (cobrador só vê `views/carteira_cobrador.py`; gestor tudo).
- Anotações e rotinas ficam no SQLite (tabelas `anotacoes` e `rotinas`) e NÃO vão para o SIAC.
- Recuperado = `lanca` paga desde a entrada do cliente, de títulos que estavam na faixa naquela data.
- Regras ajustáveis: `config.py`.

## Dependências principais
streamlit, polars, pandas, sqlalchemy, psycopg2-binary, python-dotenv, plotly
