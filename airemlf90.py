import streamlit as st
import subprocess
import os
import tempfile
import platform
import zipfile
import io
import re
from datetime import datetime

def extrair_resumo_variancias(log_text):
    """
    Tenta capturar o bloco final do log do AIREMLF90 onde as variâncias 
    estimadas são sumarizadas (ex: 'Estimates of variance components').
    """
    if not log_text:
        return "Log vazio ou não disponível."
        
    match = re.search(r'(Estimates of variance components.*|Final estimate.*|Final variance components.*)', log_text, re.DOTALL | re.IGNORECASE)
    
    if match:
        resumo = match.group(0)
        linhas = resumo.split('\n')
        return '\n'.join(linhas[:50]) 
    return "Bloco de resumo de variâncias não identificado automaticamente. Consulte o log completo na aba correspondente."

def render_variance_module():

    # --- Estilização ---
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem !important; }
        .info-box { background-color: #e8f8f5; border-left: 5px solid #1abc9c; padding: 15px; margin-bottom: 20px; border-radius: 4px; font-size: 14px; color: #2c3e50; }
        .log-box { background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 5px; font-family: 'Courier New', monospace; font-size: 12px; height: 300px; overflow-y: scroll; white-space: pre-wrap;}
        </style>
        """, 
        unsafe_allow_html=True
    )

    st.title("🧬 Fase 2: Estimação de Componentes de Variância (Bifurcado)")
    
    st.markdown("""
    <div class="info-box">
        <strong>📚 O que faz esta etapa?</strong><br>
        O sistema agora processa dois caminhos paralelos utilizando o motor unificado BLUPF90+: Características Lineares (Ex: Peso, Carcaça) usam o método <b>AIREML</b> para cálculo analítico exato. Características Categóricas (Ex: Stayability, Escores) usam o método <b>THRGIBBS1</b> (Bayesiano) simulando milhares de cenários para encontrar as variâncias.
    </div>
    """, unsafe_allow_html=True)

    # Inicialização de variáveis de estado
    if 'dados_var_out' not in st.session_state:
        st.session_state.dados_var_out = None

    # ==========================================
    # 1. ÁREA DE UPLOAD E WORKSPACE
    # ==========================================
    st.subheader("📂 1. Upload de Arquivos e Motor Fortran")
    
    workspace_dir = st.session_state.get('workspace_dir')
    caminho_zip_auto = os.path.join(workspace_dir, "Dataset_RENUMF90_Pronto.zip") if workspace_dir else None

    c1, c2, c3 = st.columns(3)
    with c1: 
        if caminho_zip_auto and os.path.exists(caminho_zip_auto):
            st.success("📁 **'Dataset_RENUMF90_Pronto.zip'** (Auto)")
            f_zip_up = st.file_uploader("Opcional: Trocar Pacote RENUMF90 (.zip)", type="zip", key="var_zip")
            f_zip = f_zip_up if f_zip_up is not None else caminho_zip_auto
        else:
            f_zip = st.file_uploader("Upload do Pacote RENUMF90 (.zip)", type="zip", help="O arquivo .zip baixado na Fase 1.", key="var_zip")
            
    with c2: 
        f_exe = st.file_uploader("Executável Unificado (blupf90+.exe)", help="Motor central que contém o AIREML e o GIBBS.")
        
    with c3: 
        f_dlls = st.file_uploader("DLLs de Suporte (Segure Ctrl para várias)", accept_multiple_files=True)

    # ==========================================
    # 2. CONFIGURAÇÕES ESPECÍFICAS (GIBBS)
    # ==========================================
    with st.expander("⚙️ Configurações Gibbs Sampling (Modelo Categórico)", expanded=False):
        st.markdown("<small style='color: #7f8c8d;'>Estas configurações só serão aplicadas se houver características categóricas no pacote ZIP.</small>", unsafe_allow_html=True)
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            iteracoes = st.number_input("Iterações (Gibbs)", min_value=1000, value=50000, step=5000)
        with col_g2:
            burnin = st.number_input("Burn-in (Gibbs)", min_value=100, value=10000, step=1000)
        with col_g3:
            st.info("💡 Modelos complexos exigem mais iterações para convergir.")

    # ==========================================
    # 3. EXECUÇÃO ORQUESTRADA
    # ==========================================
    if st.button("🚀 Iniciar Cálculo de Variâncias", type="primary", use_container_width=True):
        if not f_zip:
            st.error("⚠️ Faça o upload (ou certifique-se da carga automática) do Pacote .zip gerado pelo RENUMF90.")
            return
        if not f_exe:
            st.error("⚠️ Faça o upload do executável unificado (blupf90+.exe).")
            return

        with st.spinner("Descompactando pacote e analisando rotas estatísticas..."):
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir_norm = os.path.normpath(tmpdir)
                    
                    # Extração do ZIP (suporta tanto caminho em disco quanto UploadedFile da memória)
                    with zipfile.ZipFile(f_zip, 'r') as z:
                        z.extractall(tmpdir_norm)
                    
                    # Verificação de Rotas
                    has_linear = os.path.exists(os.path.join(tmpdir_norm, "renf90_linear.par"))
                    has_categ = os.path.exists(os.path.join(tmpdir_norm, "renf90_categ.par"))
                    
                    if not has_linear and not has_categ:
                        st.error("❌ O arquivo ZIP não contém renf90_linear.par nem renf90_categ.par. Verifique a Fase 1.")
                        return

                    # Preparando o Executável Único
                    exe_name = f_exe.name
                    exe_path = os.path.join(tmpdir_norm, exe_name)
                    with open(exe_path, "wb") as f:
                        f.write(f_exe.getbuffer())
                        
                    cmd_exe = f".\\{exe_name}" if platform.system() == "Windows" else f"./{exe_name}"
                    if platform.system() != "Windows":
                        os.chmod(exe_path, 0o755)

                    # Salvando DLLs
                    if f_dlls:
                        for dll in f_dlls:
                            with open(os.path.join(tmpdir_norm, dll.name), "wb") as f:
                                f.write(dll.getbuffer())

                    logs_gerados = {}
                    alertas = []
                    
                    # CORREÇÃO DEFINITIVA: Trava de segurança contra duplo sufixo
                    def preparar_par_para_variancia(nome_arquivo, sufixo, metodo):
                        caminho = os.path.join(tmpdir_norm, nome_arquivo)
                        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                            linhas = f.readlines()
                            
                        with open(caminho, "w", encoding="utf-8") as f:
                            for linha in linhas:
                                if "OPTION method" in linha.strip():
                                    continue
                                
                                linha_mod = linha
                                if "renf90.dat" in linha_mod:
                                    linha_mod = linha_mod.replace("renf90.dat", f"renf90_{sufixo}.dat")
                                    
                                # A trava: só substitui se ainda não tiver sido substituído antes
                                if "renadd" in linha_mod and ".ped" in linha_mod:
                                    if f"renadd_{sufixo}" not in linha_mod:
                                        linha_mod = linha_mod.replace("renadd", f"renadd_{sufixo}")
                                    
                                f.write(linha_mod)
                                
                            f.write(f"\nOPTION method {metodo}\n")

                    # --- ROTA A: PIPELINE LINEAR (AIREML) ---
                    if has_linear:
                        st.info("⚙️ Iniciando processamento Linear (Método AIREML)...")
                        
                        preparar_par_para_variancia("renf90_linear.par", "linear", "aireml")
                        
                        process_lin = subprocess.run(
                            [cmd_exe], 
                            input="renf90_linear.par\n", 
                            cwd=tmpdir_norm, 
                            capture_output=True, 
                            text=True
                        )
                        
                        logs_gerados['linear'] = process_lin.stdout + "\n" + process_lin.stderr
                        with open(os.path.join(tmpdir_norm, "log_aireml.txt"), "w", encoding='utf-8') as f:
                            f.write(logs_gerados['linear'])
                            
                        if process_lin.returncode != 0:
                            alertas.append(f"Erro na rota Linear: {process_lin.stderr}")

                    # --- ROTA B: PIPELINE CATEGÓRICO (THRGIBBS1) ---
                    if has_categ:
                        st.warning("⚙️ Iniciando processamento Bayesiano (Método THRGIBBS1). Isso pode demorar...")
                        
                        preparar_par_para_variancia("renf90_categ.par", "categ", "thrgibbs1")

                        # O Gibbs interativo ainda pede: [arquivo], [iterações], [burn-in] via terminal
                        input_cat = f"renf90_categ.par\n{int(iteracoes)}\n{int(burnin)}\n\n\n\n"
                        
                        process_cat = subprocess.run(
                            [cmd_exe], 
                            input=input_cat, 
                            cwd=tmpdir_norm, 
                            capture_output=True, 
                            text=True
                        )
                        
                        logs_gerados['categ'] = process_cat.stdout + "\n" + process_cat.stderr
                        with open(os.path.join(tmpdir_norm, "log_thrgibbs.txt"), "w", encoding='utf-8') as f:
                            f.write(logs_gerados['categ'])
                            
                        if process_cat.returncode != 0:
                            alertas.append(f"Erro na rota Categórica: {process_cat.stderr}")

                    # EMPACOTAMENTO
                    res_files = {}
                    exclude_ext = ['.exe', '.dll']
                    
                    for filename in os.listdir(tmpdir_norm):
                        file_ext = os.path.splitext(filename)[1].lower()
                        if file_ext not in exclude_ext:
                            filepath = os.path.join(tmpdir_norm, filename)
                            if os.path.isfile(filepath):
                                with open(filepath, "rb") as f:
                                    res_files[filename] = f.read()
                                    
                    # Criação do ZIP na memória RAM
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for fname, fdata in res_files.items():
                            zip_file.writestr(fname, fdata)
                            
                    zip_data = zip_buffer.getvalue()

                    st.session_state.dados_var_out = {
                        "logs": logs_gerados,
                        "files": res_files,
                        "alertas": alertas,
                        "has_linear": has_linear,
                        "has_categ": has_categ,
                        "zip_data": zip_data
                    }
                    
                    # --- NOVO: SALVAMENTO FÍSICO EXCLUSIVO DO ZIP NO WORKSPACE ---
                    if workspace_dir and os.path.exists(workspace_dir):
                        caminho_zip_out = os.path.join(workspace_dir, "Variancias_Bifurcadas_Pronto.zip")
                        with open(caminho_zip_out, "wb") as f_out:
                            f_out.write(zip_data)
                    # -------------------------------------------------------------
                    
                    st.success("✅ Cálculos de variância finalizados com sucesso!")

            except Exception as e:
                st.error(f"Erro crítico durante a execução do Fortran: {e}")

    # ==========================================
    # 4. EXIBIÇÃO DE RESULTADOS E DOWNLOADS
    # ==========================================
    if st.session_state.get('dados_var_out') is not None:
        res = st.session_state.dados_var_out
        st.divider()
        
        # --- AVISO VISUAL DE SEGURANÇA NO DISCO ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            st.info(f"💾 **Segurança Ativa:** O pacote `Variancias_Bifurcadas_Pronto.zip` foi salvo exclusiva e fisicamente na pasta do projeto e destravou a etapa de Predição de DEPs.")
        
        if res['alertas']:
            for alerta in res['alertas']:
                st.error(alerta)

        st.subheader("📊 Resumo das Matrizes Estimadas")
        
        tab_lin, tab_cat = st.tabs(["📉 Modelo Linear (REML)", "📈 Modelo Categórico (Bayesiano)"])
        
        # ABA LINEAR
        with tab_lin:
            if res['has_linear']:
                st.markdown("**Resumo Automático de Variâncias (AIREML):**")
                resumo_lin = extrair_resumo_variancias(res['logs'].get('linear', ''))
                st.code(resumo_lin, language="text")
                
                with st.expander("📋 Ver Log Completo de Convergência (Linear)", expanded=False):
                    st.markdown(f"<div class='log-box'>{res['logs'].get('linear', '')}</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhuma característica linear foi processada neste lote.")

        # ABA CATEGÓRICA
        with tab_cat:
            if res['has_categ']:
                st.markdown("**Relatório de Amostragem (THRGIBBS1):**")
                st.write("O modelo Bayesiano gera um arquivo chamado `gibbs_samples` que contém as amostras gravadas. O resumo do processamento está abaixo:")
                
                log_cat = res['logs'].get('categ', '')
                linhas_cat = log_cat.split('\n')
                resumo_cat = '\n'.join(linhas_cat[-30:]) if len(linhas_cat) > 30 else log_cat
                st.code(resumo_cat, language="text")
                
                with st.expander("📋 Ver Log Completo de Amostragem (Categórico)", expanded=False):
                    st.markdown(f"<div class='log-box'>{log_cat}</div>", unsafe_allow_html=True)
            else:
                st.info("Nenhuma característica categórica foi processada neste lote.")

        # BOTÕES DE DOWNLOAD
        st.divider()
        st.subheader("📦 Download do Pacote Final (Pronto para BLUPF90)")
        st.markdown("O ZIP abaixo contém os parâmetros atualizados, os logs e os arquivos `gibbs_samples`. **Este é o pacote que você deve fornecer na Fase 3 para predição final das DEPs.**")
                
        # NOME DO ZIP FIXO PARA SOBREPOSIÇÃO
        st.download_button(
            label="⬇️ BAIXAR PACOTE COM VARIÂNCIAS ESTIMADAS (.ZIP)",
            data=res['zip_data'],
            file_name="Variancias_Bifurcadas_Pronto.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
        
        st.divider()
        def reiniciar_etapa_var():
            if 'dados_var_out' in st.session_state:
                del st.session_state['dados_var_out']
                
        if st.button("🔄 Reiniciar Fase de Variâncias", type="secondary", on_click=reiniciar_etapa_var):
            st.rerun()

if __name__ == '__main__':
    render_variance_module()