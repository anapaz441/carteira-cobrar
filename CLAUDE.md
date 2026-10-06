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
- Acordos: `acordo`.in_situaca A/N = ativo, I = quebrado/inativo, Q = quitado (+ `acor_par` para parcelas).
- Recuperado = `lanca` paga desde a entrada do cliente, de títulos que estavam na faixa naquela data.
- Relacionamento (`domain/relacionamento.py`): quem fechou o acordo (assinatura na obs do acordo,
  ver `config.ASSINATURAS_ACORDO`) > quem mais ligou em 60 dias, com teto pela fatia; lojas críticas
  escolhem primeiro. Usado só na tela Gerar → "Refazer pelo relacionamento" (out/2026).
- UM cliente = UM cobrador (mesmo com títulos/acordos em várias lojas): PK (ciclo_id, codcli) na
  carteira, `adicionar_clientes` usa INSERT OR IGNORE (nunca move ninguém; troca só por mover_cliente).
- Meus acordos / acordo atrasado na rotina: dono = cobrador da carteira do mês; fora da carteira =
  quem assinou o acordo mais recente (`servico.dono_dos_acordos`). Alerta para parcela atrasada.
- Simulador de acordo (`domain/simulador.py` + `ui/simulador.py`): replica ACO000.prg do SIAC
  (juros título×%/30×dias, multa 3%, bisseção do % quando há desconto, juros<11,80% ou multa<3% → "N",
  parcela mín. R$50, 1º vcto ≤15 dias). Acordo é POR LOJA (cada loja tem seu LANCA no SIAC):
  cliente com títulos em mais de uma loja escolhe a loja no simulador. Na carteira o cliente
  aparece uma vez só, na loja de maior débito (`loja_principal`), com o débito somado. Validado contra o acordo real 06/000507 em `tests/test_simulador.py`.
- acordo.in_situaca: A=ativo, N=NÃO AUTORIZADO, I=inativo, Q=quitado (tabela dominio).
- Regras ajustáveis: `config.py`.

## Dependências principais
streamlit, polars, pandas, sqlalchemy, psycopg2-binary, python-dotenv, plotly
