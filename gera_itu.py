import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import tempfile
import time
import os  # <-- NOVO: Importação necessária para manipular pastas e arquivos
from fpdf import FPDF

# ==============================================================================
# --- FUNÇÕES DE LIMPEZA E ESTATÍSTICA ---
# ==============================================================================

def limpar_outliers_estatisticos(df, colunas=['temperatura_C', 'umidade%']):
    """
    Remove erros de sensores usando os limites físicos e o método estatístico IQR.
    Isso impede que travamentos de sensor passem despercebidos.
    """
    df_clean = df.copy()
    
    # 1. Filtro Físico (O que é impossível na natureza)
    mask_t_fisica = df_clean['temperatura_C'].between(-10, 60)
    mask_ur_fisica = df_clean['umidade%'].between(0, 100)
    df_clean.loc[~mask_t_fisica, 'temperatura_C'] = np.nan
    df_clean.loc[~mask_ur_fisica, 'umidade%'] = np.nan

    # 2. Filtro Estatístico IQR (O que é anômalo para a realidade daquela fazenda)
    for col in colunas:
        Q1 = df_clean[col].quantile(0.25)
        Q3 = df_clean[col].quantile(0.75)
        IQR = Q3 - Q1
        
        # Limites aceitáveis (1.5 vezes o IQR é o padrão ouro na estatística)
        limite_inferior = Q1 - 1.5 * IQR
        limite_superior = Q3 + 1.5 * IQR
        
        # Transforma os absurdos em NaN (vazio)
        mask_outliers = (df_clean[col] < limite_inferior) | (df_clean[col] > limite_superior)
        df_clean.loc[mask_outliers, col] = np.nan

    return df_clean

# ==============================================================================
# --- FUNÇÕES DE CÁLCULO E GRÁFICOS ---
# ==============================================================================
def calcular_metricas_itu(df_ambiente, df_clima, dias, limiar_itu, completude_minima, freq_horas=1, _progress_bar=None, _status_text=None):
    """
    Calcula as métricas de ITU aplicando travas de completude e limiares customizados.
    """
    df_amb = df_ambiente.copy()
    df_cli = df_clima.copy()

    # Padronização e Tipagem
    df_amb['Data_Coleta_Pesagem'] = pd.to_datetime(df_amb['Data_Coleta_Pesagem'], errors='coerce')
    df_cli['Data_Hora_Leitura'] = pd.to_datetime(df_cli['Data_Hora_Leitura'], errors='coerce')

    for col in ['Fazenda', 'Piquete']:
        df_amb[col] = df_amb[col].astype(str).str.strip().str.upper()
        df_cli[col] = df_cli[col].astype(str).str.strip().str.upper()

    # Cálculo do ITU Base (Fórmula NRC / Thom)
    t = df_cli['temperatura_C']
    ur = df_cli['umidade%']
    df_cli['ITU_Calculado'] = (0.8 * t) + ((ur / 100) * (t - 14.4)) + 46.4

    eventos_unicos = df_amb[['Fazenda', 'Piquete', 'Data_Coleta_Pesagem']].drop_duplicates().dropna()
    total_eventos = len(eventos_unicos)
    
    # Expectativa de dados (Ex: 7 dias * 24 horas = 168 leituras esperadas se a frequência for de 1 hora)
    leituras_esperadas = dias * (24 / freq_horas)
    
    resultados = []

    for i, (_, row) in enumerate(eventos_unicos.iterrows()):
        f = row['Fazenda']
        p = row['Piquete']
        d_pesagem = row['Data_Coleta_Pesagem']
        
        if _progress_bar is not None:
            _progress_bar.progress(min((i + 1) / total_eventos, 1.0))
        if _status_text is not None:
            _status_text.text(f"A analisar lote {i + 1}/{total_eventos} (Fazenda: {f}, Piquete: {p})...")
        
        mask_local = (df_cli['Fazenda'] == f) & (df_cli['Piquete'] == p)
        cli_local = df_cli[mask_local]
        
        res_row = {'Fazenda': f, 'Piquete': p, 'Data_Coleta_Pesagem': d_pesagem}
        
        d_fim = d_pesagem + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        d_inicio = d_pesagem - pd.Timedelta(days=dias)
        
        if cli_local.empty:
            res_row.update({'itu_media': np.nan, 'itu_dp': np.nan, 'itu_max': np.nan, 'itu_min': np.nan, 'itu_leituras_criticas': np.nan, 'confiabilidade_dados%': 0})
        else:
            mask_tempo = (cli_local['Data_Hora_Leitura'] >= d_inicio) & (cli_local['Data_Hora_Leitura'] <= d_fim)
            cli_janela = cli_local[mask_tempo]
            
            # Conta quantos ITUs válidos (não nulos) temos na janela
            leituras_validas = cli_janela['ITU_Calculado'].count()
            taxa_completude = (leituras_validas / leituras_esperadas) * 100 if leituras_esperadas > 0 else 0
            
            res_row['confiabilidade_dados%'] = round(taxa_completude, 1)

            # Trava Estatística: Só calcula se tiver dados suficientes para não mentir na média
            if taxa_completude >= completude_minima:
                res_row['itu_media'] = round(cli_janela['ITU_Calculado'].mean(), 2)
                res_row['itu_dp'] = round(cli_janela['ITU_Calculado'].std(), 2)
                res_row['itu_max'] = round(cli_janela['ITU_Calculado'].max(), 2)
                res_row['itu_min'] = round(cli_janela['ITU_Calculado'].min(), 2)
                # Conta quantas leituras ultrapassaram o limiar definido
                res_row['itu_leituras_criticas'] = int((cli_janela['ITU_Calculado'] >= limiar_itu).sum())
            else:
                # Retorna vazio para não sujar a avaliação genética com dados insuficientes
                res_row.update({'itu_media': np.nan, 'itu_dp': np.nan, 'itu_max': np.nan, 'itu_min': np.nan, 'itu_leituras_criticas': np.nan})
                
        resultados.append(res_row)

    if _status_text is not None:
        _status_text.empty()

    df_stats = pd.DataFrame(resultados)
    colunas_padrao = ['itu_media', 'itu_dp', 'itu_max', 'itu_min', 'itu_leituras_criticas', 'confiabilidade_dados%']
    df_amb_clean = df_amb.drop(columns=[c for c in colunas_padrao if c in df_amb.columns], errors='ignore')
    
    df_final = pd.merge(df_amb_clean, df_stats, on=['Fazenda', 'Piquete', 'Data_Coleta_Pesagem'], how='left')

    # Identifica os que falharam por falta de dados climáticos OU por baixa confiabilidade
    mask_missing = (df_final['itu_media'].isna()) & (df_final['Data_Coleta_Pesagem'].notna())
    df_missing = df_final.loc[mask_missing, ['Fazenda', 'Piquete', 'Data_Coleta_Pesagem', 'confiabilidade_dados%']]

    df_final['Data_Coleta_Pesagem'] = df_final['Data_Coleta_Pesagem'].dt.strftime('%Y-%m-%d')
    if not df_missing.empty:
        df_missing['Data_Coleta_Pesagem'] = df_missing['Data_Coleta_Pesagem'].dt.strftime('%Y-%m-%d')

    return df_final, df_missing

def plot_comparativo_outliers(df_raw, df_clean):
    """Gera gráficos comparando antes e depois da limpeza avançada (Boxplots e Histogramas)"""
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    fig.suptitle('Auditoria de Limpeza Estatistica (IQR): Boxplots e Distribuicao', fontsize=16, fontweight='bold')
    
    def safe_boxplot(ax, data, title, color):
        data_valid = data.dropna()
        if not data_valid.empty:
            ax.boxplot(data_valid, patch_artist=True, boxprops=dict(facecolor=color))
        else:
            ax.text(0.5, 0.5, 'Sem dados', ha='center', va='center')
        ax.set_title(title, fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.6)

    def safe_hist(ax, data, title, color):
        data_valid = data.dropna()
        if not data_valid.empty:
            ax.hist(data_valid, bins=30, color=color, edgecolor='black', alpha=0.7)
        else:
            ax.text(0.5, 0.5, 'Sem dados', ha='center', va='center')
        ax.set_title(title, fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.6)

    # --- LINHA 1: Temperatura (°C) ---
    safe_boxplot(axes[0, 0], df_raw['temperatura_C'], 'Temp Bruta (Boxplot)', '#ff9999')
    safe_boxplot(axes[0, 1], df_clean['temperatura_C'], 'Temp Limpa (Boxplot)', '#99ff99')
    safe_hist(axes[0, 2], df_raw['temperatura_C'], 'Distribuicao Temp Bruta', '#ff9999')
    safe_hist(axes[0, 3], df_clean['temperatura_C'], 'Distribuicao Temp Limpa', '#99ff99')
    
    # --- LINHA 2: Umidade (%) ---
    safe_boxplot(axes[1, 0], df_raw['umidade%'], 'Umidade Bruta (Boxplot)', '#99ccff')
    safe_boxplot(axes[1, 1], df_clean['umidade%'], 'Umidade Limpa (Boxplot)', '#99ff99')
    safe_hist(axes[1, 2], df_raw['umidade%'], 'Distribuicao Umid Bruta', '#99ccff')
    safe_hist(axes[1, 3], df_clean['umidade%'], 'Distribuicao Umid Limpa', '#99ff99')
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    return fig

# ==============================================================================
# --- GERAÇÃO DE RELATÓRIO PDF ---
# ==============================================================================
def gerar_relatorio_pdf(df_resultado, fig_outliers, info_tempo):
    class RelatorioPDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.cell(0, 10, 'Relatorio de Gestao e Genetica - Estresse Termico (ITU)', 0, 1, 'C')
            self.ln(5)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

    pdf = RelatorioPDF()
    pdf.add_page()
    
    # Seção 1: Resumo
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, '1. Resumo do Processamento Estatistico', 0, 1)
    pdf.set_font('Helvetica', '', 11)
    pdf.multi_cell(0, 8, f"Este relatorio consolida os dados climaticos cruzados com as pesagens da fazenda.\n"
                         f"Iniciamos a avaliacao em {info_tempo['start']} e finalizamos em {info_tempo['end']}.\n"
                         f"Para garantir precisao genetica, aplicamos o filtro estatistico (IQR) que identificou e limpou "
                         f"{info_tempo['outliers_removidos']} anomalias nos sensores (picos falsos ou falhas).")
    pdf.ln(5)

    # Seção 2: Parâmetros Utilizados
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, '2. Parametros Utilizados na Avaliacao', 0, 1)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 7, f"- Janela de Avaliacao: {info_tempo['dias']} dias. O sistema analisou o clima que o animal enfrentou "
                         f"neste periodo exato antes de subir na balanca.\n"
                         f"- Limiar de Estresse da Raca (ITU): {info_tempo['limiar']}. Valor a partir do qual "
                         f"consideramos que o animal comecou a sofrer com o calor e prejudicar seu desempenho.\n"
                         f"- Confiabilidade Minima Exigida: {info_tempo['completude']}%. Lotes onde o sensor ficou "
                         f"desligado ou falhou na maior parte do tempo foram descartados para nao gerar medias mentirosas.")
    pdf.ln(5)

    # Seção 3: Dicionário do Campo
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, '3. Dicionario do Campo (O que significam os indices?)', 0, 1)
    pdf.set_font('Helvetica', '', 10)
    
    dicionario = [
        "itu_media -> Estresse Termico Medio: Indice que junta Temperatura e Umidade media. Quanto mais alto, mais os animais sofreram no pasto.",
        "itu_dp -> Variacao do Estresse Termico: Indica se o clima na regiao variou muito (alivio noturno) ou se manteve em calor constante.",
        "itu_max -> Pico de Estresse Termico: O pico maximo de calor e abafamento que os animais enfrentaram no pasto durante o periodo.",
        "itu_min -> Clima Ameno: O momento mais fresco do periodo avaliado.",
        f"itu_leituras_criticas -> Leituras de Risco: Quantas vezes o sensor registrou calor excessivo (Acima do limiar de {info_tempo['limiar']}).",
        "confiabilidade_dados% -> % de tempo que o sensor esteve funcionando e enviando dados reais."
    ]
    
    for item in dicionario:
        pdf.multi_cell(0, 7, item)
        pdf.ln(2)

    # Seção 4: Estatísticas do Rebanho
    pdf.add_page(orientation="L") # Página deitada (Paisagem) para acomodar os 8 gráficos confortavelmente
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, '4. Auditoria Visual - Distribuicao e Limpeza do Sensor', 0, 1)
    pdf.set_font('Helvetica', '', 11)
    pdf.multi_cell(0, 8, "Boxplots mostram os extremos (Outliers) e as medianas. "
                         "Histogramas revelam o volume de dados e onde a maior parte do clima se concentrou.")
    pdf.ln(2)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        fig_outliers.savefig(tmpfile.name, format="png", bbox_inches="tight")
        # Gráfico estendido ocupando quase a largura toda da página paisagem
        pdf.image(tmpfile.name, x=10, w=275)

    return bytes(pdf.output(dest='S'))

# ==============================================================================
# --- RENDERIZAÇÃO DA INTERFACE (STREAMLIT) ---
# ==============================================================================
def render_itu_module():
    if 'itu_state_final' not in st.session_state:
        st.session_state['itu_state_final'] = None

    st.markdown("<style>.block-container { padding-top: 1.5rem !important; }</style>", unsafe_allow_html=True)
    st.markdown("<h1 style='margin-top: -20px;'>🌡️ Gera ITU - Genética & Clima</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    if st.session_state['itu_state_final'] is not None:
        st.success("✅ Avaliação Ambiental e Genética calculada com sucesso!")
        
        # --- AVISO VISUAL DE GRAVAÇÃO NO WORKSPACE ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            st.info(f"💾 **Segurança Ativa:** Seus arquivos foram salvos fisicamente na pasta do projeto:\n `{workspace_dir}`")
        
        res_itu = st.session_state['itu_state_final']
        t_info = res_itu.get('time_info', {})
        
        st.markdown(f"""
        <div style='background-color: #f0f2f6; padding: 15px; border-radius: 8px; margin-bottom: 20px;'>
            <h4>Resumo da Auditoria Estatística</h4>
            <p>⏱️ <b>Início do processamento:</b> {t_info.get('start')}</p>
            <p>⏱️ <b>Fim do processamento:</b> {t_info.get('end')}</p>
            <p>🧹 <b>Qualidade dos Dados:</b> Filtramos {t_info.get('outliers_removidos')} anomalias usando inteligência estatística.</p>
            <p>🎯 <b>Limiar Utilizado:</b> O estresse térmico foi contabilizado a partir do ITU <b>{t_info.get('limiar')}</b>.</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📖 Dicionário do Campo: Entenda os Resultados", expanded=True):
            st.markdown(f"""
            * **itu_media:** Estresse Térmico Médio.
            * **itu_dp:** Variação do clima (importante para avaliar se houve alívio térmico noturno).
            * **itu_max e itu_min:** Picos de calor e frio.
            * **itu_leituras_criticas:** Quantas vezes o sensor registrou calor excessivo (Acima de {t_info.get('limiar')}).
            * **confiabilidade_dados%:** Porcentagem de tempo que o equipamento esteve gerando dados perfeitos.
            """)

        df_resultado = res_itu['resultado']
        fig_outliers = res_itu.get('figura_outliers', None)
        df_falhas = res_itu.get('falhas', pd.DataFrame())
        
        if fig_outliers is not None:
            with st.expander("📊 Gráficos de Auditoria: Boxplots e Histogramas (Antes e Depois)"):
                st.markdown("Veja como a limpeza removeu ruídos (Boxplot) e qual foi a concentração real do clima da fazenda (Histograma).")
                st.pyplot(fig_outliers)
                
        if not df_falhas.empty:
            with st.expander(f"⚠️ Avisos: Lotes descartados por falta de dados ou baixa confiabilidade ({len(df_falhas)} ocorrências)"):
                st.warning("Esses lotes não receberam cálculo de ITU porque os sensores caíram muito ou não atingiram o limite mínimo de confiança de dados configurado.")
                st.dataframe(df_falhas, use_container_width=True)
        
        # --- OTIMIZAÇÃO DE LEITURA PARA DOWNLOADS ---
        # Tenta ler do disco para poupar CPU. Se por algum motivo não achar, gera novamente na memória.
        caminho_csv = os.path.join(workspace_dir, "ambiente_comITU.csv") if workspace_dir else None
        caminho_pdf = os.path.join(workspace_dir, "Relatorio_ITU_Fazenda.pdf") if workspace_dir else None

        if caminho_csv and os.path.exists(caminho_csv):
            with open(caminho_csv, "rb") as f:
                csv_bytes = f.read()
        else:
            csv_bytes = df_resultado.to_csv(sep=';', index=False).encode('utf-8')

        if caminho_pdf and os.path.exists(caminho_pdf):
            with open(caminho_pdf, "rb") as f:
                pdf_bytes = f.read()
        else:
            pdf_bytes = gerar_relatorio_pdf(df_resultado, fig_outliers, t_info)
        
        col_csv, col_pdf, col_reset = st.columns(3)
        
        with col_csv:
            st.download_button("📥 Baixar Planilha (CSV)", data=csv_bytes, file_name="ambiente_comITU.csv", mime="text/csv", use_container_width=True, type="primary")
            
        with col_pdf:
            st.download_button("📄 Baixar Relatório (PDF)", data=pdf_bytes, file_name="Relatorio_ITU_Fazenda.pdf", mime="application/pdf", use_container_width=True, type="primary")
            
        with col_reset:
            if st.button("🔄 Novo Cálculo", use_container_width=True):
                st.session_state['itu_state_final'] = None
                st.rerun()

    else:
        # TELA DE UPLOAD
        st.markdown("### Bem-vindo ao Módulo de Gestão Climática do Rebanho")
        st.markdown("Antes de calcularmos as DEPs ou o valor genético, precisamos isolar o efeito do ambiente de forma estatisticamente segura.")
        
        c1, c2 = st.columns([1, 1])
        df_amb, df_clima = None, None
        
        with c1:
            st.subheader("1. Configurações e Dados")
            
            with st.expander("⚙️ Parâmetros do Cálculo", expanded=True):
                intervalo_dias = st.number_input("Janela de avaliação (Dias antes da pesagem):", min_value=1, max_value=120, value=7)
                limiar_padrao = st.number_input("Limiar de Estresse da Raça (ITU Crítico):", min_value=60, max_value=90, value=72)
                completude = st.slider("Confiabilidade Mínima Exigida (%):", min_value=10, max_value=100, value=70)
                freq_leitura = st.selectbox("Frequência de Leitura do Sensor (em horas):", [1, 2, 4, 6, 12, 24], index=0)

                st.markdown("""
                ---
                **💡 Entenda as Configurações Acima:**
                * **Janela de Avaliação:** Quantos dias antes de ir para a balança nós vamos analisar o clima? (Ex: 7 a 14 dias costumam ditar o ritmo de ganho de peso recente).
                * **Limiar de Estresse:** Qual o limite de conforto térmico do seu gado? (Use 72 para gado Europeu/Leiteiro e valores acima de 74 para Zebuínos como Nelore).
                * **Confiabilidade Mínima:** A porcentagem mínima de tempo que o sensor precisa ter funcionado. Evita que o sistema calcule médias falsas se o equipamento quebrar ou ficar sem bateria no meio da semana.
                * **Frequência de Leitura:** De quantas em quantas horas a sua estação ou sensor de pasto registra a temperatura?
                """)

            f_amb = st.file_uploader("Arquivo de Pesagens/Ambiente (.csv)", type='csv')
            f_clima = st.file_uploader("Arquivos de Clima/Sensores (.csv)", type='csv', accept_multiple_files=True)
            
            if f_amb: 
                df_amb = pd.read_csv(f_amb, sep=';')
                df_amb['Data_Coleta_Pesagem_Val'] = pd.to_datetime(df_amb['Data_Coleta_Pesagem'], errors='coerce')
                
            if f_clima:
                try:
                    df_clima = pd.concat([pd.read_csv(f, sep=';') for f in f_clima], ignore_index=True)
                    df_clima['Data_Hora_Leitura_Val'] = pd.to_datetime(df_clima['Data_Hora_Leitura'], errors='coerce')
                except Exception as e: 
                    st.error(f"Erro na leitura do clima: {e}")

        with c2:
            st.subheader("2. Auditoria e Cálculo")
            bloquear = True
            
            if (df_amb is not None) and (df_clima is not None):
                min_c, max_c = df_clima['Data_Hora_Leitura_Val'].min(), df_clima['Data_Hora_Leitura_Val'].max()
                min_a, max_a = df_amb['Data_Coleta_Pesagem_Val'].min(), df_amb['Data_Coleta_Pesagem_Val'].max()
                
                if pd.notna(min_c) and pd.notna(min_a):
                    req_inicio = min_a - pd.Timedelta(days=intervalo_dias)
                    req_fim = max_a + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                    
                    st.info(f"🕒 **Período de Clima Identificado:**\n\nDe `{min_c.strftime('%d/%m/%Y')}` até `{max_c.strftime('%d/%m/%Y')}`")
                    
                    if req_inicio < min_c or req_fim > max_c:
                        st.error("❌ O clima não cobre todas as datas das pesagens.")
                    else:
                        st.success("✅ Período validado! Tudo pronto.")
                        bloquear = False

            if st.button("🚀 Processar e Limpar Dados", disabled=bloquear, type="primary", use_container_width=True):
                
                hora_inicio = datetime.now()
                str_inicio = hora_inicio.strftime("%d/%m/%Y %H:%M:%S")
                
                painel_tempo = st.empty()
                painel_tempo.info(f"⏳ **Início do processamento:** {str_inicio}")
                
                status_text, progress_bar = st.empty(), st.progress(0)
                
                try:
                    df_amb_clean = df_amb.drop(columns=['Data_Coleta_Pesagem_Val'])
                    df_clima_raw = df_clima.drop(columns=['Data_Hora_Leitura_Val']).copy()
                    
                    status_text.text("A aplicar filtros estatísticos nos sensores...")
                    
                    # Usa a nova função de limpeza estatística profunda (IQR + Física)
                    df_clima_clean = limpar_outliers_estatisticos(df_clima_raw)
                    
                    # Conta quantos dados foram removidos
                    total_antes = df_clima_raw['temperatura_C'].count() + df_clima_raw['umidade%'].count()
                    total_depois = df_clima_clean['temperatura_C'].count() + df_clima_clean['umidade%'].count()
                    outliers_count = total_antes - total_depois
                    
                    fig = plot_comparativo_outliers(df_clima_raw, df_clima_clean)
                    
                    novo_amb, falhas = calcular_metricas_itu(
                        df_ambiente=df_amb_clean, 
                        df_clima=df_clima_clean, 
                        dias=intervalo_dias, 
                        limiar_itu=limiar_padrao,
                        completude_minima=completude,
                        freq_horas=freq_leitura,
                        _progress_bar=progress_bar, 
                        _status_text=status_text
                    )
                    
                    hora_fim = datetime.now()
                    str_fim = hora_fim.strftime("%d/%m/%Y %H:%M:%S")
                    
                    # --- NOVO: BLOCO DE GRAVAÇÃO FÍSICA NO WORKSPACE ---
                    t_info_temp = {
                        "start": str_inicio, 
                        "end": str_fim,      
                        "outliers_removidos": outliers_count,
                        "limiar": limiar_padrao,
                        "dias": intervalo_dias,
                        "completude": completude
                    }
                    
                    # Prepara os bytes em memória
                    csv_bytes_temp = novo_amb.to_csv(sep=';', index=False).encode('utf-8')
                    pdf_bytes_temp = gerar_relatorio_pdf(novo_amb, fig, t_info_temp)
                    
                    # Resgata o caminho do projeto e força a gravação no HD
                    workspace_dir = st.session_state.get('workspace_dir')
                    if workspace_dir and os.path.exists(workspace_dir):
                        with open(os.path.join(workspace_dir, "ambiente_comITU.csv"), "wb") as f_csv:
                            f_csv.write(csv_bytes_temp)
                        with open(os.path.join(workspace_dir, "Relatorio_ITU_Fazenda.pdf"), "wb") as f_pdf:
                            f_pdf.write(pdf_bytes_temp)
                    # ----------------------------------------------------
                    
                    painel_tempo.success(f"✅ **Concluído e Salvo no Disco!** \n\n Início: {str_inicio} | Fim: {str_fim}")
                    status_text.empty()
                    progress_bar.empty()
                    
                    # Breve pausa para o usuário ler a mensagem de sucesso antes da tela ser limpa
                    time.sleep(1.5)
                    
                    st.session_state['itu_state_final'] = {
                        "resultado": novo_amb,
                        "falhas": falhas,
                        "figura_outliers": fig,
                        "time_info": t_info_temp
                    }
                    st.rerun()
                    
                except Exception as e: 
                    st.error(f"Erro no processamento: {e}")

if __name__ == "__main__":
    render_itu_module()