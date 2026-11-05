import sqlite3, time, os, hmac
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from engine import DB, QUERIES, connect, fetch_once

st.set_page_config(page_title='TixBoard',page_icon='🎟️',layout='wide')
password = os.environ.get('TIXBOARD_PASSWORD')
if not password:
    st.error('TIXBOARD_PASSWORD no está configurada en el servidor. Acceso bloqueado.')
    st.stop()
if not st.session_state.get('authenticated', False):
    st.title('🎟️ TixBoard')
    with st.form('login'):
        supplied = st.text_input('Contraseña', type='password')
        submitted = st.form_submit_button('Entrar')
    if submitted:
        if hmac.compare_digest(supplied, password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error('Contraseña incorrecta')
    st.stop()
st.title('🎟️ TixBoard')
st.caption('Noticias USA · Deportes y entretenimiento · Análisis heurístico, NO predicción de precios')
connect().close()
if 'last_fetch' not in st.session_state: st.session_state.last_fetch=0
if 'last_result' not in st.session_state: st.session_state.last_result=None

with st.sidebar:
    st.header('Configuración')
    if st.button('Cerrar sesión'):
        st.session_state.authenticated = False
        st.rerun()
    interval=st.selectbox('Frecuencia de consulta', [2,5,10,15],index=1,format_func=lambda x:f'{x} minutos')
    auto=st.toggle('Monitoreo automático',value=True)
    categories=st.multiselect('Categorías',list(QUERIES),default=list(QUERIES))
    minimum=st.slider('Prioridad mínima',0,100,35,5)
    impacts=st.multiselect('Impactos', ['Positivo potencial','Negativo potencial','Mixto','Sin señal clara'],default=['Positivo potencial','Negativo potencial','Mixto'])
    search=st.text_input('Buscar artista, equipo o término')
    if st.button('Consultar fuentes ahora',use_container_width=True):
        with st.spinner('Consultando feeds...'):
            st.session_state.last_result=fetch_once()
            st.session_state.last_fetch=time.monotonic()
    st.caption('Google News RSS puede tener demoras y límites. Sin acceso a noticias privadas, redes sociales cerradas ni precios de boletos.')

@st.fragment(run_every='30s')
def dashboard():
    if auto and time.monotonic()-st.session_state.last_fetch >= interval*60:
        st.session_state.last_fetch=time.monotonic()
        with st.spinner('Actualizando noticias...'):
            st.session_state.last_result=fetch_once()
    result=st.session_state.last_result
    if result:
        st.caption(f"Última consulta: {result['at'][:19]} UTC · Nuevas: {result['new']} · Revisadas: {result['checked']}")
        if result['errors']: st.warning(f"{len(result['errors'])} feeds con errores. Ejemplo: {result['errors'][0]}")
    with sqlite3.connect(DB) as c:
        df=pd.read_sql_query('SELECT * FROM news ORDER BY detected DESC LIMIT 5000',c)
    if df.empty:
        st.info('Sin noticias todavía. Pulsa “Consultar fuentes ahora” o espera la primera consulta automática.')
        return
    df=df[df.category.isin(categories) & df.impact.isin(impacts) & (df.priority>=minimum)].copy()
    if search: df=df[df.title.str.contains(search,case=False,regex=False,na=False)]
    a,b,c=st.columns(3)
    a.metric('Noticias filtradas',len(df));b.metric('Alta prioridad (≥75)',int((df.priority>=75).sum()));c.metric('Categorías activas',len(categories))
    st.subheader('Alertas y noticias')
    if df.empty: st.info('No hay noticias que coincidan con los filtros.')
    else:
        for _,r in df.head(120).iterrows():
            with st.container(border=True):
                st.markdown(f"**[{r['title']}]({r['url']})**")
                st.caption(f"{r['category']} · {r['source']} · Publicado: {(r['published'] or 'Sin fecha')[:16]} UTC · Prioridad {r['priority']}/100 · {r['impact']}")
                st.write(r['reason'])
        st.download_button('Exportar resultados CSV',df.to_csv(index=False).encode('utf-8-sig'),'ticket_news.csv','text/csv')
    st.caption('Prioridad = puntuación heurística por palabras clave. No representa probabilidad, variación porcentual ni recomendación de compra/venta.')

dashboard()
