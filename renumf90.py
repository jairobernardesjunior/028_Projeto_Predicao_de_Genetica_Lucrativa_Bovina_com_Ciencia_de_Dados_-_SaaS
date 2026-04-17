import streamlit as st
import pandas as pd
import subprocess
import os
import tempfile
import platform
import zipfile
import io
import re
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import unicodedata

# Requisito de instalação: pip install fpdf
try:
    from fpdf import FPDF
except ImportError:
    st.error("⚠️ A biblioteca FPDF não foi encontrada. Rode no terminal: pip install fpdf")

# --- HELPERS (Robustez e Formatação) ---
def limpar_texto(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    return u"".join([c for c in nfkd if not unicodedata.combining(c)])

def ler_csv_seguro(file_obj):
    """ Lê CSVs de forma resiliente contra problemas de encoding clássicos do Windows """
    if isinstance(file_obj, str):
        try:
            return pd.read_csv(file_obj, sep=";", encoding='utf-8')
        except UnicodeDecodeError:
            return pd.read_csv(file_obj, sep=";", encoding='latin-1')
    else:
        file_obj.seek(0)
        try:
            return pd.read_csv(file_obj, sep=";", encoding='utf-8')
        except UnicodeDecodeError:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep=";", encoding='latin-1')

def analisar_variaveis(df, traits, limiar_cat=5):
    """ Identifica quais traits são contínuas (Lineares) e quais são discretas (Categóricas/Limiar) """
    lineares = []
    categoricas = {}
    for trait in traits:
        if trait in df.columns:
            n_unique = df[trait].dropna().nunique()
            # Se tiver até 5 valores únicos (ex: 0 e 1, ou notas 1 a 4), trata como categórica
            if n_unique <= limiar_cat:
                categoricas[trait] = n_unique
            else:
                lineares.append(trait)
    return lineares, categoricas

def render_renumf90_module():

    # --- Estilização ---
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem !important; }
        .info-box { background-color: #e8f8f5; border-left: 5px solid #1abc9c; padding: 15px; margin-bottom: 20px; border-radius: 4px; font-size: 14px; color: #2c3e50; }
        .edu-text { font-size: 13px; color: #7f8c8d; margin-top: -10px; margin-bottom: 10px; }
        .highlight-red { color: #e74c3c; font-weight: bold; }
        .highlight-green { color: #27ae60; font-weight: bold; }
        .glossary-term { font-weight: bold; color: #2980b9; }
        .glossary-cat { color: #2c3e50; font-size: 16px; margin-top: 15px; margin-bottom: 5px; border-bottom: 2px solid #bdc3c7;}
        .metric-card { background-color: #f8f9fa; border-radius: 8px; padding: 15px; border-left: 4px solid #3498db; box-shadow: 0 2px 4px rgba(0,0,0,0.05); height: 100%; }
        .alert-cg { color: #e67e22; font-size: 13px; font-weight: 500;}
        </style>
        """, 
        unsafe_allow_html=True
    )

    st.title("📁 Fase 1: Recodificação e Preparação (RENUMF90)")
    
    st.markdown("""
    <div class="info-box">
        <strong>📚 O que faz esta etapa? (Entenda de forma simples)</strong><br>
        Softwares matemáticos avançados de avaliação genética (como o BLUPF90) não conseguem ler nomes ou códigos de animais com letras (Ex: "NEL1234"). 
        O RENUMF90 é o nosso <b>tradutor oficial</b>. Ele pega todo o seu rebanho e transforma o ID de cada animal em um número sequencial contínuo. 
        Além disso, ele cruza as informações de parentesco com os pesos e <b>descarta automaticamente</b> animais que não têm conexão útil com o rebanho.
    </div>
    """, unsafe_allow_html=True)

    if 'dados_renum_out' not in st.session_state:
        st.session_state.dados_renum_out = None

    # ==========================================
    # 1. ÁREA DE UPLOAD DE DADOS (COM WORKSPACE)
    # ==========================================
    st.subheader("📂 1. Upload dos Arquivos Base (.csv)")
    st.info("Carregue as planilhas tratadas e, opcionalmente, a tabela de Pesos Econômicos para rastreio do índice.")
    
    workspace_dir = st.session_state.get('workspace_dir')
    caminho_fen_auto = os.path.join(workspace_dir, "fenotipos_tratados.csv") if workspace_dir else None
    caminho_ped_auto = os.path.join(workspace_dir, "pedigree_qc_final.csv") if workspace_dir else None
    caminho_gen_auto = os.path.join(workspace_dir, "genotipos_qc_final.csv") if workspace_dir else None
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        if caminho_fen_auto and os.path.exists(caminho_fen_auto):
            st.success("📁 **'fenotipos_tratados.csv'** (Auto)")
            f_fen_up = st.file_uploader("Opcional: Trocar Fenótipos", type="csv", key="renum_fen")
            f_fen = f_fen_up if f_fen_up is not None else caminho_fen_auto
        else:
            f_fen = st.file_uploader("Fenótipos (.csv)", type="csv", key="renum_fen")
            
    with c2:
        if caminho_ped_auto and os.path.exists(caminho_ped_auto):
            st.success("📁 **'pedigree_qc_final.csv'** (Auto)")
            f_ped_up = st.file_uploader("Opcional: Trocar Pedigree", type="csv", key="renum_ped")
            f_ped = f_ped_up if f_ped_up is not None else caminho_ped_auto
        else:
            f_ped = st.file_uploader("Pedigree (.csv)", type="csv", key="renum_ped")
            
    with c3:
        if caminho_gen_auto and os.path.exists(caminho_gen_auto):
            st.success("📁 **'genotipos_qc_final.csv'** (Auto)")
            f_gen_up = st.file_uploader("Opcional: Trocar Genótipos", type="csv", key="renum_gen")
            f_gen = f_gen_up if f_gen_up is not None else caminho_gen_auto
        else:
            f_gen = st.file_uploader("Genótipos (.csv)", type="csv", key="renum_gen")
            
    with c4:
        f_pesos = st.file_uploader("Pesos Econ. (.csv)", type="csv", key="renum_pesos", help="Arquivo pesos_economicos.csv para cruzar com as DEPs.")

    if f_fen and f_ped:
        try:
            df_fen_preview = ler_csv_seguro(f_fen)
            colunas_fen = df_fen_preview.columns.tolist()
            
            # ==========================================
            # 2. CONFIGURAÇÃO DINÂMICA DO MODELO
            # ==========================================
            st.divider()
            st.subheader("⚙️ 2. Configuração do Modelo Biológico")
            st.markdown("O sistema detectou automaticamente as variáveis válidas. Você pode excluir as que não deseja avaliar clicando no 'x'.")
            
            # Variáveis categorizadas estritamente conforme as regras Lineares/Categóricas
            traits_conhecidas = ['pn_kg', 'pd_kg', 'ps_kg', 'gpd_g-dia', 'pe_cm', 'aol_cm2', 'egs_mm', 'mar_%', 'car_kg-dia', 'prec_sex', 'ipp_dias', 'prob_3p_%', 'stay_%']
            fixos_conhecidos = ['gc', 'fazenda', 'estacao', 'lote_manejo', 'regime_alim', 'tipo_pastagem', 'localidade_bloco', 'piquete', 'sexo', 'geracao', 'raca']
            cov_conhecidas = ['itu_media', 'itu_dp', 'itu_max', 'itu_min', 'itu_leituras_criticas']
            
            traits_sugeridas = [c for c in colunas_fen if c.lower() in traits_conhecidas]
            efeitos_sugeridos = [c for c in colunas_fen if c.lower() in fixos_conhecidos]
            cov_sugeridas = [c for c in colunas_fen if c.lower() in cov_conhecidas]

            if "cb_traits" not in st.session_state:
                st.session_state.cb_traits = traits_sugeridas
            if "cb_fixos" not in st.session_state:
                st.session_state.cb_fixos = efeitos_sugeridos
            if "cb_cov" not in st.session_state:
                st.session_state.cb_cov = cov_sugeridas

            def reset_box(chave_estado, valores_originais):
                st.session_state[chave_estado] = valores_originais

            col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
            
            with col_cfg1:
                st.markdown("**🎯 Características (Traits)**")
                traits_selecionadas = st.multiselect("Selecione as características de interesse:", options=traits_sugeridas, key="cb_traits")
                st.button("↺ Restaurar Originais", on_click=reset_box, args=("cb_traits", traits_sugeridas), key="btn_rst_t")
                st.markdown("<p class='edu-text'>O que você quer melhorar no rebanho?</p>", unsafe_allow_html=True)
            
            with col_cfg2:
                st.markdown("**🛡️ Efeitos Fixos (Crossclassified)**")
                efeitos_selecionados = st.multiselect("Selecione os grupos de manejo/ambiente:", options=efeitos_sugeridos, key="cb_fixos")
                st.button("↺ Restaurar Originais", on_click=reset_box, args=("cb_fixos", efeitos_sugeridos), key="btn_rst_f")
                st.markdown("<p class='edu-text'>Condições ambientais/categóricas para comparação justa.</p>", unsafe_allow_html=True)
            
            with col_cfg3:
                st.markdown("**📏 Covariáveis (Lineares)**")
                cov_selecionadas = st.multiselect("Selecione as covariáveis contínuas:", options=cov_sugeridas, key="cb_cov")
                st.button("↺ Restaurar Originais", on_click=reset_box, args=("cb_cov", cov_sugeridas), key="btn_rst_c")
                st.markdown("<p class='edu-text'>Fatores contínuos que afetam o desempenho (regressão).</p>", unsafe_allow_html=True)

            with st.expander("📖 Não sabe o que excluir? Clique aqui e veja o Glossário Explicativo das Suas Variáveis"):
                st.markdown("""
                ### Entenda onde cada variável se encaixa no seu modelo matemático:
                
                <h4 class="glossary-cat">🎯 1. Características (Traits)</h4>
                <i>São as medidas reais de desempenho. É o que você quer melhorar geneticamente. O sistema detecta sozinho e separa em duas rotas:</i><br>
                <b>🔹 Rotas Lineares (Variáveis Contínuas):</b><br>
                * **EGS_mm / MAR_%:** Medidas de carcaça via ultrassom (Espessura de Gordura e Marmoreio). Possuem dezenas de valores decimais contínuos.<br>
                * **CAR_kg-dia:** Consumo Alimentar Residual. É o quanto o animal come a mais ou a menos do que o esperado (eficiência alimentar contínua).<br>
                * **PROB_3P_%:** Indicador reprodutivo contínuo de probabilidade.<br>
                <b>🔸 Rotas Categóricas (Escores / Limiar - Threshold):</b><br>
                * **PN_kg / PD_kg / PS_kg / GPD_g-dia:** Nesta base de dados, os pesos e os ganhos foram convertidos em "notas" ou "escores" (ex: notas de 1 a 4).<br>
                * **PE_cm / AOL_cm2:** Perímetro Escrotal e Área de Olho de Lombo também foram agrupados em classes (notas de 1 a 4).<br>
                * **PREC_SEX / STAY_%:** Variáveis reprodutivas binárias. O animal emprenhou precocemente ou não? (0 ou 1). Ficou no rebanho ou não? (0 ou 1).

                <h4 class="glossary-cat">🛡️ 2. Efeitos Fixos (Grupos Contemporâneos e Fatores - Crossclassified)</h4>
                <i>São as "gavetas" de classificação estritamente categóricas. Elas informam ao Fortran quais animais competiram de forma justa no mesmo ambiente.</i><br>
                * **GC (Grupo Contemporâneo):** Código principal que agrupa os animais que tiveram o mesmo tratamento.<br>
                * **Fazenda / Estação / Lote_Manejo / Localidade_Bloco / Piquete:** Divisões físicas, climáticas e temporais do ambiente.<br>
                * **Regime_Alim / Tipo_Pastagem:** Grupos nutricionais que os animais receberam.<br>
                * **Sexo / Geração / Raça:** Fatores biológicos de agrupamento. A "Raça" entra aqui pois na sua planilha ela está estruturada como um rótulo/categoria e não como porcentagem contínua.

                <h4 class="glossary-cat">📏 3. Covariáveis (Efeitos Ambientais Lineares)</h4>
                <i>São números estritamente contínuos que criam uma "régua de desconto" (regressão) sobre o desempenho do animal.</i><br>
                * **ITU (media, dp, max, min, leituras_criticas):** Índices de Temperatura e Umidade. A matemática usa essas variáveis contínuas para criar uma linha de desconto que pune menos os animais que sofreram maior estresse térmico, ajustando o mérito genético de forma justa.
                """, unsafe_allow_html=True)

            missing_val = -999

            # ==========================================
            # 3. ÁREA DO EXECUTÁVEL E DLLs
            # ==========================================
            st.divider()
            st.subheader("🚀 3. Motor Fortran (RENUMF90)")
            
            col_exe, col_dll = st.columns(2)
            with col_exe:
                f_exe = st.file_uploader("Executável (renumf90.exe)", key="renum_exe")
                
            with col_dll:
                f_dlls = st.file_uploader(
                    "DLLs de Suporte (Segure Ctrl para selecionar várias)", 
                    accept_multiple_files=True, 
                    key="renum_dlls"
                )

            # ==========================================
            # 4. EXECUÇÃO BIFURCADA E EXTRAÇÃO DE MÉTRICAS
            # ==========================================
            if st.button("🔄 Rodar RENUMF90 e Gerar Arquivos", type="primary", use_container_width=True):
                if not traits_selecionadas:
                    st.error("⚠️ Selecione pelo menos uma Característica (Trait).")
                elif 'ID_Animal' not in colunas_fen:
                    st.error("⚠️ A coluna 'ID_Animal' não foi encontrada nos fenótipos!")
                elif not f_exe:
                    st.error("⚠️ Faça o upload do executável renumf90.exe.")
                else:
                    inicio_processo = datetime.now()
                    str_inicio = inicio_processo.strftime('%d/%m/%Y às %H:%M:%S')
                    
                    status_container = st.empty()
                    status_container.info(f"⏳ **Início da Execução:** {str_inicio}")

                    progress_bar = st.progress(0)
                    progress_text = st.empty()
                    registros_excluidos = []

                    try:
                        # Etapa 1: Leitura Robusta
                        progress_text.text("Etapa 1/5: Lendo arquivos CSV com Encoding Dinâmico...")
                        progress_bar.progress(10)
                        
                        df_fen = ler_csv_seguro(f_fen)
                        df_ped = ler_csv_seguro(f_ped)
                        qtd_fen_original = len(df_fen)
                        qtd_ped_original = len(df_ped)

                        # --- ROTEAMENTO ESTATÍSTICO ---
                        traits_lineares, traits_categoricas = analisar_variaveis(df_fen, traits_selecionadas)
                        
                        st.write("### 📊 Diagnóstico do Roteador Estatístico")
                        if traits_lineares:
                            st.info(f"**Rota A (Linear/REML):** {', '.join(traits_lineares)}")
                        if traits_categoricas:
                            st.warning(f"**Rota B (Limiar/Bayesiano):** {', '.join(traits_categoricas.keys())}")

                        # --- CRUZAMENTO BIOECONÔMICO ---
                        df_mapa_pesos = None
                        if f_pesos:
                            try:
                                df_p = ler_csv_seguro(f_pesos)
                                if all(col in df_p.columns for col in ['id_peso', 'nome_peso', 'valor_estimado']):
                                    mapa_data = []
                                    for idx, trait in enumerate(traits_selecionadas, start=1):
                                        match = df_p[df_p['nome_peso'] == trait]
                                        if not match.empty:
                                            id_p = match.iloc[0]['id_peso']
                                            valor_est = match.iloc[0]['valor_estimado']
                                        else:
                                            id_p = "N/A"
                                            valor_est = 0.0
                                        mapa_data.append({"Ordem_Geral": f"Trait_{idx}", "Nome_Trait": trait, "ID_Peso": id_p, "Valor_Economico": valor_est})
                                    df_mapa_pesos = pd.DataFrame(mapa_data)
                            except Exception as e:
                                st.warning(f"Aviso: Falha ao cruzar pesos_economicos.csv - {e}")

                        # --- MAPEAMENTO DE EFEITOS (BLUPF90) ---
                        mapa_efeitos_data = []
                        contador_efeito = 1
                        
                        for ef in efeitos_selecionados:
                            mapa_efeitos_data.append({"Ordem_Efeito": contador_efeito, "Nome_Efeito": ef, "Tipo_Efeito": "Fixo_Crossclassified"})
                            contador_efeito += 1
                            
                        for cov in cov_selecionadas:
                            mapa_efeitos_data.append({"Ordem_Efeito": contador_efeito, "Nome_Efeito": cov, "Tipo_Efeito": "Covariavel_Linear"})
                            contador_efeito += 1
                            
                        # O animal é sempre o último efeito aleatório inserido no .par
                        mapa_efeitos_data.append({"Ordem_Efeito": contador_efeito, "Nome_Efeito": "ID_Animal", "Tipo_Efeito": "Animal_Random"})
                        
                        df_mapa_efeitos = pd.DataFrame(mapa_efeitos_data)

                        # Etapa 2: Auditoria e Limpeza
                        progress_text.text("Etapa 2/5: Auditoria de Dados e Blindagem contra Crash...")
                        progress_bar.progress(30)
                        
                        for col in traits_selecionadas + cov_selecionadas:
                            df_fen[col] = pd.to_numeric(df_fen[col], errors='coerce')
                            
                        mask_sem_id = df_fen['ID_Animal'].isna() | (df_fen['ID_Animal'].astype(str).str.strip() == '')
                        if mask_sem_id.any():
                            for _, row in df_fen[mask_sem_id].iterrows():
                                registros_excluidos.append({"ID_Animal": "EM BRANCO", "Local / Fazenda": row.get('Fazenda', 'N/A'), "Causa da Exclusão": "ID_Animal vazio", "Explicação Simples": "Desempenho sem identificação."})
                            df_fen = df_fen[~mask_sem_id]
                            
                        fen_clean = df_fen.fillna(missing_val)
                        
                        if {'ID_Animal', 'ID_Pai', 'ID_Mae'}.issubset(df_ped.columns):
                            df_ped['ID_Animal'] = df_ped['ID_Animal'].astype(str).str.strip()
                            df_ped['ID_Pai'] = df_ped['ID_Pai'].astype(str).str.strip()
                            df_ped['ID_Mae'] = df_ped['ID_Mae'].astype(str).str.strip()
                            
                            mask_auto_pai = (df_ped['ID_Animal'] == df_ped['ID_Pai']) & (df_ped['ID_Pai'] != '0') & (df_ped['ID_Pai'] != 'nan')
                            mask_auto_mae = (df_ped['ID_Animal'] == df_ped['ID_Mae']) & (df_ped['ID_Mae'] != '0') & (df_ped['ID_Mae'] != 'nan')
                            mask_auto = mask_auto_pai | mask_auto_mae
                            
                            if mask_auto.any():
                                for _, row in df_ped[mask_auto].iterrows():
                                    registros_excluidos.append({"ID_Animal": row['ID_Animal'], "Local / Fazenda": "Pedigree", "Causa da Exclusão": "Auto-parentesco", "Explicação Simples": "Animal não pode ser pai dele mesmo."})
                                df_ped = df_ped[~mask_auto]
                                
                            ped_clean = df_ped[['ID_Animal', 'ID_Pai', 'ID_Mae']].fillna(0)
                        else:
                            ped_clean = df_ped.iloc[:, 0:3].fillna(0)

                        def to_fortran_text(df):
                            return df.to_csv(sep=' ', header=False, index=False, lineterminator='\n').encode('utf-8')

                        # Etapa 3: Disco e Genômica
                        progress_text.text("Etapa 3/5: Rastreio Genômico e Configuração de Arquivos...")
                        progress_bar.progress(50)
                        
                        metricas_genomica = None
                        res_files = {}
                        logs_processamento = ""
                        alertas_fortran = []
                        
                        with tempfile.TemporaryDirectory() as tmpdir:
                            tmpdir_norm = os.path.normpath(tmpdir)
                            
                            # Gravação dos arquivos raw e mapas de referência
                            with open(os.path.join(tmpdir_norm, "fenotipos_raw.txt"), "wb") as f: f.write(to_fortran_text(fen_clean))
                            with open(os.path.join(tmpdir_norm, "pedigree_raw.txt"), "wb") as f: f.write(to_fortran_text(ped_clean))
                            
                            if df_mapa_pesos is not None:
                                mapa_csv = df_mapa_pesos.to_csv(sep=';', index=False).encode('utf-8')
                                with open(os.path.join(tmpdir_norm, "mapa_bioeconomico.csv"), "wb") as f: f.write(mapa_csv)

                            if df_mapa_efeitos is not None and not df_mapa_efeitos.empty:
                                mapa_ef_csv = df_mapa_efeitos.to_csv(sep=';', index=False).encode('utf-8')
                                with open(os.path.join(tmpdir_norm, "mapa_efeitos.csv"), "wb") as f: f.write(mapa_ef_csv)

                            snp_block = ""
                            if f_gen:
                                df_gen = ler_csv_seguro(f_gen).astype(str)
                                col_id = df_gen.columns[0]
                                duplicatas = df_gen[df_gen.duplicated(subset=[col_id], keep='first')]
                                if not duplicatas.empty:
                                    for _, row in duplicatas.iterrows():
                                        registros_excluidos.append({"ID_Animal": row.iloc[0], "Local / Fazenda": "Laboratório DNA", "Causa da Exclusão": "Genótipo Duplicado", "Explicação Simples": "Cópia removida para não corromper G."})
                                
                                df_gen_clean = df_gen.drop_duplicates(subset=[col_id], keep='first')
                                
                                ids_produtivos = set(df_fen['ID_Animal'].astype(str)).union(set(df_ped['ID_Animal'].astype(str)))
                                ids_genotipados = set(df_gen_clean[col_id].str.strip())
                                genotipos_uteis = ids_genotipados.intersection(ids_produtivos)
                                taxa_util = (len(genotipos_uteis) / len(ids_genotipados) * 100) if ids_genotipados else 0
                                metricas_genomica = {"total_gen": len(ids_genotipados), "inuteis_gen": len(ids_genotipados) - len(genotipos_uteis), "taxa": taxa_util}

                                max_id_len = max(df_gen_clean[col_id].str.strip().str.len().max(), 20)
                                gen_text = "".join([f"{str(row.iloc[0]).strip().rjust(max_id_len)} {str(row.iloc[1]).strip()}\n" for _, row in df_gen_clean.iterrows()])
                                with open(os.path.join(tmpdir_norm, "genotipos_raw.txt"), "w", encoding='utf-8', newline='\n') as f: f.write(gen_text)
                                snp_block = "SNP_FILE\ngenotipos_raw.txt\n"
                            
                            exe_filename = f_exe.name.strip()
                            exe_path = os.path.join(tmpdir_norm, exe_filename)
                            with open(exe_path, "wb") as f: f.write(f_exe.getbuffer())
                            if platform.system() != "Windows": os.chmod(exe_path, 0o755)
                                
                            if f_dlls:
                                for dll in f_dlls:
                                    with open(os.path.normpath(os.path.join(tmpdir_norm, dll.name.strip())), "wb") as f: f.write(dll.getbuffer())

                            cmd_exe = f".\\{exe_filename}" if platform.system() == "Windows" else f"./{exe_filename}"

                            # Lista de arquivos para ignorar ao renomear saídas
                            exclude_list = ["fenotipos_raw.txt", "pedigree_raw.txt", "genotipos_raw.txt", "mapa_bioeconomico.csv", "mapa_efeitos.csv", exe_filename]
                            if f_dlls: exclude_list.extend([d.name.strip() for d in f_dlls])

                            # Função auxiliar de criação do .PAR
                            def gerar_conteudo_par(traits_subset, is_categ=False):
                                num_traits = len(traits_subset)
                                traits_idx = [str(colunas_fen.index(t) + 1) for t in traits_subset]
                                matriz_residual = "\n".join([" ".join(["1.0" if i==j else "0.0" for j in range(num_traits)]) for i in range(num_traits)])
                                
                                efeitos_str = "".join([f"EFFECT\n{' '.join([str(colunas_fen.index(ef) + 1)] * num_traits)} cross alpha     # Fixo: {ef}\n" for ef in efeitos_selecionados])
                                cov_str = "".join([f"EFFECT\n{' '.join([str(colunas_fen.index(cov) + 1)] * num_traits)} cov             # Cov: {cov}\n" for cov in cov_selecionadas])
                                idx_animal_str = " ".join([str(colunas_fen.index('ID_Animal') + 1)] * num_traits)
                                efeito_animal_str = f"EFFECT\n{idx_animal_str} cross alpha     # Animal\nRANDOM\nanimal\n"

                                instrucoes = f"DATAFILE\nfenotipos_raw.txt\nTRAITS\n{' '.join(traits_idx)}\n"
                                instrucoes += f"RESIDUAL_VARIANCE\n{matriz_residual}\n{efeitos_str}{cov_str}{efeito_animal_str}FILE\npedigree_raw.txt\n{snp_block}OPTION missing {missing_val}\n"
                                
                                if is_categ:
                                    for idx, trait in enumerate(traits_subset):
                                        num_classes = traits_categoricas.get(trait)
                                        if num_classes:
                                            instrucoes += f"OPTION categorical {idx + 1} {num_classes}\n"
                                return instrucoes

                            progress_text.text("Etapa 4/5: Orquestrando Pipelines do RENUMF90 (Linear e Limiar)...")
                            progress_bar.progress(70)

                            # --- ROTA A: PIPELINE LINEAR ---
                            if traits_lineares:
                                par_lin = gerar_conteudo_par(traits_lineares, is_categ=False)
                                with open(os.path.join(tmpdir_norm, "renum_linear.par"), "w", encoding='utf-8', newline='\n') as f: f.write(par_lin)
                                
                                logs_processamento += "\n" + "="*40 + "\n[PIPELINE LINEAR]\n" + "="*40 + "\n"
                                process_lin = subprocess.run([cmd_exe], input="renum_linear.par\n", cwd=tmpdir_norm, capture_output=True, text=True)
                                logs_processamento += process_lin.stdout + "\n" + process_lin.stderr
                                alertas_fortran.extend(re.findall(r'(.*eliminated.*)', process_lin.stdout, re.IGNORECASE))
                                
                                if process_lin.returncode != 0:
                                    raise Exception(f"Falha Crítica no RENUMF90 (Linear):\n{process_lin.stderr}")
                                
                                renf90_par_path = os.path.join(tmpdir_norm, "renf90.par")
                                if os.path.exists(renf90_par_path):
                                    with open(renf90_par_path, "a", encoding='utf-8', newline='\n') as f_par: f_par.write("\nOPTION thrStopCorAG -1\n")
                                
                                for arq in os.listdir(tmpdir_norm):
                                    if arq not in exclude_list and arq != "renum_linear.par" and os.path.isfile(os.path.join(tmpdir_norm, arq)):
                                        novo_nome = arq.replace('renf90', 'renf90_linear').replace('renadd', 'renadd_linear')
                                        if arq == novo_nome: novo_nome = f"{arq}_linear"
                                        os.rename(os.path.join(tmpdir_norm, arq), os.path.join(tmpdir_norm, novo_nome))
                                        with open(os.path.join(tmpdir_norm, novo_nome), "rb") as f: res_files[novo_nome] = f.read()
                                        exclude_list.append(novo_nome) # Ignorar na Rota B

                            # --- ROTA B: PIPELINE CATEGÓRICO ---
                            if traits_categoricas:
                                par_cat = gerar_conteudo_par(list(traits_categoricas.keys()), is_categ=True)
                                with open(os.path.join(tmpdir_norm, "renum_categ.par"), "w", encoding='utf-8', newline='\n') as f: f.write(par_cat)
                                
                                logs_processamento += "\n" + "="*40 + "\n[PIPELINE CATEGÓRICO (LIMIAR)]\n" + "="*40 + "\n"
                                process_cat = subprocess.run([cmd_exe], input="renum_categ.par\n", cwd=tmpdir_norm, capture_output=True, text=True)
                                logs_processamento += process_cat.stdout + "\n" + process_cat.stderr
                                alertas_fortran.extend(re.findall(r'(.*eliminated.*)', process_cat.stdout, re.IGNORECASE))
                                
                                if process_cat.returncode != 0:
                                    raise Exception(f"Falha Crítica no RENUMF90 (Categórico):\n{process_cat.stderr}")
                                
                                renf90_par_path = os.path.join(tmpdir_norm, "renf90.par")
                                if os.path.exists(renf90_par_path):
                                    with open(renf90_par_path, "a", encoding='utf-8', newline='\n') as f_par: f_par.write("\nOPTION thrStopCorAG -1\n")
                                
                                for arq in os.listdir(tmpdir_norm):
                                    if arq not in exclude_list and arq != "renum_categ.par" and os.path.isfile(os.path.join(tmpdir_norm, arq)):
                                        novo_nome = arq.replace('renf90', 'renf90_categ').replace('renadd', 'renadd_categ')
                                        if arq == novo_nome: novo_nome = f"{arq}_categ"
                                        os.rename(os.path.join(tmpdir_norm, arq), os.path.join(tmpdir_norm, novo_nome))
                                        with open(os.path.join(tmpdir_norm, novo_nome), "rb") as f: res_files[novo_nome] = f.read()

                            # Etapa 5: Finalização e Extração de Inteligência
                            progress_text.text("Etapa 5/5: Coletando resultados, inteligência e gerando relatório...")
                            progress_bar.progress(90)

                            fim_processo = datetime.now()
                            str_fim = fim_processo.strftime('%d/%m/%Y às %H:%M:%S')

                            # Contagem de linhas geradas
                            qtd_fen_renum, qtd_ped_renum = 0, 0
                            for fname, fdata in res_files.items():
                                if "renf90" in fname.lower() and fname.lower().endswith(".dat"):
                                    qtd_fen_renum = len(fdata.decode('utf-8', errors='ignore').strip().split('\n'))
                                elif "renadd" in fname.lower() and fname.lower().endswith(".ped"):
                                    qtd_ped_renum = len(fdata.decode('utf-8', errors='ignore').strip().split('\n'))

                            # Extração de Métricas Consanguinidade (pega a última menção no log unificado)
                            metricas_log = {"inb_max": "N/D", "inb_avg": "N/D", "base_animals": "N/D"}
                            match_inb = re.findall(r'Inbreeding.*?max\s*=\s*([0-9.]+).*?avg\s*=\s*([0-9.]+)', logs_processamento, re.IGNORECASE)
                            if match_inb:
                                metricas_log["inb_max"] = f"{float(match_inb[-1][0])*100:.2f}%"
                                metricas_log["inb_avg"] = f"{float(match_inb[-1][1])*100:.3f}%"
                                
                            match_base = re.findall(r'([0-9]+)\s*base\s*animals', logs_processamento, re.IGNORECASE)
                            if match_base: metricas_log["base_animals"] = match_base[-1]

                            alertas_fortran = list(set(alertas_fortran))[:10]

                            desc_traits = ", ".join(traits_selecionadas)
                            desc_fixos = ", ".join(efeitos_selecionados) if efeitos_selecionados else "Nenhum"
                            desc_cov = ", ".join(cov_selecionadas) if cov_selecionadas else "Nenhuma"

                            st.session_state.dados_renum_out = {
                                "log": logs_processamento,
                                "files": res_files,
                                "metricas": {"fen_orig": qtd_fen_original, "fen_renum": qtd_fen_renum, "ped_orig": qtd_ped_original, "ped_renum": qtd_ped_renum},
                                "metricas_log": metricas_log,
                                "metricas_gen": metricas_genomica,
                                "alertas_fortran": alertas_fortran,
                                "config_aplicada": {"traits": desc_traits, "fixos": desc_fixos, "cov": desc_cov, "missing": missing_val},
                                "df_mapa_pesos": df_mapa_pesos,
                                "df_mapa_efeitos": df_mapa_efeitos,
                                "excluidos": pd.DataFrame(registros_excluidos),
                                "inicio": str_inicio, "fim": str_fim
                            }
                            
                            progress_text.text("Concluído!")
                            progress_bar.progress(100)
                            status_container.success(f"✅ **Processamento e Tradução Concluídos!**\n\n🕒 **Início:** {str_inicio} | **Fim:** {str_fim}")

                    except Exception as e:
                        st.error(f"Erro Crítico Controlado: {e}")
                        
        except Exception as e:
            st.error(f"Erro na interface ou leitura de CSV: {e}")

    else:
        st.info("⚠️ Carregue os Fenótipos e o Pedigree para começar as configurações.")

    # ==========================================
    # 5. RESULTADOS, GRÁFICOS E DOWNLOADS PDF
    # ==========================================
    if st.session_state.get('dados_renum_out') is not None:
        res = st.session_state.dados_renum_out
        
        # --- AVALIAÇÃO GRÁFICA EXPLICATIVA ---
        st.divider()
        st.subheader("📈 Funil de Avaliação: Sobrevivência de Dados")
        st.markdown("O gráfico abaixo mostra quantos dados entraram no sistema e quantos realmente servirão para calcular a genética (DEPs).")
        
        col_graf, col_texto = st.columns([2, 1])
        with col_graf:
            fig, ax = plt.subplots(figsize=(8, 6))
            categorias = ['Fenótipos (Pesagens)', 'Pedigree (Genealogia)']
            valores_orig = [res['metricas']['fen_orig'], res['metricas']['ped_orig']]
            valores_renum = [res['metricas']['fen_renum'], res['metricas']['ped_renum']]
            
            x = range(len(categorias))
            width = 0.35
            
            ax.bar([i - width/2 for i in x], valores_orig, width, label='Enviado pela Fazenda (Original)', color='#95a5a6')
            ax.bar([i + width/2 for i in x], valores_renum, width, label='Aproveitado para DEPs (Recodificado)', color='#3498db')
            
            ax.set_ylabel('Quantidade de Animais / Linhas', fontsize=12)
            ax.set_title('Antes e Depois do Filtro RENUMF90', fontsize=14, fontweight='bold')
            ax.set_xticks(x)
            ax.set_xticklabels(categorias, fontsize=12)
            
            max_y = max(valores_orig + valores_renum) if (valores_orig + valores_renum) else 100
            ax.set_ylim(0, max_y * 1.25) 
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=1)
            
            for i, v in enumerate(valores_orig):
                ax.text(i - width/2, v + (max_y*0.02), f"{v:,}", ha='center', fontsize=11)
            for i, v in enumerate(valores_renum):
                ax.text(i + width/2, v + (max_y*0.02), f"{v:,}", ha='center', fontsize=11, fontweight='bold', color='#2980b9')
                
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            fig.tight_layout() 
            st.pyplot(fig)
            
        with col_texto:
            perda_fen = res['metricas']['fen_orig'] - res['metricas']['fen_renum']
            perda_ped = res['metricas']['ped_orig'] - res['metricas']['ped_renum']
            st.markdown(f"**📉 Resumo do Corte:**")
            st.markdown(f"- <span class='highlight-red'>{perda_fen} Pesagens Descartadas</span><br>Motivos: Falta de conexão genéalogica ou grupos estáticos.", unsafe_allow_html=True)
            st.markdown(f"- <span class='highlight-red'>{perda_ped} Animais Removidos</span><br>Motivo: Ancestrais muito antigos que não deixaram produção avaliada.", unsafe_allow_html=True)

            if res.get('metricas_gen'):
                st.markdown(f"- <span class='highlight-red'>{res['metricas_gen']['inuteis_gen']} Genótipos Isolados</span><br>Atenção: Animais genotipados que não possuem peso ou pedigree cadastrado no sistema ({res['metricas_gen']['taxa']:.1f}% de aproveitamento do laboratório).", unsafe_allow_html=True)

        # --- DIAGNÓSTICO E ALERTAS DO FORTRAN ---
        st.divider()
        st.subheader("🩺 Diagnóstico de Saúde Genética e Alertas")
        
        if res.get("alertas_fortran"):
            with st.expander("⚠️ Alertas de Manejo (Extraídos do Log Fortran)", expanded=True):
                st.markdown("O RENUMF90 identificou falhas matemáticas (baixa variação) em alguns grupos contemporâneos (Ex: todos os animais pesaram igual, ou só havia 1 bezerro no grupo).")
                for alerta in res["alertas_fortran"]:
                    st.markdown(f"<span class='alert-cg'>- {alerta.strip()}</span>", unsafe_allow_html=True)
        
        c_diag1, c_diag2, c_diag3 = st.columns(3)
        with c_diag1:
            st.markdown(f"""<div class='metric-card'>
                <h4 style='color:#e74c3c; margin:0;'>{res["metricas_log"]["inb_max"]}</h4>
                <strong>Consanguinidade Máxima</strong><br>
                <small style='color:#7f8c8d;'>O maior grau de parentesco encontrado no cruzamento.</small>
            </div>""", unsafe_allow_html=True)
        with c_diag2:
            st.markdown(f"""<div class='metric-card'>
                <h4 style='color:#f39c12; margin:0;'>{res["metricas_log"]["inb_avg"]}</h4>
                <strong>Média de Consanguinidade</strong><br>
                <small style='color:#7f8c8d;'>A média geral de inbreeding da fazenda avaliada.</small>
            </div>""", unsafe_allow_html=True)
        with c_diag3:
            st.markdown(f"""<div class='metric-card'>
                <h4 style='color:#2980b9; margin:0;'>{res["metricas_log"]["base_animals"]}</h4>
                <strong>Animais Fundadores (Base)</strong><br>
                <small style='color:#7f8c8d;'>Animais no início do pedigree sem pais conhecidos na base.</small>
            </div>""", unsafe_allow_html=True)
            
        # --- TABELAS DE CRUZAMENTO BIOECONÔMICO E MAPA DE EFEITOS ---
        if res.get('df_mapa_pesos') is not None:
            st.divider()
            st.subheader("💰 Mapa de Cruzamento Bioeconômico")
            st.markdown("O sistema vinculou automaticamente a ordem matemática do Fortran aos valores financeiros da sua tabela de pesos.")
            st.dataframe(res['df_mapa_pesos'], use_container_width=True)

        if res.get('df_mapa_efeitos') is not None:
            st.divider()
            st.subheader("🗺️ Mapa de Efeitos (BLUPF90)")
            st.markdown("Relação da ordem dos efeitos gerada pelo RENUMF90, útil para rastrear as soluções (solutions).")
            st.dataframe(res['df_mapa_efeitos'], use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # ==========================================
        # GERAÇÃO DO RELATÓRIO PDF DINÂMICO E ZIP
        # ==========================================
        pdf_bytes = b""
        try:
            pdf = FPDF()
            pdf.add_page()
            
            pdf.set_font("Arial", 'B', 15)
            pdf.cell(0, 10, limpar_texto("RELATÓRIO DE AVALIAÇÃO E PREPARAÇÃO - RENUMF90"), ln=True, align='C')
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 8, limpar_texto(f"Data de Processamento: {res['inicio']} até {res['fim']}"), ln=True, align='C')
            pdf.ln(5)

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, limpar_texto("1. CONFIGURAÇÃO DO MODELO BIOLÓGICO"), ln=True)
            pdf.set_font("Arial", '', 10)
            texto_config = f"Características (Traits): {res['config_aplicada']['traits']}\n"
            texto_config += f"Efeitos Fixos: {res['config_aplicada']['fixos']}\n"
            texto_config += f"Covariáveis: {res['config_aplicada']['cov']}\n"
            pdf.multi_cell(0, 6, limpar_texto(texto_config))
            pdf.ln(5)

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, limpar_texto("2. RETENÇÃO E AUDITORIA DE DADOS"), ln=True)
            pdf.set_font("Arial", '', 10)
            texto_funil = f"FENÓTIPOS: Fornecidos ({res['metricas']['fen_orig']}) -> Aproveitados ({res['metricas']['fen_renum']})\n"
            texto_funil += f"PEDIGREE: Fornecidos ({res['metricas']['ped_orig']}) -> Aproveitados ({res['metricas']['ped_renum']})\n"
            if res.get('metricas_gen'):
                texto_funil += f"GENÔMICA: Total Analisado ({res['metricas_gen']['total_gen']}) -> Isolados/Inúteis ({res['metricas_gen']['inuteis_gen']})\n"
            pdf.multi_cell(0, 6, limpar_texto(texto_funil))
            pdf.ln(2)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                fig.savefig(tmpfile.name, format="png", bbox_inches="tight", dpi=150)
                tmp_img_path = tmpfile.name
            
            pdf.image(tmp_img_path, w=160, x=25)
            pdf.ln(5)

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, limpar_texto("3. SAÚDE GENÉTICA E ALERTAS"), ln=True)
            pdf.set_font("Arial", '', 10)
            texto_saude = f"Consanguinidade Máx: {res['metricas_log']['inb_max']} | Média: {res['metricas_log']['inb_avg']}\n"
            pdf.multi_cell(0, 6, limpar_texto(texto_saude))
            if res.get("alertas_fortran"):
                pdf.set_font("Arial", 'I', 9)
                pdf.multi_cell(0, 5, limpar_texto("Avisos Fortran sobre Grupos Contemporâneos (CG):"))
                for alerta in res["alertas_fortran"][:5]:
                    pdf.multi_cell(0, 5, limpar_texto(f"- {alerta.strip()}"))

            pdf.add_page()
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, limpar_texto("4. LOG TÉCNICO ORIGINAL (MOTOR FORTRAN)"), ln=True)
            pdf.set_font("Courier", '', 7)
            safe_log = res['log'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 4, safe_log)

            pdf_out = pdf.output(dest='S')
            pdf_bytes = pdf_out.encode('latin-1') if isinstance(pdf_out, str) else bytes(pdf_out)
            
            if os.path.exists(tmp_img_path):
                os.remove(tmp_img_path)

        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

        # --- CONSTRUÇÃO DO ZIP UNIFICADO ---
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for fname, fdata in res["files"].items():
                zip_file.writestr(fname, fdata)
            if pdf_bytes:
                zip_file.writestr("Laudo_Processamento_RENUMF90.pdf", pdf_bytes)
            if res.get('df_mapa_pesos') is not None:
                mapa_csv = res['df_mapa_pesos'].to_csv(sep=';', index=False, encoding='utf-8')
                zip_file.writestr("mapa_bioeconomico.csv", mapa_csv)
            if res.get('df_mapa_efeitos') is not None:
                mapa_ef_csv = res['df_mapa_efeitos'].to_csv(sep=';', index=False, encoding='utf-8')
                zip_file.writestr("mapa_efeitos.csv", mapa_ef_csv)
                
        zip_data = zip_buffer.getvalue()

        # --- NOVO: SALVAMENTO FÍSICO EXCLUSIVO DO ZIP NO WORKSPACE ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            caminho_zip = os.path.join(workspace_dir, "Dataset_RENUMF90_Pronto.zip")
            with open(caminho_zip, "wb") as f_out:
                f_out.write(zip_data)
                
            st.info(f"💾 **Segurança Ativa:** O pacote `Dataset_RENUMF90_Pronto.zip` foi salvo exclusiva e fisicamente na pasta do projeto:\n`{workspace_dir}`")
        # -------------------------------------------------------------

        # BOTÕES DE DOWNLOAD
        if pdf_bytes:
            st.download_button(
                label="📄 BAIXAR LAUDO OFICIAL EM PDF",
                data=pdf_bytes,
                file_name=f"Laudo_Executivo_RENUMF90_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf",
                mime="application/pdf",
                type="secondary",
                use_container_width=True
            )

        st.divider()
        st.subheader("🗑️ Relatório de Limpeza (Pré-Fortran)")
        if res['excluidos'].empty:
            st.success("✅ **Parabéns! Sua base de dados inicial passou ilesa na varredura técnica de integridade.**")
        else:
            st.error(f"⚠️ **Foram removidos {len(res['excluidos'])} registros falhos estruturalmente na varredura (ex: Auto-Parentesco, Sem ID).**")
            with st.expander("📋 Ver Lista de Exclusões"):
                st.dataframe(res['excluidos'])
                csv_excl = res['excluidos'].to_csv(sep=';', index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório de Exclusões (CSV)", csv_excl, "exclusoes_renumf90.csv", "text/csv")
        
        st.divider()
        st.subheader("📦 Arquivos Finais Traduzidos (Prontos para o BLUPF90)")
                
        # --- NOME DO ARQUIVO ZIP FIXO PARA SOBREPOSIÇÃO ---
        st.download_button(
            label="⬇️ BAIXAR PACOTE DE DADOS (.ZIP) PARA AVALIAÇÃO GENÉTICA",
            data=zip_data,
            file_name="Dataset_RENUMF90_Pronto.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )

        # ==========================================
        # BOTÃO PARA REINICIAR TODA A ETAPA
        # ==========================================
        st.divider()
        st.subheader("🔁 Nova Avaliação")
        st.markdown("Deseja refazer o processo de leitura do Fortran com outras configurações?")
        
        def reiniciar_etapa():
            if 'dados_renum_out' in st.session_state:
                del st.session_state['dados_renum_out']
                
        if st.button("🔄 Reiniciar Toda a Etapa", type="primary", on_click=reiniciar_etapa, use_container_width=True):
            st.rerun()

if __name__ == '__main__':
    render_renumf90_module()