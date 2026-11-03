"""Painel Macroeconômico Brasil
Dados públicos da API SGS do Banco Central do Brasil (sem chave de acesso).

Séries usadas:
  1   -> Dólar americano (câmbio livre, diário)
  432 -> Meta da taxa Selic definida pelo Copom (% a.a., diário)
  433 -> IPCA, variação mensal (%)
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# =========================================================
# 1. CONFIGURAÇÕES GERAIS
# =========================================================

st.set_page_config(
    page_title="Macro Brasil | Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CORES = {
    "fundo": "#0B1120",
    "painel": "#121C2E",
    "borda": "#26364D",
    "texto": "#F4F7FB",
    "texto_secundario": "#A9B8CC",
    "verde": "#10B981",
    "azul": "#3B82F6",
    "amarelo": "#F59E0B",
    "vermelho": "#EF4444",
}

URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
SERIE_DOLAR, SERIE_SELIC, SERIE_IPCA = 1, 432, 433
PERIODOS = {"6 meses": 183, "1 ano": 365, "2 anos": 730, "5 anos": 1825}


# =========================================================
# 2. ESTILO VISUAL
# =========================================================

def aplicar_estilo():
    st.markdown(
        f"""
        <style>
        :root {{ color-scheme: dark; }}
        .stApp {{ background: {CORES["fundo"]}; color: {CORES["texto"]}; }}
        .block-container {{ max-width: 1500px; padding-top: 1.1rem; padding-bottom: 2.5rem; }}
        [data-testid="stHeader"] {{ background: rgba(11, 17, 32, 0.85); }}
        [data-testid="stSidebar"] {{ background: {CORES["painel"]}; border-right: 1px solid {CORES["borda"]}; }}
        h1, h2, h3, h4, p, label {{ color: {CORES["texto"]}; }}
        [data-testid="stMetric"] {{
            background: linear-gradient(145deg, #162238, #111B2C);
            border: 1px solid {CORES["borda"]};
            padding: 17px 18px;
            border-radius: 15px;
        }}
        [data-testid="stMetricLabel"] p {{ color: {CORES["texto_secundario"]} !important; font-size: 0.84rem; }}
        [data-testid="stMetricValue"] {{ color: {CORES["texto"]} !important; font-weight: 700; }}
        [data-testid="stPlotlyChart"] {{
            background: {CORES["painel"]};
            border: 1px solid {CORES["borda"]};
            border-radius: 15px;
            padding: 7px;
        }}
        .hero {{
            background: radial-gradient(circle at 90% 0%, rgba(59,130,246,0.20), transparent 35%),
                        linear-gradient(120deg, #15243A, #10203A);
            border: 1px solid #1E3A66;
            border-radius: 18px;
            padding: 22px 26px;
            margin-bottom: 20px;
        }}
        .hero-eyebrow {{ color: {CORES["azul"]}; text-transform: uppercase; letter-spacing: 0.14em; font-size: 0.72rem; font-weight: 700; }}
        .hero-title {{ color: #FFFFFF; font-size: clamp(1.65rem, 3vw, 2.25rem); font-weight: 800; margin: 0; }}
        .hero-subtitle {{ color: #FFFFFF; font-size: 0.94rem; margin-top: 6px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def estilizar_grafico(fig, altura: int = 380):
    fig.update_layout(
        template="plotly_dark",
        height=altura,
        paper_bgcolor=CORES["painel"],
        plot_bgcolor=CORES["painel"],
        font=dict(family="Arial, sans-serif", size=12, color=CORES["texto"]),
        margin=dict(l=18, r=18, t=50, b=20),
        legend=dict(font=dict(color=CORES["texto_secundario"]), bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(169,184,204,0.10)", showline=False)
    fig.update_yaxes(gridcolor="rgba(169,184,204,0.10)", showline=False)
    return fig


def fmt_br(valor: float, casas: int = 2) -> str:
    """Formata número no padrão brasileiro (1.234,56)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


# =========================================================
# 3. COLETA E TRATAMENTO DOS DADOS (API DO BANCO CENTRAL)
# =========================================================

@st.cache_data(ttl=3600, show_spinner="Consultando a API do Banco Central...")
def buscar_serie(codigo: int, inicio: date, fim: date) -> pd.DataFrame:
    """Baixa uma série do SGS. Séries diárias aceitam janelas de até 10 anos."""
    params = {
        "formato": "json",
        "dataInicial": inicio.strftime("%d/%m/%Y"),
        "dataFinal": fim.strftime("%d/%m/%Y"),
    }
    resposta = requests.get(
        URL_BCB.format(codigo=codigo),
        params=params,
        headers={"User-Agent": "macro-brasil-dashboard"},
        timeout=30,
    )
    resposta.raise_for_status()

    df = pd.DataFrame(resposta.json())
    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])

    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df.dropna().sort_values("data").reset_index(drop=True)


def carregar_dados(dias: int):
    """Busca as três séries e calcula os indicadores derivados."""
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    # O IPCA acumulado em 12 meses precisa de 12 meses de histórico antes do início
    inicio_ipca = inicio - timedelta(days=400)

    dolar = buscar_serie(SERIE_DOLAR, inicio, fim)
    selic = buscar_serie(SERIE_SELIC, inicio, fim)
    ipca = buscar_serie(SERIE_IPCA, inicio_ipca, fim)

    if ipca.empty:
        return dolar, selic, ipca, pd.DataFrame()

    # IPCA acumulado em 12 meses: produto dos fatores mensais (1 + variação)
    ipca["acum_12m"] = (np.exp(np.log1p(ipca["valor"] / 100).rolling(12).sum()) - 1) * 100

    # Juro real ex-post: (1 + Selic) / (1 + IPCA 12m) - 1, mês a mês
    selic_mensal = selic.set_index("data")["valor"].resample("MS").last().rename("selic")
    ipca_12m = ipca.set_index("data")["acum_12m"].rename("ipca_12m")
    real = pd.concat([selic_mensal, ipca_12m], axis=1).dropna()
    real["juro_real"] = ((1 + real["selic"] / 100) / (1 + real["ipca_12m"] / 100) - 1) * 100

    ipca = ipca[ipca["data"] >= pd.Timestamp(inicio)].reset_index(drop=True)
    return dolar, selic, ipca, real.reset_index()


# =========================================================
# 4. INTERFACE
# =========================================================

aplicar_estilo()

st.sidebar.markdown("## 📈 Macro Brasil")
st.sidebar.caption("DADOS ABERTOS · BANCO CENTRAL")
st.sidebar.divider()

pagina = st.sidebar.radio(
    "Navegação",
    ["Visão Geral", "Câmbio", "Juros e Inflação", "Dados"],
    format_func=lambda item: {
        "Visão Geral": "📊  Visão Geral",
        "Câmbio": "💵  Câmbio",
        "Juros e Inflação": "🏦  Juros e Inflação",
        "Dados": "🗂️  Dados",
    }[item],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown("### Filtros")
periodo = st.sidebar.select_slider("Período", options=list(PERIODOS.keys()), value="2 anos")

try:
    dolar, selic, ipca, real = carregar_dados(PERIODOS[periodo])
except requests.RequestException as erro:
    st.error(f"Não foi possível consultar a API do Banco Central: {erro}")
    st.stop()

if dolar.empty or selic.empty or ipca.empty or real.empty:
    st.warning("A API não retornou dados suficientes para o período escolhido.")
    st.stop()

# Valores mais recentes
dolar_ultimo = dolar.iloc[-1]["valor"]
dolar_var = (dolar_ultimo / dolar.iloc[-2]["valor"] - 1) * 100 if len(dolar) > 1 else 0.0
selic_atual = selic.iloc[-1]["valor"]
ipca_12m_atual = ipca.dropna(subset=["acum_12m"]).iloc[-1]["acum_12m"]
juro_real_atual = real.iloc[-1]["juro_real"]

st.markdown(
    f"""<div class="hero">
    <div class="hero-eyebrow">Painel Analytics · Economia</div>
    <div class="hero-title">Macro Brasil Dashboard</div>
    <div class="hero-subtitle">Câmbio, juros e inflação &nbsp;·&nbsp; Últimos {periodo}
    &nbsp;·&nbsp; Fonte: API SGS do Banco Central do Brasil</div>
</div>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# PÁGINA 1: VISÃO GERAL
# ---------------------------------------------------------
if pagina == "Visão Geral":
    st.markdown("### Indicadores Chave")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "💵 Dólar",
        f"R$ {fmt_br(dolar_ultimo, 4)}",
        f"{dolar_var:+.2f}% vs dia anterior".replace(".", ","),
        delta_color="off",
    )
    c2.metric("🏦 Selic (meta)", f"{fmt_br(selic_atual)}% a.a.")
    c3.metric("🛒 IPCA 12 meses", f"{fmt_br(ipca_12m_atual)}%")
    c4.metric(
        "📐 Juro real",
        f"{fmt_br(juro_real_atual)}% a.a.",
        help="(1 + Selic) / (1 + IPCA 12m) - 1. Aproximação ex-post.",
    )

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.line(dolar, x="data", y="valor", title="Dólar (R$)",
                      labels={"data": "", "valor": "R$"},
                      color_discrete_sequence=[CORES["verde"]])
        st.plotly_chart(estilizar_grafico(fig), use_container_width=True)
    with col_b:
        fig = px.line(selic, x="data", y="valor", title="Meta da Selic (% a.a.)",
                      labels={"data": "", "valor": "% a.a."}, line_shape="hv",
                      color_discrete_sequence=[CORES["azul"]])
        st.plotly_chart(estilizar_grafico(fig), use_container_width=True)

# ---------------------------------------------------------
# PÁGINA 2: CÂMBIO
# ---------------------------------------------------------
elif pagina == "Câmbio":
    st.markdown("### Dólar no Período")

    dolar = dolar.copy()
    dolar["media_30d"] = dolar["valor"].rolling(30).mean()
    retornos = dolar["valor"].pct_change().dropna() * 100
    volatilidade = retornos.std() * np.sqrt(252)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mínima", f"R$ {fmt_br(dolar['valor'].min(), 4)}")
    c2.metric("Máxima", f"R$ {fmt_br(dolar['valor'].max(), 4)}")
    c3.metric("Média", f"R$ {fmt_br(dolar['valor'].mean(), 4)}")
    c4.metric("Volatilidade anualizada", f"{fmt_br(volatilidade)}%",
              help="Desvio padrão das variações diárias × √252.")

    fig = px.line(
        dolar, x="data", y=["valor", "media_30d"],
        title="Dólar e média móvel de 30 dias",
        labels={"data": "", "value": "R$", "variable": ""},
        color_discrete_sequence=[CORES["verde"], CORES["amarelo"]],
    )
    fig.for_each_trace(lambda t: t.update(name={"valor": "Dólar", "media_30d": "Média 30d"}[t.name]))
    st.plotly_chart(estilizar_grafico(fig, 440), use_container_width=True)

    fig_hist = px.histogram(
        retornos, nbins=50, title="Distribuição das variações diárias (%)",
        labels={"value": "Variação diária (%)", "count": "Dias"},
        color_discrete_sequence=[CORES["azul"]],
    )
    fig_hist.update_layout(showlegend=False)
    st.plotly_chart(estilizar_grafico(fig_hist), use_container_width=True)

# ---------------------------------------------------------
# PÁGINA 3: JUROS E INFLAÇÃO
# ---------------------------------------------------------
elif pagina == "Juros e Inflação":
    st.markdown("### Juros e Inflação")
    col_a, col_b = st.columns(2)

    with col_a:
        fig = px.bar(ipca, x="data", y="valor", title="IPCA mensal (%)",
                     labels={"data": "", "valor": "% no mês"},
                     color_discrete_sequence=[CORES["amarelo"]])
        st.plotly_chart(estilizar_grafico(fig), use_container_width=True)

    with col_b:
        fig = px.line(ipca.dropna(subset=["acum_12m"]), x="data", y="acum_12m",
                      title="IPCA acumulado em 12 meses (%)",
                      labels={"data": "", "acum_12m": "%"}, markers=True,
                      color_discrete_sequence=[CORES["vermelho"]])
        st.plotly_chart(estilizar_grafico(fig), use_container_width=True)

    fig = px.area(real, x="data", y="juro_real",
                  title="Juro real ex-post (% a.a.)",
                  labels={"data": "", "juro_real": "% a.a."},
                  color_discrete_sequence=[CORES["verde"]])
    st.plotly_chart(estilizar_grafico(fig, 420), use_container_width=True)
    st.caption("Juro real = (1 + Selic meta) / (1 + IPCA acumulado em 12 meses) − 1, calculado mês a mês.")

# ---------------------------------------------------------
# PÁGINA 4: DADOS
# ---------------------------------------------------------
elif pagina == "Dados":
    st.markdown("### Dados Brutos")
    escolha = st.selectbox("Série", ["Dólar (série 1)", "Selic meta (série 432)", "IPCA mensal (série 433)"])
    tabela = {"Dólar (série 1)": dolar, "Selic meta (série 432)": selic, "IPCA mensal (série 433)": ipca}[escolha]
    tabela = tabela[["data", "valor"]].sort_values("data", ascending=False)

    st.dataframe(tabela, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Baixar CSV",
        data=tabela.to_csv(index=False).encode("utf-8"),
        file_name=f"{escolha.split(' ')[0].lower()}_bcb.csv",
        mime="text/csv",
    )

st.divider()
st.caption("Fonte: Banco Central do Brasil · API SGS (dados abertos) · Cache de 1 hora.")
