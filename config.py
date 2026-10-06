"""Constantes do app Carteira de Cobrança.

Tudo que é "regra de negócio ajustável" fica aqui, num lugar só.
Se a regra mudar (faixa de atraso, meta, peso dos cobradores), mude AQUI.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # lê o .env antes de qualquer configuração

# ---------------------------------------------------------------------------
# Cache (segundos). O SIAC em `public` é réplica em tempo real; o ttl só diz
# quanto a TELA pode atrasar. Contatos: 2 min para o cobrador ver o progresso
# logo depois de registrar a ligação no SIAC.
# ---------------------------------------------------------------------------
TTL_FREQUENTE = 300  # 5 min — títulos em aberto / clientes elegíveis
TTL_CONTATOS = 120  # 2 min — ligações registradas no SIAC

# ---------------------------------------------------------------------------
# Faixa de atraso da carteira
# Regra combinada: entra o cliente que tem PELO MENOS UM título vencido
# entre 16 e 60 dias (mesmo que tenha outros mais antigos).
# ---------------------------------------------------------------------------
DIAS_ATRASO_MIN = 16
DIAS_ATRASO_MAX = 60

# Contas (codcon) consideradas como débito do cliente
CONTAS_DEBITO = ("0001", "0021")  # 0001 = Venda faturada | 0021 = Serasa (automático)

# ---------------------------------------------------------------------------
# Lojas — na ordem de PRIORIDADE (1 = mais crítica).
# Goiânia = Parque Oeste (08) no SIAC. Pecista (01) e Vendas Online ficam de fora.
# ---------------------------------------------------------------------------
LOJAS_PRIORIDADE: dict[str, str] = {
    "08": "Goiânia",
    "07": "Planaltina",
    "04": "Ceilândia",
    "05": "Gama",
    "06": "SOF",
    "03": "Asa Norte",
    "10": "Recife",
}
LOJAS_CARTEIRA = tuple(LOJAS_PRIORIDADE.keys())
PRIORIDADE_LOJA = {cod: i + 1 for i, cod in enumerate(LOJAS_PRIORIDADE)}

# ---------------------------------------------------------------------------
# Cobradores
# Tempo integral = peso 1. Parcial = 1/4 a menos (0,75).
# ---------------------------------------------------------------------------
PESO_TIPO = {"Integral": 1.0, "Parcial": 0.75}

# Na distribuição, quanto pesa equilibrar cada coisa (quantidade x valor x loja).
PESO_EQUILIBRIO_QTD = 1.0
PESO_EQUILIBRIO_VALOR = 1.0
PESO_EQUILIBRIO_LOJA = 0.5

# Qual valor é usado para equilibrar a carteira:
#  "vl_vencido" = tudo que o cliente deve vencido | "vl_faixa" = só títulos 16–60 dias
METRICA_VALOR_EQUILIBRIO = "vl_faixa"
# Peso do débito vencido TOTAL no ajuste fino (0 = ignora; 1 = tão importante quanto o principal)
PESO_VALOR_SECUNDARIO = 0.5

# ---------------------------------------------------------------------------
# Meta de contatos
# ---------------------------------------------------------------------------
META_CONTATOS = 6
# Conta no máximo 1 contato por cliente por dia (evita 6 ligações seguidas valerem a meta)
UM_CONTATO_POR_DIA = True

# Resultados da ligação (cobtpneg) que NÃO contam como contato efetivo
# (não conseguiu falar com quem decide).
NEGOCIACAO_NAO_EFETIVA = ("03", "04", "05", "06", "07", "SR")  # "SR" = sem retorno (app)

# Quantos dias para trás buscar o "último contato" do cliente
DIAS_HISTORICO_ULTIMO_CONTATO = 365

# ---------------------------------------------------------------------------
# Onde fica salvo a carteira gerada (o SIAC é só leitura).
# É um arquivo SQLite local do app. No servidor, a TI deve manter essa pasta
# persistente e com backup.
# ---------------------------------------------------------------------------
CAMINHO_BANCO_CARTEIRA = os.getenv("CARTEIRA_DB_PATH", "dados_app/carteira.db")

# ---------------------------------------------------------------------------
# Acesso
# Senha da visão de GESTOR (gerar carteira, ver todos). Fica no .env.
# ---------------------------------------------------------------------------
GESTOR_SENHA = os.getenv("GESTOR_SENHA", "")
# Matrículas que podem entrar como gestor (todas usam a mesma senha acima)
GESTORES = tuple(m.strip() for m in os.getenv("GESTORES", "2184,1386,8630").split(",") if m.strip())

# ---------------------------------------------------------------------------
# Rotina do dia
# ---------------------------------------------------------------------------
ROTINA_TAMANHO_PADRAO = 15  # quantos clientes entram na rotina gerada
# Registro de contato feito no app (o cobrador escolhe o tipo e o canal)
CONTATO_EFETIVO = "EF"  # falou com o cliente → conta como contato E como efetivo
CONTATO_SEM_RETORNO = "SR"  # tentou e não teve retorno → conta como contato, não efetivo
SO_ANOTACAO = "SO_ANOTACAO"  # só uma informação → não conta como contato
TIPOS_CONTATO_APP = {
    CONTATO_EFETIVO: "✅ Contato efetivo (falou com o cliente)",
    CONTATO_SEM_RETORNO: "📵 Contato feito, sem retorno",
    SO_ANOTACAO: "📝 Só anotação (não conta como contato)",
}
CANAIS_CONTATO = ["Ligação", "WhatsApp"]

# ---------------------------------------------------------------------------
# Acordos (acordo.in_situaca no SIAC)
# ---------------------------------------------------------------------------
ACORDO_ATIVO = ("A", "N")  # A = ativo · N = não autorizado (fechado, aguardando autorização)

# Simulador de acordo — mesmas regras da tela de Acordos do SIAC (ACO000.prg)
ACORDO_JUROS_MES = 12.0  # % ao mês (_JurosMes; é o juros gravado nos títulos)
ACORDO_MULTA = 3.0  # % (_MultaFirma)
ACORDO_JUROS_MIN_AUTOMATICO = 11.80  # abaixo disso (ou multa < 3%) o acordo fica "N"
ACORDO_PARCELA_MIN = 50.0  # parcela mínima (R$)
ACORDO_PRIMEIRO_VCTO_MAX_DIAS = 15  # 1º vencimento em até 15 dias
ACORDO_DIAS_SEMANA = {"02": "Segunda", "03": "Terça", "04": "Quarta", "05": "Quinta", "06": "Sexta"}
ACORDO_ROTULO = {
    "A": "Ativo",
    "N": "Não autorizado (aguardando)",
    "I": "Quebrado / inativo",
    "Q": "Quitado",
}
SEM_ACORDO = "Sem acordo"
# Assinaturas no fim da observação do acordo que NÃO são só o primeiro nome do cobrador.
# Conferir com a gestão: "PEDRO PAULO" e "PEDRO LIMA" foram considerados o Pedro (8177).
ASSINATURAS_ACORDO = {"PEDRO PAULO": "8177", "PEDRO LIMA": "8177"}

# Nomes de coluna exibidos na tela
COLUNAS_PT = {
    "prioridade": "Prior.",
    "loja": "Loja",
    "codcli": "Código",
    "cliente": "Cliente",
    "fantasia": "Fantasia",
    "telefone": "Telefone",
    "whatsapp": "Celular/WhatsApp",
    "qt_titulos": "Qtd títulos",
    "vl_vencido": "Débito vencido (R$)",
    "vl_faixa": "Débito 16–60d (R$)",
    "dias_atraso_max": "Dias atraso (máx)",
    "contatos": "Contatos",
    "efetivos": "Efetivos",
    "progresso": "Progresso meta",
    "ult_data": "Último contato",
    "ult_quem": "Quem falou",
    "ult_resultado": "Resultado",
    "ult_texto": "Anotação",
    "prox_ligacao": "Próx. ligação",
    "status": "Situação",
}
