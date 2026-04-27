import streamlit as st
import subprocess
import os
import tempfile
import platform
import shutil
from datetime import datetime
import pandas as pd
import zipfile
import io

def parse_solutions(filepath):
    """
    Lê o arquivo 'solutions' gerado pelo BLUPF90+ e o converte em um DataFrame pandas.
    O arquivo solutions tem o formato padrão: trait, effect, level, solution.
    """
    try:
        df = pd.read_csv(filepath, sep=r'\s+', header=None, engine='python')
        num_cols = len(df.columns)
        if num_cols == 4:
            df.columns = ['Trait', 'Effect', 'Level', 'Solution (DEP)']
        elif num_cols == 5:
            df.columns = ['Trait', 'Effect', 'Level', 'Solution (DEP)', 'Standard Error']
        else:
            df.columns = [f'Col_{i}' for i in range(num_cols)]
        return df
    except Exception as e:
        return pd.DataFrame() 

def render_prediction_module():
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

    st.title("🧬 Fase 3: Predição de DEPs Genômicas (Bifurcada)")
    
    st.markdown("""
    <div class="info-box">
        <strong>📚 O que faz esta etapa?</strong><br>
        O sistema pega as matrizes de variância recém-estimadas e resolve as Equações de Modelos Mistos (MME) usando o resolvedor padrão. Ele processa automaticamente as rotas <b>Lineares</b> e <b>Categóricas</b> em paralelo, gerando o valor genético final (DEP/GEBV) de cada animal.
    </div>
    """, unsafe_allow_html=True)

    if 'dados_pred_out' not in st.session_state:
        st.session_state.dados_pred_out = None

    # ==========================================
    # 1. ÁREA DE UPLOAD E WORKSPACE
    # ==========================================
    st.subheader("📂 1. Upload do Pacote e Motor Fortran")
    
    workspace_dir = st.session_state.get('workspace_dir')
    caminho_zip_auto = os.path.join(workspace_dir, "Variancias_Bifurcadas_Pronto.zip") if workspace_dir else None
    caminho_gen_auto = os.path.join(workspace_dir, "genotipos_qc_final.csv") if workspace_dir else None
    
    c1, c2 = st.columns(2)
    with c1: 
        if caminho_zip_auto and os.path.exists(caminho_zip_auto):
            st.success("📁 **'Variancias_Bifurcadas_Pronto.zip'** (Auto)")
            f_zip_up = st.file_uploader("Opcional: Trocar Pacote de Variâncias (.zip)", type="zip", key="pred_zip")
            f_zip = f_zip_up if f_zip_up is not None else caminho_zip_auto
        else:
            f_zip = st.file_uploader("1. Pacote de Variâncias (.zip)", type="zip", help="O arquivo .zip baixado na Fase 2.")
            
    with c2: 
        f_exe = st.file_uploader("2. Executável Unificado (blupf90+.exe - https://nce.ads.uga.edu/html/projects/programs/Windows/64bit/)", help="O mesmo motor utilizado na Fase 2.")
        
    c3, c4 = st.columns(2)
    with c3: 
        f_dlls = st.file_uploader("3. DLLs de Suporte (Opcional)", accept_multiple_files=True)
        
    with c4:
        if caminho_gen_auto and os.path.exists(caminho_gen_auto):
            st.success("📁 **'genotipos_qc_final.csv'** (Auto)")
            f_extras_up = st.file_uploader("Opcional: Trocar Arquivos Genômicos / Extras", accept_multiple_files=True, key="pred_extras")
            f_extras = f_extras_up if f_extras_up else [caminho_gen_auto]
        else:
            f_extras = st.file_uploader("4. Arquivos Genômicos / Extras (Para ssGBLUP)", accept_multiple_files=True, help="Faça o upload do genótipo e do pedigree original aqui.")

    # ==========================================
    # 2. EXECUÇÃO ORQUESTRADA
    # ==========================================
    if st.button("🚀 Iniciar Predição de DEPs", type="primary", use_container_width=True):
        if not f_zip:
            st.error("⚠️ Faça o upload (ou certifique-se da carga automática) do Pacote .zip da Fase 2.")
            return
        if not f_exe:
            st.error("⚠️ Faça o upload do executável unificado (blupf90+.exe).")
            return

        debug_log = []
        def dlog(msg):
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            debug_log.append(f"[{timestamp}] {msg}")

        with st.spinner("Descompactando pacote, processando genomas e equações de predição..."):
            try:
                dlog("=== INÍCIO DO TRACER DE EXECUÇÃO DA FASE 3 ===")
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmpdir_norm = os.path.normpath(tmpdir)
                    dlog(f"Diretório temporário criado: {tmpdir_norm}")
                    
                    # Extração do ZIP (Caminho físico ou UploadedFile em RAM)
                    with zipfile.ZipFile(f_zip, 'r') as z:
                        z.extractall(tmpdir_norm)
                        
                    # Limpeza de Segurança
                    for f in os.listdir(tmpdir_norm):
                        if f.startswith("fort.") or f == "solutions":
                            try:
                                os.remove(os.path.join(tmpdir_norm, f))
                            except:
                                pass
                                
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
                            
                    # --- INTELIGÊNCIA DE CONVERSÃO GENÔMICA ---
                    expected_snp_files = set()
                    for par_file in ["renf90_linear.par", "renf90_categ.par"]:
                        par_path = os.path.join(tmpdir_norm, par_file)
                        if os.path.exists(par_path):
                            with open(par_path, "r", encoding="utf-8", errors="ignore") as f:
                                for linha in f:
                                    if "OPTION SNP_file" in linha:
                                        parts = linha.strip().split()
                                        if len(parts) >= 3:
                                            expected_snp_files.add(parts[2])
                    
                    if expected_snp_files:
                        dlog(f"O Fortran está esperando os arquivos SNP: {expected_snp_files}")
                        
                        # Cópia do Dicionário (Cross-Reference)
                        for snp_file in expected_snp_files:
                            xref_base = f"{snp_file}_XrefID"
                            xref_path = os.path.join(tmpdir_norm, xref_base)
                            if not os.path.exists(xref_path):
                                if os.path.exists(f"{xref_path}_linear"):
                                    shutil.copy(f"{xref_path}_linear", xref_path)
                                elif os.path.exists(f"{xref_path}_categ"):
                                    shutil.copy(f"{xref_path}_categ", xref_path)

                    if f_extras:
                        for extra in f_extras:
                            if isinstance(extra, str):
                                extra_name = os.path.basename(extra)
                                with open(extra, 'rb') as f_in:
                                    extra_bytes = f_in.read()
                            else:
                                extra_name = extra.name
                                extra_bytes = extra.getvalue()
                                
                            target_path = os.path.join(tmpdir_norm, extra_name)
                            is_genotipo_csv = extra_name.endswith('.csv') and ('genotipo' in extra_name.lower() or 'snp' in extra_name.lower())
                            
                            if is_genotipo_csv and expected_snp_files:
                                target_name = list(expected_snp_files)[0]
                                target_path = os.path.join(tmpdir_norm, target_name)
                                dlog(f"Convertendo CSV genômico ({extra_name}) com alinhamento fixo (Fixed-Width).")
                                
                                try:
                                    content = extra_bytes.decode('utf-8', errors='ignore')
                                    lines = content.splitlines()
                                    with open(target_path, "w", encoding="utf-8") as f_out:
                                        for i, line in enumerate(lines):
                                            if i == 0 and any(c.isalpha() for c in line):
                                                continue
                                            
                                            # CORREÇÃO DEFINITIVA: Alinhamento fixo
                                            parts = line.replace(",", ";").split(";")
                                            if len(parts) >= 2:
                                                animal_id = parts[0].strip()
                                                snp_seq = parts[1].strip()
                                                f_out.write(f"{animal_id.ljust(15)} {snp_seq}\n")
                                            else:
                                                f_out.write(line.replace(";", " ") + "\n")
                                                
                                    dlog(f"Matriz de SNP alinhada e salva como {target_name}.")
                                except Exception as e:
                                    dlog(f"Erro na conversão: {e}")
                                    with open(target_path, "wb") as f:
                                        f.write(extra_bytes)
                            else:
                                with open(target_path, "wb") as f:
                                    f.write(extra_bytes)

                    has_linear = os.path.exists(os.path.join(tmpdir_norm, "renf90_linear.par"))
                    has_categ = os.path.exists(os.path.join(tmpdir_norm, "renf90_categ.par"))
                    
                    if not has_linear and not has_categ:
                        st.error("❌ O arquivo ZIP não contém os arquivos .par necessários.")
                        return

                    logs_gerados = {}
                    solucoes_raw = {}
                    solucoes_df = {}
                    alertas = []

                    def preparar_par_para_blup(nome_arquivo, sufixo):
                        caminho = os.path.join(tmpdir_norm, nome_arquivo)
                        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                            linhas = f.readlines()
                            
                        with open(caminho, "w", encoding="utf-8") as f:
                            for linha in linhas:
                                if "OPTION method" in linha:
                                    continue
                                linha_mod = linha
                                if "renf90.dat" in linha_mod:
                                    linha_mod = linha_mod.replace("renf90.dat", f"renf90_{sufixo}.dat")
                                if "renadd" in linha_mod and ".ped" in linha_mod:
                                    if f"renadd_{sufixo}" not in linha_mod:
                                        linha_mod = linha_mod.replace("renadd", f"renadd_{sufixo}")
                                f.write(linha_mod)

                    # --- ROTA A: PREDIÇÃO LINEAR ---
                    if has_linear:
                        st.info("⚙️ Resolvendo equações para o Modelo Linear...")
                        preparar_par_para_blup("renf90_linear.par", "linear")
                        
                        process_lin = subprocess.run(
                            [cmd_exe], 
                            input="renf90_linear.par\n", 
                            cwd=tmpdir_norm, 
                            capture_output=True, 
                            text=True
                        )
                            
                        logs_gerados['linear'] = process_lin.stdout + "\n" + process_lin.stderr
                        sol_path = os.path.join(tmpdir_norm, "solutions")
                        if os.path.exists(sol_path):
                            sol_lin_path = os.path.join(tmpdir_norm, "solutions_linear.txt")
                            os.rename(sol_path, sol_lin_path)
                            with open(sol_lin_path, "r", encoding="utf-8") as f:
                                solucoes_raw['linear'] = f.read()
                            solucoes_df['linear'] = parse_solutions(sol_lin_path)
                        else:
                            alertas.append("O arquivo 'solutions' linear não foi gerado pelo Fortran.")

                    # --- ROTA B: PREDIÇÃO CATEGÓRICA ---
                    if has_categ:
                        st.warning("⚙️ Resolvendo equações para o Modelo Categórico/Limiar...")
                        preparar_par_para_blup("renf90_categ.par", "categ")
                        
                        process_cat = subprocess.run(
                            [cmd_exe], 
                            input="renf90_categ.par\n", 
                            cwd=tmpdir_norm, 
                            capture_output=True, 
                            text=True
                        )
                            
                        logs_gerados['categ'] = process_cat.stdout + "\n" + process_cat.stderr
                        sol_path = os.path.join(tmpdir_norm, "solutions")
                        if os.path.exists(sol_path):
                            sol_cat_path = os.path.join(tmpdir_norm, "solutions_categ.txt")
                            os.rename(sol_path, sol_cat_path)
                            with open(sol_cat_path, "r", encoding="utf-8") as f:
                                solucoes_raw['categ'] = f.read()
                            solucoes_df['categ'] = parse_solutions(sol_cat_path)
                        else:
                            alertas.append("O arquivo 'solutions' categórico não foi gerado pelo Fortran.")

                    # --- MONTAGEM DO PACOTE ZIP FINAL ---
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        if has_linear and 'linear' in logs_gerados:
                            zip_file.writestr("log_predicao_linear.txt", logs_gerados['linear'])
                        if has_categ and 'categ' in logs_gerados:
                            zip_file.writestr("log_predicao_categ.txt", logs_gerados['categ'])
                        if has_linear and 'linear' in solucoes_raw:
                            zip_file.writestr("solutions_linear.txt", solucoes_raw['linear'])
                        if has_categ and 'categ' in solucoes_raw:
                            zip_file.writestr("solutions_categ.txt", solucoes_raw['categ'])
                            
                    zip_data = zip_buffer.getvalue()

                    dlog("=== FIM DO TRACER DE EXECUÇÃO ===")

                    # Salvando no estado da aplicação
                    st.session_state.dados_pred_out = {
                        "logs": logs_gerados,
                        "raw_files": solucoes_raw,
                        "dfs": solucoes_df,
                        "alertas": alertas,
                        "has_linear": has_linear,
                        "has_categ": has_categ,
                        "debug_log": "\n".join(debug_log),
                        "zip_data": zip_data
                    }
                    
                    # --- SALVAMENTO FÍSICO DO PACOTE ZIP NO WORKSPACE ---
                    if workspace_dir and os.path.exists(workspace_dir):
                        caminho_zip_out = os.path.join(workspace_dir, "Predicoes_GEBVs_Finais_Pronto.zip")
                        with open(caminho_zip_out, "wb") as f_out:
                            f_out.write(zip_data)
                    # -------------------------------------------------------------
                    
                    st.success("✅ Processamento finalizado! Verifique as abas abaixo.")

            except Exception as e:
                dlog(f"EXCEÇÃO CRÍTICA: {e}")
                st.error(f"Erro crítico: {e}")
                with st.expander("🐛 Log de Diagnóstico (Falha)", expanded=True):
                    st.text("\n".join(debug_log))

    # ==========================================
    # 3. EXIBIÇÃO DE RESULTADOS EM ABAS
    # ==========================================
    if st.session_state.get('dados_pred_out') is not None:
        res = st.session_state.dados_pred_out
        st.divider()
        
        # --- AVISO VISUAL DE SEGURANÇA NO DISCO ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            st.info(f"💾 **Segurança Ativa:** O pacote de predição foi salvo fisicamente na pasta do projeto. O Dashboard de DEPs está liberado!")
        
        if res['alertas']:
            for alerta in res['alertas']:
                st.error(f"⚠️ {alerta}")

        with st.expander("🐛 Log de Diagnóstico (Debug)", expanded=bool(res['alertas'])):
            st.text(res['debug_log'])
            st.download_button("📄 Baixar Log de Debug", res['debug_log'].encode('utf-8'), "debug_tracer_fase3.txt", "text/plain")

        st.subheader("📊 Tabelas de Soluções (DEPs e Efeitos Estimados)")
        tab_lin, tab_cat = st.tabs(["📉 DEPs Genômicas - Modelo Linear", "📈 DEPs Genômicas - Modelo Categórico"])
        
        with tab_lin:
            if res['has_linear']:
                with st.expander("📋 Ver Log Completo de Predição (Linear)", expanded=bool(res['alertas'])):
                    st.markdown(f"<div class='log-box'>{res['logs'].get('linear', '')}</div>", unsafe_allow_html=True)
                if 'linear' in res['dfs'] and not res['dfs']['linear'].empty:
                    df_lin = res['dfs']['linear']
                    efeitos = ['Todos'] + sorted(df_lin['Effect'].unique().tolist())
                    ef_sel = st.selectbox("Filtrar por Efeito (Fortran) - Linear:", efeitos, key="sb_lin")
                    st.dataframe(df_lin if ef_sel == 'Todos' else df_lin[df_lin['Effect'] == ef_sel], use_container_width=True, height=300)

        with tab_cat:
            if res['has_categ']:
                with st.expander("📋 Ver Log Completo de Predição (Categórico)", expanded=bool(res['alertas'])):
                    st.markdown(f"<div class='log-box'>{res['logs'].get('categ', '')}</div>", unsafe_allow_html=True)
                if 'categ' in res['dfs'] and not res['dfs']['categ'].empty:
                    df_cat = res['dfs']['categ']
                    efeitos = ['Todos'] + sorted(df_cat['Effect'].unique().tolist())
                    ef_sel = st.selectbox("Filtrar por Efeito (Fortran) - Categórico:", efeitos, key="sb_cat")
                    st.dataframe(df_cat if ef_sel == 'Todos' else df_cat[df_cat['Effect'] == ef_sel], use_container_width=True, height=300)

        st.divider()
        st.subheader("📥 Exportação de Dados Finais")
                
        # NOME DO ZIP FIXO PARA SOBREPOSIÇÃO
        st.download_button(
            label="💾 BAIXAR PACOTE DE PREDIÇÕES E LOGS (.ZIP)",
            data=res['zip_data'],
            file_name="Predicoes_GEBVs_Finais_Pronto.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )

        st.divider()
        if st.button("🔄 Nova Predição", type="secondary"):
            if 'dados_pred_out' in st.session_state:
                del st.session_state['dados_pred_out']
            st.rerun()

if __name__ == '__main__':
    render_prediction_module()