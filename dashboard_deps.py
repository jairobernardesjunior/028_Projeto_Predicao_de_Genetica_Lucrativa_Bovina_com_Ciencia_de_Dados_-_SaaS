import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os
import zipfile
import io
import tempfile
from fpdf import FPDF

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def carregar_solutions(file_buffer):
    """
    Função robusta para carregar o arquivo solutions, 
    ignorando a primeira linha de texto do Fortran e nomeando corretamente.
    """
    try:
        df = pd.read_csv(file_buffer, sep=r'\s+', skiprows=1, header=None, engine='python')
        
        if len(df.columns) == 4:
            df.columns = ['Trait', 'Effect', 'Level', 'Valor']
        elif len(df.columns) == 5:
            df.columns = ['Trait', 'Effect', 'Level', 'Valor', 'Erro_Padrao']
        else:
            df.columns = [f'Col_{i}' for i in range(len(df.columns))]
            
        df['Trait'] = df['Trait'].astype(str)
        df['Effect'] = df['Effect'].astype(str)
        df['Level'] = df['Level'].astype(str)
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        
        return df.dropna()
    except Exception as e:
        st.error(f"Erro ao processar o arquivo solutions: {e}")
        return None

def carregar_pedigree(file_buffer):
    """
    Lê o arquivo renadd.ped (ou similar) gerado pelo RENUMF90.
    Extrai a primeira coluna (Level/ID Renumerado) e a última coluna (ID Original).
    """
    try:
        df_ped = pd.read_csv(file_buffer, sep=r'\s+', header=None, engine='python')
        df_map = pd.DataFrame({
            'Level': df_ped.iloc[:, 0].astype(str),
            'ID_Original': df_ped.iloc[:, -1].astype(str)
        })
        return df_map
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de pedigree: {e}")
        return None

def gerar_relatorio_pdf(df_bioeconomico, df_isolado, trait_nome):
    """
    Gera um relatório PDF contendo o resumo das análises em tela.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Relatorio de Avaliacao Genetica - Boi Gene", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt=f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    # Seção 1: Valor Bioeconômico
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="1. Top 15 Animais - Maior Valor Bioeconomico Agregado (R$)", ln=True, align='L')
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 5, txt="Este indice representa a rentabilidade esperada por filho produzido, ponderando as caracteristicas pelo seu impacto financeiro na fazenda.")
    pdf.ln(5)
    
    # Cabeçalho da Tabela 1
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 8, txt="Identificacao (Brinco/RGN)", border=1)
    pdf.cell(60, 8, txt="Cod. Interno (BLUP)", border=1)
    pdf.cell(60, 8, txt="Indice Financeiro (R$)", border=1, ln=True)
    
    # Dados da Tabela 1 (Top 15)
    pdf.set_font("Arial", size=10)
    for index, row in df_bioeconomico.head(15).iterrows():
        pdf.cell(60, 8, txt=str(row['Identificação (Brinco/RGN)']), border=1)
        pdf.cell(60, 8, txt=str(row['Cód. Interno (BLUP)']), border=1)
        pdf.cell(60, 8, txt=f"R$ {row['Valor_Bioeconomico']:.2f}", border=1, ln=True)
        
    pdf.ln(15)
    
    # Seção 2: Característica Isolada
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=f"2. Top 15 Animais Isolados para: {trait_nome}", ln=True, align='L')
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 5, txt="Ranking especifico focado apenas no ganho genetico desta caracteristica (DEP), desconsiderando outras variaveis economicas.")
    pdf.ln(5)
    
    # Cabeçalho da Tabela 2
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 8, txt="Identificacao (Brinco/RGN)", border=1)
    pdf.cell(60, 8, txt="Cod. Interno (BLUP)", border=1)
    pdf.cell(60, 8, txt="Valor da DEP", border=1, ln=True)
    
    # Dados da Tabela 2 (Top 15)
    pdf.set_font("Arial", size=10)
    for index, row in df_isolado.head(15).iterrows():
        pdf.cell(60, 8, txt=str(row['Identificação (Brinco/RGN)']), border=1)
        pdf.cell(60, 8, txt=str(row['Cód. Interno (BLUP)']), border=1)
        pdf.cell(60, 8, txt=f"{row['DEP']:.4f}", border=1, ln=True)
        
    # Salvar em um arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_file.name)
    return temp_file.name

# ==========================================
# MÓDULO PRINCIPAL DO DASHBOARD
# ==========================================

def render_dashboard_module():
    st.title("📊 Fase 3: Dashboard de Avaliação Genética e Valor Bioeconômico")
    st.markdown("""
    Analise o mérito genético do rebanho de forma simples e visual. Identifique os melhores reprodutores
    baseando-se no **Valor Bioeconômico**, que pondera as características preditas pelo seu impacto financeiro na fazenda.
    """)

    # ==========================================
    # 1. ÁREA DE CARGA DE DADOS (PÁGINA PRINCIPAL)
    # ==========================================
    st.subheader(
        "📂 1. Carga de Dados (Pacotes ZIP)", 
        help="Nesta área, o sistema exige os dois pacotes matemáticos finais gerados pelo Fortran. Eles contêm todas as informações necessárias para rankear os animais."
    )
    
    workspace_dir = st.session_state.get('workspace_dir')
    caminho_zip_pred_auto = os.path.join(workspace_dir, "Predicoes_GEBVs_Finais_Pronto.zip") if workspace_dir else None
    caminho_zip_var_auto = os.path.join(workspace_dir, "Variancias_Bifurcadas_Pronto.zip") if workspace_dir else None

    col_up1, col_up2 = st.columns(2)

    with col_up1:
        help_pred = "Este pacote contém os arquivos 'solutions'. É nele que estão armazenados os valores genéticos brutos (EBVs) calculados matematicamente na Fase 3."
        if caminho_zip_pred_auto and os.path.exists(caminho_zip_pred_auto):
            st.success("📁 **'Predicoes_GEBVs_Finais_Pronto.zip'** (Detectado)")
            f_zip_pred_up = st.file_uploader("Opcional: Trocar Pacote de Predições", type="zip", key="dash_pred", help=help_pred)
            f_zip_pred = f_zip_pred_up if f_zip_pred_up is not None else caminho_zip_pred_auto
        else:
            f_zip_pred = st.file_uploader("Carregar 'Predicoes_GEBVs_Finais_Pronto.zip'", type="zip", key="dash_pred", help=help_pred)

    with col_up2:
        help_var = "Este pacote da Fase 2 contém a genealogia (para rastrear de quem o animal descende), o Mapa Bioeconômico e o Mapa de Efeitos."
        if caminho_zip_var_auto and os.path.exists(caminho_zip_var_auto):
            st.success("📁 **'Variancias_Bifurcadas_Pronto.zip'** (Detectado)")
            f_zip_var_up = st.file_uploader("Opcional: Trocar Pacote de Variâncias", type="zip", key="dash_var", help=help_var)
            f_zip_var = f_zip_var_up if f_zip_var_up is not None else caminho_zip_var_auto
        else:
            f_zip_var = st.file_uploader("Carregar 'Variancias_Bifurcadas_Pronto.zip'", type="zip", key="dash_var", help=help_var)
        
    if not f_zip_pred or not f_zip_var:
        st.info("⚠️ Aguardando a carga dos pacotes **ZIP** acima para gerar as análises.")
        return

    # --- PROCESSAMENTO ---
    df_deps = None
    
    with st.spinner("Descompactando pacotes e rastreando arquivos dinâmicos..."):
        start_time = datetime.now()
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        # 1. Extraindo as Soluções (do ZIP de Predições)
        sol_list = []
        try:
            with zipfile.ZipFile(f_zip_pred, 'r') as z_pred:
                for file_info in z_pred.infolist():
                    fname = file_info.filename.lower()
                    if fname == 'solutions_linear.txt':
                        sol_list.append(('lin', io.BytesIO(z_pred.read(file_info))))
                    elif fname == 'solutions_categ.txt':
                        sol_list.append(('cat', io.BytesIO(z_pred.read(file_info))))
        except Exception as e:
            st.error(f"Erro ao ler o ZIP de Predições: {e}")
            return
            
        # 2. Extraindo Pedigrees Dinâmicos e Mapas (do ZIP de Variâncias)
        ped_map = {}
        mapa_bio = None
        mapa_efeitos_io = None
        try:
            with zipfile.ZipFile(f_zip_var, 'r') as z_var:
                for file_info in z_var.infolist():
                    fname = file_info.filename.lower()
                    if fname.startswith('renadd_linear') and fname.endswith('.ped'):
                        ped_map['lin'] = io.BytesIO(z_var.read(file_info))
                    elif fname.startswith('renadd_categ') and fname.endswith('.ped'):
                        ped_map['cat'] = io.BytesIO(z_var.read(file_info))
                    elif fname == 'mapa_bioeconomico.csv':
                        mapa_bio = io.BytesIO(z_var.read(file_info))
                    elif fname == 'mapa_efeitos.csv':
                        mapa_efeitos_io = io.BytesIO(z_var.read(file_info))
        except Exception as e:
            st.error(f"Erro ao ler o ZIP de Variâncias: {e}")
            return

        if not sol_list:
            st.error("Nenhum arquivo 'solutions' encontrado no pacote de Predições.")
            return

        # 3. Processa cada arquivo solutions dinamicamente
        dfs_to_concat = []
        passo_progresso = 80 / len(sol_list)
        progresso_atual = 0

        for chave_sol, sol_buffer in sol_list:
            df_atual = carregar_solutions(sol_buffer)
            
            if df_atual is not None and not df_atual.empty:
                if chave_sol in ped_map:
                    ped_map[chave_sol].seek(0)
                    df_ped_atual = carregar_pedigree(ped_map[chave_sol])
                    if df_ped_atual is not None:
                        df_atual = df_atual.merge(df_ped_atual, on='Level', how='left')
                        df_atual['ID_Original'] = df_atual['ID_Original'].fillna(df_atual['Level'])
                else:
                    df_atual['ID_Original'] = df_atual['Level']
                    
                dfs_to_concat.append(df_atual)
                
            progresso_atual += passo_progresso
            progress_bar.progress(int(progresso_atual))
        
        # 4. Concatenar e Agregar
        if dfs_to_concat:
            df_combined = pd.concat(dfs_to_concat, ignore_index=True)
            agg_dict = {'Valor': 'sum'}
            if 'Erro_Padrao' in df_combined.columns:
                agg_dict['Erro_Padrao'] = 'mean'
                
            df_deps = df_combined.groupby(['Trait', 'Effect', 'ID_Original'], as_index=False).agg(agg_dict)
            df_deps['Level'] = df_deps['ID_Original']
            df_deps['EBV'] = df_deps['Valor']
            df_deps['DEP'] = df_deps['EBV'] / 2
            
        progress_bar.progress(100)
        status_text.success(f"✅ Processamento concluído em {datetime.now().strftime('%H:%M:%S')}")

    # --- RENDERIZAÇÃO DAS ABAS ---
    if df_deps is not None and not df_deps.empty:
        
        pesos_dict = {}
        nomes_dict = {}
        efeitos_dict = {}
        
        # Leitura do Mapa Bioeconômico
        if mapa_bio is not None:
            try:
                mapa_bio.seek(0)
                df_mapa = pd.read_csv(mapa_bio, sep=';')
                for _, row in df_mapa.iterrows():
                    trait_num = str(row['Ordem_Geral']).replace('Trait_', '')
                    nome_trait = str(row['Nome_Trait'])
                    pesos_dict[nome_trait] = float(row['Valor_Economico'])
                    nomes_dict[trait_num] = nome_trait
            except Exception as e:
                st.error(f"Erro ao ler o mapa_bioeconomico.csv: {e}")

        # Leitura do Mapa de Efeitos
        if mapa_efeitos_io is not None:
            try:
                mapa_efeitos_io.seek(0)
                df_mapa_ef = pd.read_csv(mapa_efeitos_io, sep=';')
                for _, row in df_mapa_ef.iterrows():
                    efeitos_dict[str(row['Ordem_Efeito'])] = str(row['Nome_Efeito'])
            except Exception as e:
                st.error(f"Erro ao ler o mapa_efeitos.csv: {e}")

        # =========================================================================
        # TRADUÇÃO DE TERMINOLOGIA (ENGENHARIA DE SOFTWARE -> NEGÓCIO)
        # =========================================================================
        df_deps['Trait'] = df_deps['Trait'].apply(lambda x: nomes_dict.get(str(x), f"Trait_{x}"))
        df_deps['Effect'] = df_deps['Effect'].apply(lambda x: efeitos_dict.get(str(x), f"Effect_{x}"))
        
        # Renomeando as colunas críticas para termos compreensíveis pelo usuário
        df_deps.rename(columns={
            'Trait': 'Característica',
            'Effect': 'Fator de Análise (Efeito)',
            'ID_Original': 'Identificação (Brinco/RGN)',
            'Level': 'Cód. Interno (BLUP)'
        }, inplace=True)

        aba1, aba2 = st.tabs(["1 - Resumo Global e Valor Bioeconômico", "2 - Filtros de Análise Genética"])

        with aba1:
            st.subheader("💰 Cálculo do Valor Bioeconômico (R$)")
            
            # --- EXPANDER EXPLICATIVO (ABA 1) ---
            with st.expander("📚 Análise Detalhada: Entendendo os Fatores de Análise e o Índice Bioeconômico"):
                st.markdown("""
                ### Como o sistema lê o seu rebanho?
                Para ranquear os animais com precisão, o motor matemático (BLUP) quebra o desempenho de cada bovino em duas partes fundamentais: **Genética** e **Ambiente**. No sistema, chamamos essas partes de **Fatores de Análise (Effects)**.

                * **Fatores Ambientais (ex: GC, Fazenda, Época de Nascimento):** Quando você seleciona um Grupo Contemporâneo (GC) no filtro, o sistema isola a "ajuda" ou o "desafio" que aquele pasto ou manejo específico ofereceu. Isso permite comparar se a Fazenda A deu melhores condições que a Fazenda B, independentemente dos animais que estavam lá.
                * **Fator Animal (ex: ID_Animal):** Ao selecionar o animal, o sistema "limpa" todo o ruído do ambiente. O número que sobra (a DEP) é a prova do verdadeiro mérito genético daquele reprodutor. Ele mostra o que o animal realmente vai transmitir para os bezerros, mesmo se for levado para um pasto de qualidade inferior.

                ### O Valor Bioeconômico
                A Tabela de Elite não mostra apenas quem é mais pesado, mas quem dá mais **lucro**. O sistema pega a DEP limpa de cada característica e multiplica pelo valor em Reais (R$) que ela impacta no ciclo de produção. A soma de tudo resulta no **Índice Financeiro**, garantindo que você selecione touros e matrizes que otimizam as margens da sua operação comercial.
                """)

            # ORDENAÇÃO E SELEÇÃO DE EFEITOS 
            efeitos_disponiveis = list(df_deps['Fator de Análise (Efeito)'].unique())
            
            idx_animal_padrao = efeitos_disponiveis.index("ID_Animal") if "ID_Animal" in efeitos_disponiveis else len(efeitos_disponiveis)-1
            
            efeito_animal_sel = st.selectbox(
                "Selecione o Fator de Análise (Qual grupo ou animal você quer avaliar?):", 
                efeitos_disponiveis, 
                index=idx_animal_padrao,
                help="Selecione o Identificador do Animal para ranquear o mérito genético (DEPs). Selecione Grupos (como Lote ou GC) para avaliar o impacto do manejo e do ambiente."
            )
            
            df_animal = df_deps[df_deps['Fator de Análise (Efeito)'] == str(efeito_animal_sel)]
            traits_disponiveis = df_animal['Característica'].unique() 
            
            # Pivotagem adaptada para os novos nomes de coluna
            df_pivot = df_animal.pivot_table(
                index=['Identificação (Brinco/RGN)', 'Cód. Interno (BLUP)'], 
                columns='Característica', 
                values='DEP', 
                aggfunc='sum'
            ).reset_index()
            
            novas_colunas = []
            for col in df_pivot.columns:
                if col in ['Identificação (Brinco/RGN)', 'Cód. Interno (BLUP)']:
                    novas_colunas.append(col)
                else:
                    novas_colunas.append(f"DEP_{col}")
            df_pivot.columns = novas_colunas
            
            # Cálculo do Índice
            df_pivot['Valor_Bioeconomico'] = 0.0
            for trait in traits_disponiveis:
                col_name = f"DEP_{trait}"
                peso = pesos_dict.get(trait, 0.0)
                if col_name in df_pivot.columns:
                    df_pivot['Valor_Bioeconomico'] += df_pivot[col_name] * peso
            
            df_pivot = df_pivot.sort_values(by='Valor_Bioeconomico', ascending=False).reset_index(drop=True)
            
            st.divider()
            st.subheader("🏆 Tabela de Elite (Ranking Bioeconômico)")
            st.dataframe(df_pivot.style.format({'Valor_Bioeconomico': 'R$ {:.2f}'}), use_container_width=True)
            
            st.subheader("📈 Top 20 Animais de Maior Valor Bioeconômico Agregado")
            
            df_plot = df_pivot[df_pivot['Valor_Bioeconomico'] != 0].head(20).copy()
            df_plot['Identificação (Brinco/RGN)'] = df_plot['Identificação (Brinco/RGN)'].astype(str)
            
            fig_top = px.bar(
                df_plot, 
                x='Identificação (Brinco/RGN)', 
                y='Valor_Bioeconomico',
                labels={'Identificação (Brinco/RGN)': 'Identificação do Animal', 'Valor_Bioeconomico': 'Índice (R$)'},
                color='Valor_Bioeconomico', 
                color_continuous_scale='Viridis', 
                text_auto='.2f'
            )
            
            fig_top.update_layout(
                xaxis={
                    'type': 'category', 
                    'categoryorder': 'total ascending'
                }
            )
            st.plotly_chart(fig_top, use_container_width=True)

        with aba2:
            st.subheader("🔍 Filtros de Características Isoladas")
            
            # --- EXPANDER EXPLICATIVO (ABA 2) ---
            with st.expander("📚 Análise Detalhada: Relacionando Características e Fatores"):
                st.markdown("""
                ### Isolando as Variáveis Biológicas
                Enquanto a **Aba 1** consolida tudo em um único índice monetário (ideal para a seleção comercial e lucro líquido), esta **Aba 2** é sua ferramenta de **correção de rebanho**.

                * **Característica (Trait):** São as medições biológicas puras inseridas no modelo (ex: Peso à Desmama, Perímetro Escrotal, Probabilidade de Parto Precoce). 
                * **Cruzamento de Dados:** 1.  Se o seu rebanho apresenta um problema estrutural (ex: animais leves na desmama), você seleciona a *Característica* correspondente e filtra pelo *Fator* "Animal". A tabela mostrará apenas os touros que resolvem esse defeito genético específico (maior DEP para Peso).
                    2.  Se você quiser auditar a qualidade da nutrição de um lote, filtre a mesma *Característica* pelo *Fator* "Grupo Contemporâneo". O sistema deixará de ranquear animais e passará a mostrar quais lotes tiveram o melhor desempenho ambiental (maior solução bruta de ambiente) naquela safra.
                """)

            c1, c2 = st.columns(2)
            with c1:
                efeito_sel = st.selectbox(
                    "Filtrar por Fator de Análise (Efeito):", 
                    efeitos_disponiveis, 
                    index=idx_animal_padrao,
                    key="f_ef"
                )
            with c2:
                trait_sel = st.selectbox(
                    "Filtrar por Característica Avaliada:", 
                    df_deps['Característica'].unique(), 
                    key="f_tr"
                )
            
            df_filtro = df_deps[(df_deps['Fator de Análise (Efeito)'] == str(efeito_sel)) & (df_deps['Característica'] == str(trait_sel))]
            df_top_isolado = df_filtro.sort_values(by='DEP', ascending=False)
            
            st.markdown(f"**Top Resultados Isolados para a Característica: {trait_sel}**")
            st.dataframe(df_top_isolado.head(50), use_container_width=True)
            
            # ==========================================
            # ZONA DE DOWNLOADS (CSV E PDF)
            # ==========================================
            st.divider()
            col_d1, col_d2 = st.columns(2)
            
            with col_d1:
                st.download_button(
                    label="💾 Baixar Tabela de Elite Completa (CSV)",
                    data=df_pivot.to_csv(index=False).encode('utf-8'),
                    file_name=f"Elite_Bioeconomica_{datetime.now().strftime('%d%m%Y')}.csv",
                    mime="text/csv", 
                    use_container_width=True
                )
                
            with col_d2:
                try:
                    # Gera o PDF dinamicamente com os dados das duas abas
                    pdf_path = gerar_relatorio_pdf(df_pivot, df_top_isolado, trait_sel)
                    with open(pdf_path, "rb") as pdf_file:
                        PDFbyte = pdf_file.read()

                    st.download_button(
                        label="📄 Baixar Relatório Resumo (PDF)",
                        data=PDFbyte,
                        file_name=f"Relatorio_Avaliacao_{datetime.now().strftime('%d%m%Y')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                except Exception as e:
                    st.warning("Para gerar o relatório PDF, certifique-se de instalar a biblioteca FPDF (`pip install fpdf`).")

if __name__ == '__main__':
    render_dashboard_module()