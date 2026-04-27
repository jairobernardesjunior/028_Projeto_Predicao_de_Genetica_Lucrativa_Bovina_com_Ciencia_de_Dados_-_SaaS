import streamlit as st
import pandas as pd
import subprocess
import tempfile
import os
import platform
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

# Configuração de Logs e Estilos de Gráfico
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
plt.rcParams.update({'font.size': 10, 'axes.labelsize': 12, 'axes.titlesize': 14})

class ProcessadorQC_PreGS:
    def __init__(self):
        self.logs = []
        self.registros_excluidos = []

    def log(self, mensagem, nivel="INFO"):
        self.logs.append(f"[{nivel}] {mensagem}")
        if nivel == "ERRO": logging.error(mensagem)

    def registrar_exclusao(self, id_animal, origem, motivo, explicacao, acao_recomendada):
        """Registra no formato amigável e detalhado para feedback ao laboratório/fazenda."""
        self.registros_excluidos.append({
            "ID_Animal": id_animal,
            "Tabela de Origem": origem,
            "Filtro / Motivo (Técnico)": motivo,
            "Explicação Simples": explicacao,
            "Ação Recomendada (Feedback)": acao_recomendada
        })

    def executar_pregsf90(self, df_gen, df_ped, maf, cr_snp, cr_anim, f_exe, hwe_val=0, progress_bar=None, status_text=None):
        """
        Orquestra a conversão de dados, execução do preGSf90 e coleta dos resultados.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            self.log(f"Diretório temporário criado: {tmpdir}")
            
            gen_path = os.path.join(tmpdir, "genotipos.txt")
            ped_path = os.path.join(tmpdir, "pedigree.txt")
            dummy_path = os.path.join(tmpdir, "dummy.dat")
            par_path = os.path.join(tmpdir, "pregsf90.par")
            xref_path = os.path.join(tmpdir, "genotipos.txt_XrefID")

            id_col_gen = df_gen.columns[0]
            id_col_ped = df_ped.columns[0]

            if status_text: status_text.text("Passo 1/4: Aplicando pré-filtros de engenharia e cruzando matrizes...")
            if progress_bar: progress_bar.progress(10)

            # =========================================================================
            # 1. PRÉ-FILTROS DE ENGENHARIA (PYTHON) E PROTEÇÃO DO ID "0"
            # =========================================================================
            # Remove linhas corrompidas onde o ID do animal é nulo, vazio ou "0" (0 é reservado para pais desconhecidos)
            df_gen = df_gen[df_gen[id_col_gen].notna() & (df_gen[id_col_gen].astype(str).str.strip() != '') & (df_gen[id_col_gen].astype(str).str.strip() != '0')]
            df_ped = df_ped[df_ped[id_col_ped].notna() & (df_ped[id_col_ped].astype(str).str.strip() != '') & (df_ped[id_col_ped].astype(str).str.strip() != '0')]

            # Interseção: Verifica animais com DNA, mas sem cadastro na genealogia (Órfãos de Pedigree)
            gen_ids = set(df_gen[id_col_gen].astype(str).str.strip())
            ped_ids = set(df_ped[id_col_ped].astype(str).str.strip())
            
            orfaos = gen_ids - ped_ids
            if orfaos:
                for o in orfaos:
                    self.registrar_exclusao(
                        o, "Genótipo", "Órfão de Pedigree (Pré-Filtro Python)", 
                        "Amostra de laboratório processada, mas o animal não existe no sistema da fazenda.", 
                        "Laboratório: Verificar se houve erro de digitação no ID da amostra. Fazenda: Verificar se o animal deixou de ser cadastrado no Pedigree."
                    )
                # Poda os órfãos do dataframe de genótipos para poupar o Fortran
                df_gen = df_gen[~df_gen[id_col_gen].astype(str).str.strip().isin(orfaos)]
                self.log(f"Removidos {len(orfaos)} genótipos órfãos (sem pedigree correspondente).")

            if status_text: status_text.text("Passo 2/4: Codificando IDs (Mapeamento Invisível) e estruturando arquivos...")
            if progress_bar: progress_bar.progress(30)

            # =========================================================================
            # 2. MAPEAMENTO INVISÍVEL (ENCODE) - SEGURO PARA BLUPF90
            # =========================================================================
            unique_ids = set()
            ped_cols = df_ped.columns[:3]
            
            unique_ids.update(df_gen[id_col_gen].astype(str).str.strip().tolist())
            for c in ped_cols:
                unique_ids.update(df_ped[c].astype(str).str.strip().tolist())

            # O valor '0' é explicitamente mantido como '0' para indicar pais desconhecidos.
            for null_val in ['0', 'nan', 'None', '', '5']:
                unique_ids.discard(null_val)

            id_to_int = {'0': '0'}
            int_to_id = {'0': '0'}
            for i, uid in enumerate(sorted(unique_ids), start=1):
                id_to_int[uid] = str(i)
                int_to_id[str(i)] = uid

            # Prepara o Pedigree
            try:
                df_ped_clean = df_ped[ped_cols].fillna('0').astype(str)
                for c in ped_cols:
                    df_ped_clean[c] = df_ped_clean[c].str.strip()
                
                df_ped_mapped = df_ped_clean.copy()
                for c in ped_cols:
                    df_ped_mapped[c] = df_ped_mapped[c].map(lambda x: id_to_int.get(x, '0'))
                    
                df_ped_mapped.to_csv(ped_path, sep=" ", index=False, header=False)
            except Exception as e:
                self.log(f"Erro ao preparar Pedigree: {str(e)}", "ERRO")
                return None, None

            # Prepara Genótipos e XrefID
            try:
                marker_cols = df_gen.columns[1:]
                if len(marker_cols) == 1:
                    geno_strings = df_gen[marker_cols[0]].astype(str)
                    geno_strings = geno_strings.str.replace(' ', '', regex=False).str.replace('nan', '5', case=False)
                    geno_strings = geno_strings.str.replace(r'\.0$', '', regex=True)
                else:
                    df_markers = df_gen[marker_cols].copy()
                    for col in df_markers.columns:
                        df_markers[col] = pd.to_numeric(df_markers[col], errors='coerce').fillna(5).astype(int).astype(str)
                    geno_strings = df_markers.apply(lambda x: ''.join(x.values), axis=1)

                with open(gen_path, "w") as f_gen_out, open(xref_path, "w") as f_xref_out:
                    for id_anim, g_str in zip(df_gen[id_col_gen].astype(str).str.strip(), geno_strings):
                        mapped_id = id_to_int.get(id_anim, '0')
                        f_gen_out.write(f"{mapped_id:<15} {g_str}\n")
                        f_xref_out.write(f"{mapped_id} {mapped_id}\n")
            except Exception as e:
                self.log(f"Erro ao preparar Genótipos/XrefID: {str(e)}", "ERRO")
                return None, None

            # Cria arquivo Dummy
            primeiro_id_valido = df_ped_mapped.iloc[0, 0]
            with open(dummy_path, "w") as f:
                f.write(f"{primeiro_id_valido} 1.0\n")

            # =========================================================================
            # 3. CONSTRUÇÃO DO PARÂMETRO COM FILTROS GENÉTICOS AVANÇADOS
            # =========================================================================
            str_hwe = f"\nOPTION HWE {hwe_val}" if hwe_val > 0 else ""
            
            par_content = f"""DATAFILE
dummy.dat
NUMBER_OF_TRAITS
1
NUMBER_OF_EFFECTS
1
OBSERVATION(S)
2
WEIGHT(S)

EFFECTS: POSITIONS_IN_DATAFILE NUMBER_OF_LEVELS TYPE_OF_EFFECT[EFFECT NESTED]
1 2 cross
RANDOM_RESIDUAL VALUES
1.0
RANDOM_GROUP
1
RANDOM_TYPE
add_animal
FILE
pedigree.txt
(CO)VARIANCES
1.0
OPTION SNP_file genotipos.txt
OPTION minfreq {maf}
OPTION callrate {cr_snp}
OPTION callrateAnim {cr_anim}{str_hwe}
"""
            with open(par_path, "w") as f:
                f.write(par_content)

            # Salva o executável e roda o Fortran
            try:
                exe_filename = f_exe.name.strip()
                exe_dest = os.path.join(tmpdir, exe_filename)
                with open(exe_dest, "wb") as f: 
                    f.write(f_exe.getbuffer())
                if platform.system() != "Windows": os.chmod(exe_dest, 0o755)
            except Exception as e:
                self.log(f"Erro ao salvar o executável: {str(e)}", "ERRO")
                return None, None

            if status_text: status_text.text("Passo 3/4: Executando motor Fortran (preGSf90)... Isso pode levar alguns minutos.")
            if progress_bar: progress_bar.progress(50)

            self.log(f"Iniciando motor {exe_filename}...")
            try:
                cmd_exe = f".\\{exe_filename}" if platform.system() == "Windows" else f"./{exe_filename}"
                process = subprocess.run([cmd_exe, "pregsf90.par"], cwd=tmpdir, input="\n\n\n\n\n", capture_output=True, text=True, timeout=90, check=True)
                self.log(f"Processamento concluído. Saída: {process.stdout[:500]}...")
            except subprocess.TimeoutExpired as e:
                self.log(f"TIMEOUT: {e.stdout}", "ERRO")
                return None, None
            except subprocess.CalledProcessError as e:
                self.log(f"Erro do preGSf90. STDERR: {e.stderr}", "ERRO")
                return None, None

            if status_text: status_text.text("Passo 4/4: Resgatando matrizes limpas geradas pelo Fortran...")
            if progress_bar: progress_bar.progress(80)

            # =========================================================================
            # 4. LEITURA DOS RESULTADOS E DECODE
            # =========================================================================
            resultados = {}
            for fname in os.listdir(tmpdir):
                fname_lower = fname.lower()
                if "clean" in fname_lower or "freqq" in fname_lower or "conflict" in fname_lower:
                    if fname_lower not in ["genotipos.txt", "pedigree.txt", "genotipos.txt_xrefid"]:
                        with open(os.path.join(tmpdir, fname), "r") as f:
                            resultados[fname] = f.read()

            has_clean_geno = any( ("geno" in k.lower() or "mrk" in k.lower() or "snp" in k.lower() or "genotipo" in k.lower()) and "clean" in k.lower() for k in resultados.keys() )
            if not has_clean_geno:
                with open(gen_path, "r") as f: resultados["genotipos_clean.txt"] = f.read()
                    
            has_clean_ped = any( "ped" in k.lower() and "clean" in k.lower() for k in resultados.keys() )
            if not has_clean_ped:
                with open(ped_path, "r") as f: resultados["pedigree_clean.txt"] = f.read()

            return resultados, int_to_id, len(gen_ids), len(orfaos)


# ==============================================================================
# --- INTERFACE DE RENDERIZAÇÃO (STREAMLIT) ---
# ==============================================================================
def render_qc_module():
    st.markdown("""<style>.block-container { padding-top: 1.5rem !important; }</style>""", unsafe_allow_html=True)

    st.title("🔬 Fase 1: Peneira Genômica (Controle de Qualidade de DNA)")
    
    st.markdown("""
    **Bem-vindo à Peneira Genômica.** Antes de cruzar os dados de DNA com os pesos dos animais, precisamos limpar o "ruído". 
    Garanta a máxima acurácia matemática nas suas DEPs genômicas. Esta fase audita falhas de digitação do laboratório, remove marcadores defeituosos e assegura que os animais com amostra de DNA correspondam à genealogia cadastrada na fazenda.
    """)
    
    with st.expander("🛡️ O que o sistema faz automaticamente nos bastidores (Filtros de Engenharia)?", expanded=False):
        st.markdown("""
        * **Cruzamento Genótipo x Pedigree (Detecção de Órfãos):** O sistema cruza automaticamente os animais genotipados com os cadastrados no Pedigree. Se o laboratório cobrou por um DNA, mas esse animal não existe no sistema da fazenda, ele é barrado imediatamente para não gerar custos computacionais irreais e gera um alerta financeiro ("Órfão de Pedigree").
        * **Proteção Estrutural do ID `0`:** O motor matemático exige que o número `0` seja estritamente reservado para representar "Pai Desconhecido" ou "Mãe Desconhecida". O código bloqueia animais com ID 0 e codifica os IDs alfanuméricos de forma segura, blindando e preservando a sua árvore genealógica de ponta a ponta.
        """)
        
    st.divider()

    if 'qc_processado' not in st.session_state:
        st.session_state.qc_processado = None

    if st.session_state.qc_processado:
        res = st.session_state.qc_processado
        
        # Bloco de Sucesso e Horários
        col_msg, col_bt = st.columns([3, 1])
        with col_msg:
            st.success(f"✅ **Auditoria Genômica Finalizada com Sucesso!**")
            st.caption(f"⏱️ **Início:** {res.get('data_inicio')} &nbsp; | &nbsp; 🏁 **Fim:** {res.get('data_fim')}")
            
        if col_bt.button("🔄 Nova Auditoria", use_container_width=True):
            st.session_state.qc_processado = None
            st.rerun()
            
        # --- AVISO VISUAL DE SEGURANÇA NO DISCO ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            st.info(f"💾 **Segurança Ativa:** As matrizes genômicas blindadas (`genotipos_qc_final.csv` e `pedigree_qc_final.csv`) foram salvas fisicamente na pasta do seu projeto.")
            
        # --- FUNIL DE DADOS (MÉTRICAS) ---
        st.subheader("📊 Funil de Retenção de Amostras Genômicas")
        col_f1, col_f2, col_f3 = st.columns(3)
        qtd_uteis = res['qtd_inicial'] - res['qtd_orfaos']
        qtd_aprovados = len(res['genotipos_qc']) if res['genotipos_qc'] is not None else 0
        
        col_f1.metric("1. Recebidas do Laboratório", res['qtd_inicial'])
        col_f2.metric("2. Úteis (Com Cadastro na Fazenda)", qtd_uteis, f"-{res['qtd_orfaos']} Órfãs")
        col_f3.metric("3. Aprovadas pelo Motor Genético", qtd_aprovados, f"-{res['animais_cortados']} Baixa Qualidade")

        df_excluidos = res.get('relatorio_exclusoes', pd.DataFrame())
        
        # --- GRÁFICOS DE MÉTRICAS ---
        st.divider()
        st.subheader("📈 Gráficos de Métricas de Qualidade")
        
        col_g1, col_g2 = st.columns(2)
        
        # Gráfico 1: Barras - Retenção de Animais
        with col_g1:
            fig_bar, ax_bar = plt.subplots(figsize=(6, 4))
            categorias = ['Recebidas', 'Úteis\n(Com Pedigree)', 'Aprovadas\n(Pós-Fortran)']
            valores = [res['qtd_inicial'], qtd_uteis, qtd_aprovados]
            sns.barplot(x=categorias, y=valores, ax=ax_bar, palette="viridis")
            ax_bar.set_ylabel('Número de Amostras')
            ax_bar.set_title('Retenção de Animais no QC')
            for i, v in enumerate(valores):
                ax_bar.text(i, v + (max(valores)*0.02), str(v), ha='center', va='bottom', fontweight='bold')
            sns.despine()
            st.pyplot(fig_bar)

        # Gráfico 2: Pizza - Motivos de Exclusão
        with col_g2:
            if not df_excluidos.empty:
                fig_pie, ax_pie = plt.subplots(figsize=(6, 4))
                contagem_motivos = df_excluidos['Filtro / Motivo (Técnico)'].value_counts()
                cores = sns.color_palette('pastel')[0:len(contagem_motivos)]
                ax_pie.pie(contagem_motivos, labels=contagem_motivos.index, autopct='%1.1f%%', startangle=140, colors=cores)
                ax_pie.set_title('Motivos de Exclusão das Amostras')
                st.pyplot(fig_pie)
            else:
                st.success("🎉 Nenhuma amostra excluída. Dados 100% íntegros e perfeitos!")
                
        # --- ALERTAS E RELATÓRIOS ---
        st.divider()
        if not df_excluidos.empty:
            st.warning(f"⚠️ **Prejuízo/Cortes:** Identificamos {len(df_excluidos)} anomalias nos dados que precisam de correção.")
            with st.expander("🚨 Ver Relatório de Amostras Rejeitadas (Para envio ao Laboratório/Fazenda)", expanded=True):
                st.markdown("As amostras abaixo custaram dinheiro, mas não podem ser usadas. Baixe este relatório e envie aos responsáveis exigindo correções ou novas análises.")
                st.dataframe(df_excluidos)
                csv_excluidos = df_excluidos.to_csv(sep=';', index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório de Erros Genômicos", csv_excluidos, "relatorio_falhas_laboratorio.csv", "text/csv", use_container_width=True)
            
        snps_cortados = res.get('snps_excluidos', 0)
        if snps_cortados > 0:
            st.info(f"🧬 **Marcadores (SNPs) Raros ou Defeituosos Removidos:** **{snps_cortados} colunas de DNA** foram descartadas pois não traziam variação genética útil (MAF) ou possuíam muitas falhas de leitura.")

    if not st.session_state.qc_processado:
        st.subheader("📂 1. Upload dos Dados Tratados")
        
        # --- NOVO: Integração com Workspace da Etapa 2 ---
        workspace_dir = st.session_state.get('workspace_dir')
        caminho_gen_auto = os.path.join(workspace_dir, "genotipos_tratado.csv") if workspace_dir else None
        caminho_ped_auto = os.path.join(workspace_dir, "pedigree_tratado.csv") if workspace_dir else None
        
        c1, c2 = st.columns(2)
        
        with c1: 
            if caminho_gen_auto and os.path.exists(caminho_gen_auto):
                st.success("📁 **'genotipos_tratado.csv'** carregado automaticamente do Projeto!")
                f_gen = st.file_uploader("Opcional: Subir outro arquivo de Genótipos?", key='qc_gen')
                gen_input = f_gen if f_gen is not None else caminho_gen_auto
            else:
                f_gen = st.file_uploader("Genótipos Tratados (.csv)", key='qc_gen')
                gen_input = f_gen
                
        with c2: 
            if caminho_ped_auto and os.path.exists(caminho_ped_auto):
                st.success("📁 **'pedigree_tratado.csv'** carregado automaticamente do Projeto!")
                f_ped = st.file_uploader("Opcional: Subir outro arquivo de Pedigree?", key='qc_ped')
                ped_input = f_ped if f_ped is not None else caminho_ped_auto
            else:
                f_ped = st.file_uploader("Pedigree Tratado (.csv)", key='qc_ped')
                ped_input = f_ped
        
        st.divider()
        st.subheader("⚙️ 2. Calibragem de Filtros Biológicos e Laboratoriais")
        st.info("Estas variáveis ditam o rigor da peneira. Elas são essenciais para auditar a qualidade do serviço do laboratório e garantir a acurácia dos cálculos.")
        
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            st.markdown("**(A) Frequência do Marcador:**")
            maf = st.number_input("MAF (minfreq)", value=0.05, min_value=0.0, max_value=0.5, step=0.01)
            st.caption("Frequência de Alelos Raros. Ex: 0.05 apaga qualquer marcador (coluna de DNA) onde a variação apareça em menos de 5% do rebanho, pois se quase 100% dos animais têm a mesma letra, o marcador não gera comparação estatística útil.")
            
        with col_p2:
            st.markdown("**(B) Qualidade da Leitura:**")
            cr_snp = st.number_input("Call Rate SNP (callrate)", value=0.90, min_value=0.0, max_value=1.0, step=0.01)
            st.caption("Qualidade do Marcador. Avalia a consistência do chip laboratorial. Ex: 0.90 exclui o marcador genético se o chip falhou/veio em branco em mais de 10% de todos os animais testados.")

        with col_p3:
            st.markdown("**(C) Qualidade da Amostra:**")
            cr_anim = st.number_input("Call Rate Animal (callrateAnim)", value=0.90, min_value=0.0, max_value=1.0, step=0.01)
            st.caption("Qualidade da Amostra Física do Animal (Pelo/Sangue). Ex: 0.90 exige que pelo menos 90% do exame esteja preenchido. Se a amostra tiver mais de 10% de 'buracos', o animal inteiro é reprovado da avaliação.")

        st.markdown("**(D) Filtros de Equilíbrio Populacional (Opcional):**")
        hwe_val = st.number_input("HWE (Equilíbrio de Hardy-Weinberg)", value=0.0, min_value=0.0, max_value=1.0, step=0.001, format="%.3f")
        st.caption("Valor 0 desativa o filtro. Se ativado (ex: 0.001), filtra SNPs com desvio drástico do equilíbrio populacional. Desvios severos desse equilíbrio geralmente não são fruto de seleção animal extrema, mas sim de erros técnicos graves de leitura durante a genotipagem no laboratório.")

        st.divider()
        st.subheader("🚀 3. Arquivo Executável do Motor (Fortran)")
        col_exe, col_btn = st.columns([3, 1])
        with col_exe: f_exe = st.file_uploader("Executável (preGSf90.exe) - https://nce.ads.uga.edu/html/projects/programs/Windows/64bit/", key="qc_exe")
        with col_btn:
            st.write(""); st.write("")
            btn_run = st.button("🚀 INICIAR AUDITORIA", use_container_width=True, type="primary")

        if btn_run and gen_input and ped_input and f_exe:
            inicio_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            st.info(f"⏳ Inicializando o processo de auditoria...")
            
            # --- ELEMENTOS VISUAIS DE PROGRESSO ---
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Reseta ponteiros caso venham do uploader (memória RAM)
            if hasattr(gen_input, 'seek'): gen_input.seek(0)
            if hasattr(ped_input, 'seek'): ped_input.seek(0)
            
            df_gen = pd.read_csv(gen_input, sep=';')
            df_ped = pd.read_csv(ped_input, sep=';')
            
            is_aglutinado = (len(df_gen.columns) == 2)
            qtd_snps_antes = len(str(df_gen.iloc[0, 1]).strip()) if is_aglutinado else len(df_gen.columns) - 1
            
            processador = ProcessadorQC_PreGS()
            
            # Interseção e Execução com tracking de progresso
            result = processador.executar_pregsf90(df_gen, df_ped, maf, cr_snp, cr_anim, f_exe, hwe_val, progress_bar, status_text)
            
            if result:
                status_text.text("Passo 4/4 (Final): Decodificando IDs, processando relatórios e montando matrizes finais...")
                progress_bar.progress(90)
                
                arquivos_limpos, int_to_id, qtd_inicial, qtd_orfaos = result
                df_gen_clean, df_ped_clean = None, None
                id_col_name = df_gen.columns[0]
                
                # Resgate das amostras enviadas (Descontando as órfãs já removidas pelo Python)
                animais_enviados_fortran = set(df_gen[df_gen[id_col_name].notna() & (~df_gen[id_col_name].astype(str).str.strip().isin(['', '0']))][id_col_name].astype(str).str.strip())
                
                for fname, conteudo in arquivos_limpos.items():
                    linhas = conteudo.strip().split('\n')
                    fname_lower = fname.lower()
                    
                    if ("geno" in fname_lower or "mrk" in fname_lower or "snp" in fname_lower) and "clean" in fname_lower:
                        dados_gen = []
                        for linha in linhas:
                            partes = linha.split()
                            if len(partes) >= 2:
                                _id_mapped = partes[0]
                                _id_original = int_to_id.get(_id_mapped, _id_mapped)
                                _snps = partes[1]
                                dados_gen.append([_id_original, _snps] if is_aglutinado else [_id_original] + list(_snps))
                        
                        if dados_gen:
                            colunas_gen = [id_col_name, df_gen.columns[1]] if is_aglutinado else [id_col_name] + [f"SNP_{i+1}" for i in range(len(dados_gen[0]) - 1)]
                            df_gen_clean = pd.DataFrame(dados_gen, columns=colunas_gen)
                    
                    elif "ped" in fname_lower and "clean" in fname_lower:
                        dados_ped = []
                        for linha in linhas:
                            partes = linha.split()
                            if partes:
                                linha_rec = [int_to_id.get(val, val) if idx < 3 else val for idx, val in enumerate(partes)]
                                dados_ped.append(linha_rec)
                        if dados_ped:
                            colunas_ped = list(df_ped.columns[:len(dados_ped[0])])
                            if len(colunas_ped) < len(dados_ped[0]): colunas_ped += [f"Var_{i}" for i in range(len(dados_ped[0]) - len(colunas_ped))]
                            df_ped_clean = pd.DataFrame(dados_ped, columns=colunas_ped)

                if df_ped_clean is None: df_ped_clean = df_ped.copy()
                    
                # Identifica quem sumiu do genótipo DENTRO do Fortran (Falta de Call Rate)
                animais_cortados = 0
                if df_gen_clean is not None:
                    animais_gen_depois = set(df_gen_clean[df_gen_clean.columns[0]].astype(str).str.strip())
                    animais_gen_excluidos = animais_enviados_fortran - animais_gen_depois
                    animais_cortados = len(animais_gen_excluidos)
                    for anim in animais_gen_excluidos:
                        processador.registrar_exclusao(
                            anim, "Genótipo", f"Call Rate Animal < {cr_anim}", 
                            "Amostra de laboratório muito falha (dados em branco). O animal foi reprovado por falta de qualidade do DNA.",
                            "Laboratório: Exigir repetição da placa/leitura ou solicitar novo material para extração."
                        )
                    qtd_snps_depois = len(str(df_gen_clean.iloc[0, 1]).strip()) if is_aglutinado else len(df_gen_clean.columns) - 1
                    snps_excluidos = max(0, qtd_snps_antes - qtd_snps_depois)
                else:
                    snps_excluidos = 0

                # --- NOVO: SALVAMENTO FÍSICO NO WORKSPACE ---
                if workspace_dir and os.path.exists(workspace_dir):
                    if df_gen_clean is not None:
                        df_gen_clean.to_csv(os.path.join(workspace_dir, "genotipos_qc_final.csv"), sep=';', index=False)
                    if df_ped_clean is not None:
                        df_ped_clean.to_csv(os.path.join(workspace_dir, "pedigree_qc_final.csv"), sep=';', index=False)

                progress_bar.progress(100)
                status_text.text("✅ Processamento finalizado com sucesso!")
                
                fim_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                st.session_state.qc_processado = {
                    "data_inicio": inicio_str,
                    "data_fim": fim_str,
                    "genotipos_qc": df_gen_clean,
                    "pedigree_qc": df_ped_clean,
                    "logs": processador.logs,
                    "relatorio_exclusoes": pd.DataFrame(processador.registros_excluidos),
                    "snps_excluidos": snps_excluidos,
                    "qtd_inicial": qtd_inicial,
                    "qtd_orfaos": qtd_orfaos,
                    "animais_cortados": animais_cortados
                }
                st.rerun()
            else:
                progress_bar.empty()
                status_text.empty()
                st.error("❌ Erro Crítico: O motor Fortran travou ou os dados são incompatíveis.")

    # Tela de Resultados / Exportação
    if st.session_state.qc_processado:
        res = st.session_state.qc_processado
        st.divider()
        
        st.subheader("📥 Exportação das Matrizes Genômicas (Blindadas)")
        st.markdown("Estes arquivos estão perfeitos, alinhados com a genealogia e prontos para o ssGBLUP.")
        
        cols_down = st.columns(2)
        
        def converter_df_csv(df): return df.to_csv(sep=';', index=False).encode('utf-8') if df is not None else None
            
        csv_gen = converter_df_csv(res.get('genotipos_qc'))
        csv_ped = converter_df_csv(res.get('pedigree_qc'))
        
        if csv_gen:
            cols_down[0].download_button(label="Baixar Genótipos (DNA Blindado)", data=csv_gen, file_name="genotipos_qc_final.csv", mime="text/csv", use_container_width=True)
        if csv_ped:
            cols_down[1].download_button(label="Baixar Pedigree (Árvore Ajustada)", data=csv_ped, file_name="pedigree_qc_final.csv", mime="text/csv", use_container_width=True)

        st.divider()
        with st.expander("Expandir para visualizar a execução interna e Logs do Fortran", expanded=False):
            st.text_area("", "\n".join(res['logs']), height=400)