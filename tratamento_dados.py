import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
import scipy.stats as stats
import base64
import os
import re
from io import BytesIO
from datetime import datetime  

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ProcessadorSSGBLUP:
    def __init__(self):
        self.logs = []
        self.figuras = []
        self.registros_excluidos = [] 
        self.registros_faltantes = [] 
        self.alertas_biologicos = [] 
        plt.rcParams.update({'font.size': 12, 'axes.labelsize': 14, 'axes.titlesize': 16})

    def log(self, mensagem, nivel="INFO"):
        self.logs.append(f"[{nivel}] {mensagem}")
        if nivel == "ERRO": logging.error(mensagem)

    def registrar_exclusao(self, id_animal, local, motivo):
        self.registros_excluidos.append({
            "ID_Animal": id_animal,
            "Local / Fazenda": local,
            "Motivo da Exclusão (Linguagem Técnica)": motivo,
            "Explicação Simples": self.traduzir_motivo_exclusao(motivo)
        })

    def registrar_faltante(self, id_animal, local, variavel, tabela):
        """Registra variáveis em branco (NaN) que receberam o sinalizador -999 para o BLUPF90."""
        self.registros_faltantes.append({
            "ID_Animal": id_animal,
            "Local / Fazenda": local,
            "Tabela de Origem": tabela,
            "Variável Ausente (NaN)": variavel,
            "Ação do Sistema": "Substituído por -999 (Sinalizador de ausência para BLUPF90)"
        })

    def registrar_alerta(self, id_animal, local, pilar, erro_tecnico, explicacao):
        """Registra inconsistências biológicas/estruturais SEM modificar os dados originais."""
        self.alertas_biologicos.append({
            "ID_Animal": id_animal,
            "Local / Fazenda": local,
            "Pilar de Validação": pilar,
            "Alerta Técnico": erro_tecnico,
            "Ação Necessária (Simples)": explicacao
        })

    def traduzir_motivo_exclusao(self, motivo):
        if "Outlier" in motivo:
            return "Animal apresentou uma medida muito irreal (alta ou baixa demais) se comparado aos animais que comeram o mesmo pasto no mesmo lote. Pode ser erro de digitação da balança."
        if "Categoria inconsistente" in motivo:
            return "Animal marcado como Enfermaria ou Descarte. Animais doentes não devem ser comparados geneticamente com os sadios."
        if "duplicidade" in motivo:
            return "Registro repetido de forma idêntica no mesmo arquivo. A cópia foi removida para não duplicar o peso do animal."
        return "Dado inconsistente para avaliação genética."

    def padronizar_id(self, serie):
        return serie.astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()

    def remover_duplicatas(self, df, nome_arquivo):
        duplicatas = df[df.duplicated(keep='first')]
        if not duplicatas.empty:
            ids_duplicados = duplicatas['ID_Animal'].tolist() if 'ID_Animal' in duplicatas.columns else ['N/A'] * len(duplicatas)
            locais_duplicados = duplicatas['Fazenda'].tolist() if 'Fazenda' in duplicatas.columns else ['N/A'] * len(duplicatas)
            for id_animal, local in zip(ids_duplicados, locais_duplicados):
                self.registrar_exclusao(id_animal, local, f"Registro em duplicidade removido ({nome_arquivo}).")
            self.log(f"Removidas {len(duplicatas)} duplicatas em {nome_arquivo}.")
        return df.drop_duplicates()

    def normalizar_zscore(self, serie):
        if serie.std() == 0: return serie
        return (serie - serie.mean()) / serie.std()

    # --- VALIDAÇÕES AVANÇADAS (BIOLÓGICAS E ESTRUTURAIS) ---
    def validar_contratos_dados(self, df, nome_tabela, colunas_obrigatorias):
        """Pilar 5: Engenharia de Software (Data Contracts). Verifica o Schema."""
        colunas_ausentes = [col for col in colunas_obrigatorias if col not in df.columns]
        if colunas_ausentes:
            self.registrar_alerta(
                "N/A", "Geral", "Pilar 5: Data Contracts",
                f"Schema Incompleto em {nome_tabela}",
                f"As colunas obrigatórias {colunas_ausentes} não foram encontradas. O sistema tentará prosseguir, mas a avaliação pode ficar comprometida. Verifique o cabeçalho do seu arquivo CSV."
            )

    def validar_pedigree_biologico(self, df):
        """Pilar 1: Validação do Pedigree (Grafo e Sexagem)"""
        if 'ID_Animal' not in df.columns: return

        # 1. Auto-filiação (Ciclo Impossível)
        if 'ID_Pai' in df.columns:
            mask_pai = (df['ID_Animal'] == df['ID_Pai']) & (df['ID_Animal'].notna())
            for _, row in df[mask_pai].iterrows():
                self.registrar_alerta(row['ID_Animal'], "Pedigree", "Pilar 1: Pedigree", 
                                      "Ciclo Genealógico (ID_Animal = ID_Pai)", 
                                      "O animal está listado como sendo o próprio pai. Verifique o cadastro do pedigree.")
        
        if 'ID_Mae' in df.columns:
            mask_mae = (df['ID_Animal'] == df['ID_Mae']) & (df['ID_Animal'].notna())
            for _, row in df[mask_mae].iterrows():
                self.registrar_alerta(row['ID_Animal'], "Pedigree", "Pilar 1: Pedigree", 
                                      "Ciclo Genealógico (ID_Animal = ID_Mae)", 
                                      "A fêmea está listada como sendo a própria mãe. Verifique o cadastro do pedigree.")

        # 2. Conflito de Sexo Biológico (Hermafroditas no Banco)
        if 'ID_Pai' in df.columns and 'ID_Mae' in df.columns:
            pais_unicos = set(df.loc[df['ID_Pai'].notna() & (df['ID_Pai'] != ''), 'ID_Pai'])
            maes_unicas = set(df.loc[df['ID_Mae'].notna() & (df['ID_Mae'] != ''), 'ID_Mae'])
            conflito_sexo = pais_unicos.intersection(maes_unicas)
            
            if conflito_sexo:
                for animal_herma in conflito_sexo:
                    mask_afetados = (df['ID_Pai'] == animal_herma) | (df['ID_Mae'] == animal_herma)
                    para_quem = df[mask_afetados]['ID_Animal'].tolist()
                    self.registrar_alerta(animal_herma, "Pedigree", "Pilar 1: Pedigree",
                                          "Conflito de Sexagem Biológica",
                                          f"Este animal aparece como PAI de alguns animais e MÃE de outros (ex: para os animais {para_quem[:3]}). Corrija a genealogia urgente.")

    def validar_crescimento_biologico(self, df):
        """Pilar 2: Consistência Biológica Longitudinal (Fenótipos)"""
        if 'PN_kg' in df.columns and 'PD_kg' in df.columns:
            mask_pn_pd = (df['PN_kg'] > df['PD_kg']) & (df['PN_kg'].notna()) & (df['PD_kg'].notna())
            for _, row in df[mask_pn_pd].iterrows():
                local = row.get('Fazenda', 'N/A')
                self.registrar_alerta(row.get('ID_Animal', 'N/A'), local, "Pilar 2: Biologia",
                                      f"Inversão de Crescimento (PN: {row['PN_kg']} > PD: {row['PD_kg']})",
                                      "Biologicamente impossível: O peso ao nascer está maior que o peso na desmama. Provável erro de digitação na prancheta ou na balança.")

        if 'PD_kg' in df.columns and 'PS_kg' in df.columns:
            mask_pd_ps = (df['PD_kg'] > df['PS_kg']) & (df['PD_kg'].notna()) & (df['PS_kg'].notna())
            for _, row in df[mask_pd_ps].iterrows():
                local = row.get('Fazenda', 'N/A')
                self.registrar_alerta(row.get('ID_Animal', 'N/A'), local, "Pilar 2: Biologia",
                                      f"Inversão de Crescimento (PD: {row['PD_kg']} > PS: {row['PS_kg']})",
                                      "O animal 'encolheu'. O peso na desmama está maior que o peso ao sobreano (18 meses). Revisar apontamento.")

    def validar_integridade_gcs(self, df):
        """Pilar 3: Integridade Estatística dos Grupos Contemporâneos"""
        if 'GC' in df.columns:
            gc_counts = df['GC'].value_counts()
            micro_gcs = gc_counts[gc_counts < 3].index
            
            if not micro_gcs.empty:
                mask_micro = df['GC'].isin(micro_gcs)
                for _, row in df[mask_micro].iterrows():
                    local = row.get('Fazenda', 'N/A')
                    self.registrar_alerta(row.get('ID_Animal', 'N/A'), local, "Pilar 3: GCs",
                                          f"Micro-Grupo Contemporâneo (GC: {row['GC']} tem apenas {gc_counts[row['GC']]} animais)",
                                          "Lote muito pequeno (menos de 3 animais). É impossível comparar geneticamente quem é melhor ou pior num grupo tão pequeno. Tente reagrupar.")

    # --- FLUXO PRINCIPAL DE TRATAMENTO ---
    def gerar_graficos_frequencia_original(self, df):
        try:
            sns.set_context("talk") 
            fig1, ax1 = plt.subplots(figsize=(14, 8))
            counts_fp = df.groupby(['Fazenda', 'Piquete']).size().reset_index(name='Total')
            counts_fp['Faz_Piq'] = counts_fp['Fazenda'].astype(str) + "-" + counts_fp['Piquete'].astype(str)
            sns.barplot(data=counts_fp.sort_values('Total', ascending=False).head(20), 
                        x='Faz_Piq', y='Total', ax=ax1, palette='viridis')
            ax1.set_title('Top 20: Quantidade de Animais por Fazenda e Piquete', fontsize=18)
            ax1.tick_params(axis='x', rotation=45, labelsize=12)
            plt.tight_layout()
            self.figuras.append(fig1)

            fig2, ax2 = plt.subplots(figsize=(14, 6))
            lote_counts = df['Lote_Manejo'].value_counts().head(20)
            sns.barplot(x=lote_counts.index, y=lote_counts.values, ax=ax2, palette='magma')
            ax2.set_title('Top 20: Distribuição dos Animais nos Lotes de Manejo', fontsize=18)
            ax2.tick_params(axis='x', rotation=45, labelsize=12)
            plt.tight_layout()
            self.figuras.append(fig2)

            if 'GC' in df.columns: 
                fig3, ax3 = plt.subplots(figsize=(14, 6))
                gc_counts = df['GC'].value_counts().head(20)
                sns.barplot(x=gc_counts.index, y=gc_counts.values, ax=ax3, palette='rocket')
                ax3.set_title('Top 20: Grupos Contemporâneos (Animais criados juntos nas mesmas condições)', fontsize=18)
                plt.tight_layout()
                self.figuras.append(fig3)
                
            sns.set_context("notebook")
        except Exception as e:
            self.log(f"Erro gráficos originais: {str(e)}", "AVISO")

    def tratar_pedigree(self, df):
        self.validar_contratos_dados(df, "Pedigree", ['ID_Animal', 'ID_Pai', 'ID_Mae'])
        df = self.remover_duplicatas(df, "pedigree.csv")
        for col in ['ID_Animal', 'ID_Pai', 'ID_Mae']:
            if col in df.columns: df[col] = self.padronizar_id(df[col])
            
        self.validar_pedigree_biologico(df)

        if 'Sexo' in df.columns: df['Sexo'] = df['Sexo'].map({'M': 1, 'F': 2}).fillna(0).astype(int)
        if 'Raca' in df.columns: df['Raca'] = df['Raca'].apply(lambda x: 1.0 if 'Nelore' in str(x) else 0.5)
        if 'Data_Nascimento' in df.columns: df['Data_Nascimento'] = pd.to_datetime(df['Data_Nascimento'], errors='coerce').dt.strftime('%Y%m%d').astype(float)
        if 'Geracao' in df.columns: df['Geracao'] = pd.to_numeric(df['Geracao'], errors='coerce').fillna(0).astype(int)

        if 'Categoria' in df.columns:
            inconsistentes = df[df['Categoria'].str.contains("Enfermaria|Descarte", case=False, na=False)]
            for _, row in inconsistentes.iterrows():
                self.registrar_exclusao(row.get('ID_Animal', 'N/A'), "Pedigree", f"Categoria inconsistente: {row['Categoria']}")
            df = df[~df['Categoria'].str.contains("Enfermaria|Descarte", case=False, na=False)]
            
        return df

    def tratar_ambiente(self, df, df_ped):
        self.validar_contratos_dados(df, "Ambiente", ['ID_Animal', 'Fazenda'])
        df = self.remover_duplicatas(df, "ambiente.csv")
        df_plot = df.copy()
        self.gerar_graficos_frequencia_original(df_plot)

        if 'ID_Animal' in df.columns: df['ID_Animal'] = self.padronizar_id(df['ID_Animal'])

        for col in ['Fazenda', 'Piquete']:
            if col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.strip().str.upper()
                    labels, uniques = pd.factorize(df[col])
                    df[col] = labels + 1
                else:
                    df[col] = df[col].fillna(0).astype(int)

        if 'Estacao' in df.columns: df['Estacao'] = df['Estacao'].map({'Verão': 1, 'Outono': 2, 'Inverno': 3, 'Primavera': 4}).fillna(0).astype(int)
        if 'Regime_Alim' in df.columns and df['Regime_Alim'].dtype == 'object':
             df['Regime_Alim'] = df['Regime_Alim'].map({'Pasto': 1, 'Pasto + Suplemento': 2, 'Suplemento': 3, 'Confinamento': 4}).fillna(0).astype(int)

        for col_cat in ['Lote_Manejo', 'Tipo_Pastagem', 'Localidade_Bloco']:
            if col_cat in df.columns and df[col_cat].dtype == 'object':
                labels, uniques = pd.factorize(df[col_cat])
                df[col_cat] = labels + 1
            
        if 'Data_Coleta_Pesagem' in df.columns:
            df['Data_Coleta_Pesagem'] = pd.to_datetime(df['Data_Coleta_Pesagem'], errors='coerce').dt.strftime('%Y%m%d').astype(float)

        for col in ['ITU_Media', 'ITU_DP', 'ITU_Max', 'itu_min', 'itu_horas_criticas']:
            if col in df.columns:
                orig = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
                df[col] = self.normalizar_zscore(orig)

        return df

    def tratar_fenotipos(self, df, df_amb):
        self.validar_contratos_dados(df, "Fenótipos", ['ID_Animal'])
        df = self.remover_duplicatas(df, "fenotipos.csv")
        vars_plot = ['PN_kg', 'PD_kg', 'PS_kg', 'GPD_g-dia', 'PE_cm', 'AOL_cm2', 'EGS_mm', 'MAR_%', 'CAR_kg-dia', 'REND_%', 'PROB_3P_%', 'IPP_dias']
        df_original = df.copy()

        if 'ID_Animal' in df.columns: df['ID_Animal'] = self.padronizar_id(df['ID_Animal'])

        for col in vars_plot:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='coerce')
                if col in df_original.columns:
                    df_original[col] = pd.to_numeric(df_original[col].astype(str).str.replace(',', '.'), errors='coerce')

        self.validar_crescimento_biologico(df)

        if 'GC' in df.columns:
            self.validar_integridade_gcs(df)
            for col in vars_plot:
                if col in df.columns and col != 'IPP_dias': 
                    def calc_limites(group):
                        s = group[col].dropna()
                        if len(s) > 5:
                            q1, q3 = s.quantile(0.25), s.quantile(0.75)
                            iqr = q3 - q1
                            return pd.Series({'lower': q1 - 1.5 * iqr, 'upper': q3 + 1.5 * iqr})
                        return pd.Series({'lower': -np.inf, 'upper': np.inf})

                    limites = df.groupby('GC').apply(calc_limites).reset_index()
                    df_temp = df.merge(limites, on='GC', how='left')
                    
                    cond_outlier = (df_temp[col].notna()) & ((df_temp[col] < df_temp['lower']) | (df_temp[col] > df_temp['upper']))
                    outliers = df_temp[cond_outlier]
                    
                    for _, row in outliers.iterrows():
                        local = row.get('Fazenda', 'N/A')
                        self.registrar_exclusao(
                            row['ID_Animal'], local, 
                            f"Outlier em {col} (Valor: {row[col]:.2f}) fora do limite do GC {row['GC']}"
                        )
                    df = df_temp[~cond_outlier].drop(columns=['lower', 'upper'])

        if 'EGS_mm' in df.columns and abs(df['EGS_mm'].skew()) > 1:
            df['EGS_mm'] = np.log1p(df['EGS_mm'].clip(lower=0))
                
        return df

    def tratar_genotipos(self, df):
        self.validar_contratos_dados(df, "Genótipos", ['ID_Animal'])
        df = self.remover_duplicatas(df, "genotipos.csv")
        if 'ID_Animal' in df.columns: df['ID_Animal'] = self.padronizar_id(df['ID_Animal'])
        return df

    def finalizar(self, df, nome_tabela="Geral"):
        cols_num = df.select_dtypes(include=[np.number]).columns
        
        for col in cols_num:
            missing_mask = df[col].isna()
            if missing_mask.any():
                missing_df = df[missing_mask]
                ids = missing_df['ID_Animal'].tolist() if 'ID_Animal' in missing_df.columns else ['N/A'] * len(missing_df)
                locais = missing_df['Fazenda'].tolist() if 'Fazenda' in missing_df.columns else ['N/A'] * len(missing_df)
                
                for id_animal, local in zip(ids, locais):
                    self.registrar_faltante(id_animal, local, col, nome_tabela)

        # Preenche os valores nulos
        df[cols_num] = df[cols_num].fillna(-999)
        
        # Tenta reverter colunas para inteiro onde não há perda de informação decimal.
        # Isso impede que IDs categóricos (como GC e Fazenda) fiquem como float apenas por causa do NaN preenchido.
        for col in cols_num:
            try:
                if (df[col] == df[col].astype(int)).all():
                    df[col] = df[col].astype(int)
            except (ValueError, TypeError):
                pass
                
        return df

    def gerar_grafico_explicativo(self):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        
        x = np.linspace(-3, 3, 100)
        y = stats.norm.pdf(x, 0, 1)
        axes[0].plot(x, y, color='#27ae60', lw=3)
        axes[0].fill_between(x, y, alpha=0.3, color='#2ecc71')
        axes[0].set_title('Exemplo: A Curva de Sino (Ideal)', fontsize=14, fontweight='bold', color='#2c3e50')
        axes[0].set_yticks([])
        axes[0].set_xticks([])
        axes[0].text(0, 0.15, 'Média do Rebanho\n(A maioria fica aqui)', ha='center', fontsize=11, fontweight='bold', color='#145a32')
        axes[0].text(-2.5, 0.05, 'Muito\nLeves', ha='center', fontsize=10, color='#e74c3c')
        axes[0].text(2.5, 0.05, 'Muito\nPesados', ha='center', fontsize=10, color='#2980b9')
        axes[0].spines['top'].set_visible(False); axes[0].spines['right'].set_visible(False); axes[0].spines['left'].set_visible(False)

        np.random.seed(42)
        x_skew = np.random.exponential(scale=2, size=1000)
        n, bins, patches = axes[1].hist(x_skew, bins=4, edgecolor='white')
        axes[1].set_title('Exemplo: Divisão em Classes (Agrupamento)', fontsize=14, fontweight='bold', color='#2c3e50')
        axes[1].set_yticks([])
        axes[1].set_xticks([])
        
        cores_classes = ['#e74c3c', '#f39c12', '#f1c40f', '#27ae60']
        for i, patch in enumerate(patches):
            if i < len(cores_classes): patch.set_facecolor(cores_classes[i])
        
        axes[1].text(bins[0] + (bins[1]-bins[0])/2, n[0]*0.5, 'Classe 1\n(Ex: Inferiores)', ha='center', fontsize=10, color='white', fontweight='bold')
        axes[1].text(bins[-2] + (bins[-1]-bins[-2])/2, n[-1]*0.5 + 50, 'Classe 4\n(Ex: Superiores)', ha='center', fontsize=10, color='black', fontweight='bold')
        axes[1].spines['top'].set_visible(False); axes[1].spines['right'].set_visible(False); axes[1].spines['left'].set_visible(False)

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=120)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    def obter_dicionario_siglas(self):
        """Retorna as explicações limpas, em linguagem simples para o glossário do pecuarista."""
        return {
            'AOL_cm2': 'AOL (Área de Olho de Lombo): Mede a quantidade de carne na carcaça. Quanto maior o valor, mais musculoso é o animal e maior será o rendimento de cortes nobres no gancho.',
            'CAR_kg-dia': 'CAR (Consumo Alimentar Residual): Mostra a eficiência alimentar. Um valor menor (ou negativo) é excelente, pois significa que o animal come menos para ganhar o mesmo peso, gerando economia de pasto e ração.',
            'Data_Coleta_Pesagem': 'Data de Coleta: O dia exato em que o animal passou no tronco para avaliação, pesagem ou ultrassom.',
            'Data_Nascimento': 'Data de Nascimento: Usada para calcular a idade exata do animal no momento do manejo, sendo essencial para garantir que a comparação ocorra entre animais da mesma faixa etária.',
            'EGS_mm': 'EGS (Espessura de Gordura Subcutânea): Avalia o acabamento da carcaça no ultrassom. Essencial para proteger a carne no resfriamento do frigorífico e garantir a maciez final.',
            'Estacao': 'Estação do Ano: Época climática em que ocorreu a pesagem (Verão, Outono, Inverno, Primavera), ajudando o sistema a isolar o efeito da seca ou das águas no peso.',
            'Fazenda': 'Fazenda / Retiro: Código numérico ou nome da propriedade/retiro onde o animal estava.',
            'GC': 'GC (Grupo Contemporâneo): O lote de comparação justo. Animais da mesma raça, mesmo sexo, nascidos na mesma época e que comeram o mesmo pasto juntos sob o mesmo manejo.',
            'Geracao': 'Geração: Distância genealógica do animal no pedigree da fazenda. Ajuda a rastrear a evolução genética do rebanho ao longo das safras.',
            'GPD_g-dia': 'GPD (Ganho de Peso Diário): A média de gramas que o animal ganhou por dia entre uma pesagem e outra. É o "velocímetro" de crescimento do animal.',
            'IPP_dias': 'IPP (Idade ao Primeiro Parto): Indicador de precocidade sexual das fêmeas. Quanto menor o número de dias, mais cedo a matriz entrega seu primeiro bezerro, tornando-a mais lucrativa.',
            'itu_dp': 'Variação do Estresse Térmico (DP do ITU): Indica se o clima na região variou muito (dias muito quentes misturados com frescos) ou se manteve constante.',
            'itu_horas_criticas': 'Horas Críticas (Calor): Quantidade de horas que o animal passou sofrendo estresse térmico forte. O calor excessivo tira o apetite e derruba o ganho de peso.',
            'itu_max': 'Pico de Estresse Térmico (ITU Máximo): O pico máximo de calor e abafamento (temperatura + umidade) que os animais enfrentaram no pasto durante o período.',
            'itu_media': 'Estresse Térmico Médio (ITU Médio): Índice que junta Temperatura e Umidade média. Quanto mais alto, mais os animais sofreram no pasto para regular a temperatura do corpo.',
            'itu_min': 'Clima Ameno (ITU Mínimo): O momento mais fresco do período avaliado, indicando o alívio térmico noturno ou a chegada de frentes frias.',
            'Localidade_Bloco': 'Bloco / Localidade: Área específica ou subdivisão macro da fazenda (Ex: Setor Sul, Setor Norte).',
            'Lote_Manejo': 'Lote de Manejo: Grupo gerencial de animais que foram rodados no pasto juntos no dia a dia.',
            'MAR_%': 'Marmoreio (%): A quantidade de gordura entremeada na carne (gordura intramuscular). É o que dá maciez, suculência e agrega valor Premium.',
            'PD_kg': 'Peso à Desmama: Peso do bezerro quando separado da mãe (aos 7-8 meses). Reflete o próprio crescimento do bezerro e a produção de leite da vaca.',
            'PE_cm': 'Perímetro Escrotal: Medida do testículo do touro em centímetros. Reprodutores com maior PE costumam ser mais férteis e geram filhas que entram no cio mais cedo.',
            'Piquete': 'Piquete: A subdivisão exata do pasto onde o lote ficou e se alimentou.',
            'PN_kg': 'Peso ao Nascer: O peso do bezerro assim que nasce. Importante monitorar para evitar bezerros muito grandes que causam problema no parto (distocia).',
            'PREC_SEX': 'Precocidade Sexual: Mede o quão cedo o animal atinge a puberdade e está pronto para a reprodução. Animais precoces aceleram o giro da fazenda.',
            'PROB_3P_%': 'Probabilidade de Prenhez Precoce: A chance de a novilha emprenhar bem cedo, logo na sua primeira estação de monta (geralmente aos 14 meses).',
            'PS_kg': 'Peso ao Sobreano: Peso do animal jovem adulto (perto dos 18 meses). Mostra o potencial de engorda final e o peso próximo à fase de terminação.',
            'Raca': 'Proporção Racial: Grau de sangue da raça principal do animal (Ex: 100% Nelore, 1/2 Angus).',
            'Regime_Alim': 'Regime Alimentar: Como o animal foi tratado nutricionalmente no período (Pasto, Pasto + Suplemento, ou Confinamento).',
            'Sexo': 'Sexo do Animal: Identificação do gênero, convertida em número pelo sistema (ex: 1 Macho, 2 Fêmea).',
            'STAY_%': 'Stayability (Longevidade Reprodutiva): É a capacidade da vaca de permanecer no rebanho produzindo bezerros de forma regular ao longo dos anos. Avalia a "vaca que não falha".',
            'Tipo_Pastagem': 'Pastagem: Qualidade ou tipo específico do capim onde o lote estava pastejando (ex: Brachiaria, Panicum).'
        }

    def gerar_dashboard_html(self, df_merged):
        self.log("Gerando Dashboard HTML Explicativo...")
        df_analysis = df_merged.replace(-999, np.nan).copy()
        
        try:
            logo_path = os.path.join("grafic_image", "logo boigene3.png")
            if os.path.exists(logo_path):
                with open(logo_path, "rb") as image_file:
                    logo_b64 = base64.b64encode(image_file.read()).decode('utf-8')
                logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height: 75px; float: right; margin-left: 20px;">'
            else: logo_html = ''
        except: logo_html = ''

        html_content = f"""
        <html><head>
        <meta charset="UTF-8">
        <title>Auditoria de Dados do Rebanho</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f9fbff; color: #2c3e50; line-height: 1.6; }}
            .header-container {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 4px solid #16a085; padding-bottom: 15px; margin-bottom: 20px; }}
            .header-title {{ margin: 0; color: #2c3e50; font-size: 28px; font-weight: 800; }}
            .header-subtitle {{ margin: 5px 0 0 0; color: #7f8c8d; font-size: 16px; }}
            .info-box {{ background-color: #e8f8f5; border-left: 5px solid #1abc9c; padding: 15px; margin-bottom: 30px; border-radius: 4px; font-size: 14px; }}
            .section {{ background: white; padding: 25px; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #ecf0f1; }}
            .section-title {{ color: #2980b9; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; margin-top: 0; }}
            .explanation {{ font-size: 14px; color: #555; margin-bottom: 15px; }}
            .educational-box {{ background-color: #fdfefe; border: 1px dashed #bdc3c7; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 25px; }}
            .chart-row {{ display: flex; flex-wrap: wrap; justify-content: space-around; }}
            .chart-box {{ width: 48%; margin-bottom: 20px; text-align: center; }}
            .chart-box-wide {{ width: 100%; margin-bottom: 20px; text-align: center; }}
            img.plot {{ max-width: 100%; border-radius: 5px; border: 1px solid #ddd; }}
            img.plot-edu {{ max-width: 80%; border: none; }}
            .stats {{ text-align: left; background: #fdfefe; padding: 15px; border: 1px solid #bdc3c7; border-radius: 5px; font-size: 13px; color: #34495e; margin-top: 10px; }}
            .status-ok {{ color: #27ae60; font-weight: bold; }}
            .status-warn {{ color: #e67e22; font-weight: bold; }}
            .glossario-list {{ columns: 2; -webkit-columns: 2; -moz-columns: 2; list-style-type: none; padding-left: 0; }}
            .glossario-list li {{ margin-bottom: 12px; background: #f4f6f7; padding: 10px; border-radius: 5px; font-size: 13.5px; break-inside: avoid-column; }}
        </style>
        </head><body>
        
        <div class="header-container">
            <div>
                <h1 class="header-title">Relatório de Curadoria de Dados do Rebanho</h1>
                <h3 class="header-subtitle">📍 Identificação: __NOME_FAZENDA_PLACEHOLDER__ | Gerado em: {datetime.now().strftime("%d/%m/%Y")}</h3>
            </div>
            {logo_html}
        </div>

        <div class="info-box">
            <strong>Entendendo este relatório:</strong> Antes de calcularmos as DEPs ou o valor genético de um animal, precisamos garantir que o terreno de comparação seja justo. Se um bezerro pesou mais porque comeu mais ração ou estava num pasto melhor, isso não é genética, é ambiente. Este painel mostra como o sistema limpou os erros de digitação e organizou os animais em grupos justos de comparação.
        </div>
        """

        def create_image_base64(fig):
            buf = BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            plt.close(fig)
            return base64.b64encode(buf.getvalue()).decode('utf-8')

        # SEÇÃO 1: Resumo
        html_content += """
        <div class='section'>
            <h2 class='section-title'>1. Visão Geral do Rebanho Avaliado</h2>
            <p class='explanation'><b>O que é o GC (Grupo Contemporâneo)?</b> É um grupo de animais da mesma raça, mesmo sexo, nascidos na mesma época e criados no mesmo pasto. O gráfico abaixo mostra quantos animais temos em cada um dos maiores lotes válidos.</p>
            <div class='chart-row'>
        """
        if 'Fazenda' in df_analysis.columns:
            fig_f, ax_f = plt.subplots(figsize=(7, 4))
            sns.countplot(data=df_analysis, x='Fazenda', ax=ax_f, palette='Blues_r')
            ax_f.set_title('Volume de Animais por Fazenda/Retiro', fontsize=12)
            ax_f.set_ylabel('Quantidade de Animais')
            img_b64_f = create_image_base64(fig_f)
            html_content += f"<div class='chart-box'><img class='plot' src='data:image/png;base64,{img_b64_f}'/></div>"
            
        if 'GC' in df_analysis.columns:
            fig_g, ax_g = plt.subplots(figsize=(7, 4))
            gc_counts = df_analysis['GC'].value_counts().head(15)
            sns.barplot(x=gc_counts.index, y=gc_counts.values, ax=ax_g, palette='Greens_r')
            ax_g.set_title('Maiores Grupos Contemporâneos (Lotes de Comparação)', fontsize=12)
            ax_g.set_ylabel('Quantidade de Animais')
            ax_g.tick_params(axis='x', rotation=45)
            img_b64_g = create_image_base64(fig_g)
            html_content += f"<div class='chart-box'><img class='plot' src='data:image/png;base64,{img_b64_g}'/></div>"
        html_content += "</div></div>"

        # SEÇÃO 2: Normalidade 
        html_content += f"""
        <div class='section'>
            <h2 class='section-title'>2. Qualidade e Comportamento das Medidas (Pesos, Carcaça, etc.)</h2>
            <div class='educational-box'>
                <p style="margin-top:0; color:#2c3e50; font-weight:bold; font-size:16px;">📚 Entendendo a Validação dos Dados:</p>
                <img class='plot-edu' src='data:image/png;base64,{self.gerar_grafico_explicativo()}'/>
                <p class='explanation' style="margin-bottom:0; text-align:left;">
                Na natureza, a maioria dos bezerros tem um peso médio, poucos são extremamente leves e poucos extremamente pesados, formando um desenho de <b>Sino (gráfico verde)</b>. Se os dados da fazenda formarem esse sino, estão perfeitos. Se o gráfico estiver desequilibrado, o sistema aplica o <b>Agrupamento (gráfico de barras coloridas)</b>, dividindo os animais em "Classes de Desempenho" (ex: Categoria 1, 2, 3...) para evitar que o modelo seja injusto na avaliação genética.
                </p>
            </div>
            <h3 style="color:#7f8c8d; font-size:16px; border-bottom:1px solid #ecf0f1; padding-bottom:5px;">Resultados Reais do seu Rebanho:</h3>
            <div class='chart-row'>
        """
        cols_continuas = ['PN_kg', 'PD_kg', 'PS_kg', 'GPD_g-dia', 'PE_cm', 'AOL_cm2', 'EGS_mm', 'MAR_%']
        dicionario = self.obter_dicionario_siglas()
        
        for col in cols_continuas:
            if col in df_analysis.columns:
                data = df_analysis[col].dropna()
                if len(data) > 5:
                    fig, ax_hist = plt.subplots(figsize=(8, 4))
                    mean_v, std_v = data.mean(), data.std()
                    shapiro_stat, p_val = stats.shapiro(data.sample(min(len(data), 4999), random_state=42)) 
                    # Pega o nome explicativo do dicionário antes dos dois pontos (:)
                    nome_bonito = dicionario.get(col, col).split(':')[0]

                    if p_val > 0.05:
                        sns.histplot(data, kde=True, color='#3498db', bins=20, ax=ax_hist)
                        ax_hist.set_title(f'{nome_bonito} - Comportamento em Sino', fontsize=12)
                        ax_hist.set_xlabel('Medida')
                        ax_hist.set_ylabel('Volume de Animais')
                        stats_text = (f"<b>Média do Rebanho:</b> {mean_v:.1f} | <b>Variação Comum:</b> para mais ou menos {std_v:.1f}<br>"
                                      f"<span class='status-ok'>✓ Aprovado: Os dados formaram a curva de sino esperada. Mantidos os números originais.</span>")
                    else:
                        try:
                            cat_series, bins = pd.qcut(data, q=4, labels=False, retbins=True, duplicates='drop')
                            df_analysis[col] = cat_series + 1
                            sns.countplot(x=df_analysis[col], ax=ax_hist, palette='YlOrRd')
                            ax_hist.set_title(f'{nome_bonito} - Dados Agrupados em Classes', fontsize=12)
                            ax_hist.set_xlabel('Classe de Manejo (1=Inferior, 4=Superior)')
                            ax_hist.set_ylabel('Volume de Animais')
                            stats_text = (f"<span class='status-warn'>⚠️ Ajuste de Rota Aplicado:</span> O volume de dados não formou o sino perfeito.<br>"
                                          f"<b>Ação do Sistema:</b> Para evitar distorções na genética, agrupamos os animais em {len(bins)-1} classes justas.")
                        except:
                            sns.histplot(data, kde=False, color='gray', bins=10, ax=ax_hist)
                            stats_text = "Dados insuficientes para agrupamento detalhado."

                    img_b64 = create_image_base64(fig)
                    html_content += f"<div class='chart-box'><img class='plot' src='data:image/png;base64,{img_b64}'/><div class='stats'>{stats_text}</div></div>"
        html_content += "</div></div>"

        # SEÇÃO 3: Correlação
        html_content += """
        <div class='section'>
            <h2 class='section-title'>3. Como as características caminham juntas (Correlação)</h2>
            <p class='explanation'><b>Termômetro de Relacionamento:</b> Este mapa de calor mostra se duas coisas costumam acontecer juntas na fazenda. <br>
            🟦 <b>Tons Azuis (Frio):</b> Quando uma sobe, a outra desce (ex: se o estresse térmico sobe, o ganho de peso cai).<br>
            🟥 <b>Tons Vermelhos (Quente):</b> Caminham juntas de mãos dadas (ex: bezerros mais pesados na desmama tendem a ser mais pesados no sobreano).</p>
        """
        cols_para_corr = [c for c in df_analysis.columns if pd.api.types.is_numeric_dtype(df_analysis[c])]
        
        if len(cols_para_corr) > 1:
            fig_corr, ax_corr = plt.subplots(figsize=(12, 10))
            corr_matrix = df_analysis[cols_para_corr].corr()
            sns.heatmap(corr_matrix, annot=False, cmap='coolwarm', ax=ax_corr, center=0, 
                        cbar_kws={'label': 'Nível de Correlação'}, linewidths=.5)
            ax_corr.set_title('Mapa de Correlação Geral', fontsize=14)
            img_b64_corr = create_image_base64(fig_corr)
            html_content += f"<div class='chart-box-wide'><img class='plot' src='data:image/png;base64,{img_b64_corr}'/></div>"
        html_content += "</div>"

        # SEÇÃO 4: Dicionário e Siglas
        html_content += """
        <div class='section'>
            <h2 class='section-title'>4. Dicionário do Campo: O que significa cada sigla?</h2>
            <p class='explanation'>Consulte a lista abaixo para entender o nome original de todas as variáveis que apareceram nos gráficos e no Mapa de Correlação acima.</p>
            <ul class='glossario-list'>
        """
        
        cols_para_corr.sort()
        for col in cols_para_corr:
            explicacao = dicionario.get(col, "Variável técnica do sistema para modelagem.")
            html_content += f"<li><strong style='color:#16a085; font-size:15px;'>{col}</strong> ➔ {explicacao}</li>"
            
        html_content += "</ul></div></body></html>"

        return html_content, df_analysis

    def executar(self, f_ped, f_amb, f_fen, f_gen, progress_bar=None):
        def update_progress(percent, message):
            if progress_bar:
                progress_bar.progress(percent, text=message)
                
        try:
            update_progress(5, "Lendo arquivos base de Pedigree...")
            d_ped = pd.read_csv(f_ped, sep=';')
            
            update_progress(10, "Lendo arquivos de Ambiente e Clima...")
            d_amb = pd.read_csv(f_amb, sep=';')
            
            update_progress(15, "Lendo dados de Pesagens e Fenótipos...")
            d_fen = pd.read_csv(f_fen, sep=';')
            
            update_progress(20, "Lendo dados de Genótipos...")
            d_gen = pd.read_csv(f_gen, sep=';')

            update_progress(30, "Tratando e padronizando identificações (Pedigree)...")
            res_ped = self.tratar_pedigree(d_ped)
            
            update_progress(45, "Ajustando Grupos Contemporâneos (Ambiente)...")
            res_amb = self.tratar_ambiente(d_amb, res_ped)
            
            update_progress(60, "Identificando outliers e limpando dados fora da curva (Fenótipos)...")
            res_fen = self.tratar_fenotipos(d_fen, res_amb) 
            
            update_progress(70, "Validando painéis moleculares (Genótipos)...")
            res_gen = self.tratar_genotipos(d_gen)

            update_progress(75, "Consolidando valores nulos para cálculo genético...")
            amb_final = self.finalizar(res_amb, "Ambiente")

            update_progress(80, "Cruzando planilhas de Ambiente, Fenótipos e Pedigree...")
            cols_descritivas = ['Sexo', 'Geracao', 'Raca', 'Data_Nascimento']
            cols_ped_to_merge = ['ID_Animal'] + [c for c in cols_descritivas if c in res_ped.columns]
            df_ped_info = res_ped[cols_ped_to_merge].copy()

            cols_pedigree_strict = [c for c in ['ID_Animal', 'ID_Pai', 'ID_Mae'] if c in res_ped.columns]
            ped_final = self.finalizar(res_ped[cols_pedigree_strict].copy(), "Pedigree")

            res_fen_merged = pd.merge(res_fen, amb_final, on='ID_Animal', how='left')
            res_fen_merged = pd.merge(res_fen_merged, df_ped_info, on='ID_Animal', how='left')
            
            update_progress(90, "Gerando Dashboard HTML Explicativo e Gráficos de Qualidade...")
            dashboard_html_string, res_fen_merged_transf = self.gerar_dashboard_html(res_fen_merged)
            fen_final = self.finalizar(res_fen_merged_transf, "Fenótipos (Geral)")

            update_progress(100, "✅ Finalizado com sucesso! Preparando visualização...")
            return {
                "pedigree": ped_final, 
                "ambiente": amb_final,
                "fenotipos": fen_final, 
                "genotipos": res_gen,
                "logs": self.logs,
                "excluidos": pd.DataFrame(self.registros_excluidos),
                "faltantes": pd.DataFrame(self.registros_faltantes),
                "alertas": pd.DataFrame(self.alertas_biologicos), 
                "dashboard_html": dashboard_html_string 
            }
        except Exception as e:
            self.log(f"Erro Crítico: {str(e)}", "ERRO")
            if progress_bar:
                progress_bar.progress(100, text=f"❌ Erro Crítico: {str(e)}")
            return None

# ==============================================================================
# --- FUNÇÃO DE RENDERIZAÇÃO DA INTERFACE (STREAMLIT) ---
# ==============================================================================
def render_tratamento_module():
    st.markdown("""<style>.block-container { padding-top: 1.5rem !important; }</style>""", unsafe_allow_html=True)

    st.title("🚜 Painel de Auditoria e Limpeza de Dados")
    st.markdown("""
    **Bem-vindo ao centro de tratamento de dados.** Antes de passarmos esses números para as avaliações genéticas complexas, 
    nós precisamos garantir que tudo faz sentido. Este sistema lê os arquivos brutos da fazenda, corrige erros comuns de digitação de balança, 
    identifica quais animais foram criados exatamente sob as mesmas condições de pasto e clima, e separa os "pontos fora da curva" que podem prejudicar uma avaliação justa do seu touro ou matriz.
    """)
    st.divider()
    
    if 'dados_processados' not in st.session_state:
        st.session_state.dados_processados = None
    
    if st.session_state.dados_processados:
        col_msg, col_bt = st.columns([3, 1])
        res = st.session_state.dados_processados
        data_inicio = res.get('data_inicio', 'N/A')
        data_fim = res.get('data_fim', 'N/A')
        
        col_msg.success(f"✅ **Pronto! A faxina nos dados foi concluída com sucesso.**\n\n**Iniciado em:** {data_inicio} | **Finalizado em:** {data_fim}")
        
        # --- AVISO VISUAL DE SEGURANÇA NO DISCO ---
        workspace_dir = st.session_state.get('workspace_dir')
        if workspace_dir and os.path.exists(workspace_dir):
            st.info(f"💾 **Segurança Ativa:** Os 4 arquivos padronizados foram salvos fisicamente na pasta do projeto e as próximas etapas (Qualidade e RENUMF90) já estão destravadas no menu.")
            
        if col_bt.button("🔄 Iniciar Nova Faxina de Dados", use_container_width=True):
            st.session_state.dados_processados = None
            st.rerun()

        # --- BLOCO DE ALERTAS BIOLÓGICOS (PILARES 1, 2, 3 e 5) ---
        if not res['alertas'].empty:
            st.error(f"🧬 ALERTA BIOLÓGICO: Detectamos {len(res['alertas'])} inconsistências graves que quebram a lógica da natureza. **Nós NÃO apagamos esses dados**, mas você precisa revisá-los urgentemente na fazenda.")
            with st.expander("🚨 Ver Relatório de Alertas Biológicos e Estruturais (ABRA AQUI)"):
                st.markdown("Esta lista mostra animais que constam como filhos deles mesmos, animais que 'encolheram' de tamanho ao invés de crescer, ou touros cadastrados como fêmeas.")
                st.dataframe(res['alertas'])
                csv_alertas = res['alertas'].to_csv(sep=';', index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório de Alertas Biológicos (Excel/CSV)", csv_alertas, "alertas_biologicos_fazenda.csv", "text/csv", use_container_width=True)
            
        if not res['excluidos'].empty:
            st.warning(f"⚠️ Atenção: Separamos {len(res['excluidos'])} registros removidos (Outliers extremos, Enfermaria ou Duplicatas).")
            with st.expander("📋 Ver Animais Removidos da Análise (Pontos fora da curva ou Enfermaria)"):
                st.markdown("Recomendamos que você baixe esta planilha e entregue ao responsável pelos apontamentos na fazenda para verificação.")
                st.dataframe(res['excluidos'])
                csv_excluidos = res['excluidos'].to_csv(sep=';', index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório de Erros e Exclusões (Excel/CSV)", csv_excluidos, "animais_com_erro.csv", "text/csv", use_container_width=True)
                
        if not res['faltantes'].empty:
            st.info(f"🔍 Auditoria de Dados Faltantes: Identificamos {len(res['faltantes'])} ocorrências de dados em branco. Preenchidos com -999 para o BLUPF90 assumir o controle.")
            with st.expander("🔎 Ver Relatório de Dados Faltantes (-999)"):
                st.markdown("Estes são os animais que estão com medidas em branco (NaN). O BLUPF90 vai ignorar inteligentemente o fenótipo deles. Baixe a planilha caso queira corrigir os buracos na fonte.")
                st.dataframe(res['faltantes'])
                csv_faltantes = res['faltantes'].to_csv(sep=';', index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório de Faltantes (-999)", csv_faltantes, "animais_dados_faltantes.csv", "text/csv", use_container_width=True)
    
    if not st.session_state.dados_processados:
        st.info("Insira as planilhas baixadas do sistema da fazenda (em formato .csv) nas caixas abaixo:")
        
        # --- NOVO: Integração com Workspace da Etapa 1 ---
        workspace_dir = st.session_state.get('workspace_dir')
        caminho_amb_auto = os.path.join(workspace_dir, "ambiente_comITU.csv") if workspace_dir else None
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("1. Dados Físicos do Animal")
            f_fen = st.file_uploader("Fenótipos (Pesagens, Ultrassom de Carcaça, etc.)", key='main_fen')
            f_gen = st.file_uploader("Genótipos (Informações de Laboratório/DNA)", key='main_gen')
        with c2:
            st.subheader("2. Origem e Clima")
            f_ped = st.file_uploader("Pedigree (Genealogia: Quem é pai e mãe)", key='main_ped')
            
            # Checa se o arquivo de ambiente já foi gerado e salvo no disco pela Etapa 1
            if caminho_amb_auto and os.path.exists(caminho_amb_auto):
                st.success("📁 **'ambiente_comITU.csv'** carregado automaticamente do seu Projeto (Etapa 1)!")
                f_amb = st.file_uploader("Opcional: Subir outro arquivo de Ambiente para substituir o automático?", key='main_amb')
                # Se o usuário não subiu um novo, o sistema vai usar o caminho físico do arquivo automático
                amb_input = f_amb if f_amb is not None else caminho_amb_auto
            else:
                f_amb = st.file_uploader("Ambiente (Lote de manejo, Piquete, Estação)", key='main_amb')
                amb_input = f_amb
        
        if st.button("🚀 UNIR E LIMPAR TODOS OS DADOS", use_container_width=True, type="primary"):
            if f_fen and f_gen and f_ped and amb_input:
                inicio_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                st.info(f"⏳ Trabalhando nos arquivos... Iniciado em: **{inicio_str}**")
                
                progress_bar = st.progress(0, text="Iniciando a leitura dos arquivos...")
                
                # Reseta o ponteiro de leitura se os dados vieram do File Uploader (memória RAM)
                f_fen.seek(0); f_gen.seek(0); f_ped.seek(0)
                if hasattr(amb_input, 'seek'):
                    amb_input.seek(0)
                    
                proc = ProcessadorSSGBLUP()
                resultados = proc.executar(f_ped, amb_input, f_fen, f_gen, progress_bar=progress_bar)
                
                if resultados:
                    resultados['data_inicio'] = inicio_str
                    resultados['data_fim'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    
                    # --- NOVO: SALVAMENTO FÍSICO NO WORKSPACE (Destrava os Guardrails) ---
                    if workspace_dir and os.path.exists(workspace_dir):
                        def save_df(df, filename):
                            csv_str = df.to_csv(sep=';', index=False)
                            csv_str = re.sub(r'-999\.0+\b', '-999', csv_str)
                            with open(os.path.join(workspace_dir, filename), "w", encoding='utf-8') as f:
                                f.write(csv_str)
                        
                        # Salvando com a nomenclatura exata exigida pelo Guardrail do BoiGene.py
                        save_df(resultados['ambiente'], "ambiente_tratado.csv")
                        save_df(resultados['fenotipos'], "fenotipos_tratados.csv")  # O guardrail exige plural
                        save_df(resultados['genotipos'], "genotipos_tratado.csv")
                        save_df(resultados['pedigree'], "pedigree_tratado.csv")
                    # --------------------------------------------------------------------
                    
                    st.session_state.dados_processados = resultados
                    st.rerun()
                else:
                    st.error("❌ Ocorreu um erro interno. Verifique se as planilhas não estão vazias ou com formatos muito diferentes do padrão.")
            else: 
                st.error("⚠️ Calma lá! Precisamos das 4 planilhas juntas para cruzar as informações. Adicione os arquivos que faltam.")

    if st.session_state.dados_processados:
        res = st.session_state.dados_processados
        st.divider()
        
        st.subheader("📊 Relatório da Fazenda (Para Impressão)")
        st.markdown("Gere um relatório em PDF bonito e fácil de ler para levar para a reunião de gestão de gado ou para o escritório da fazenda.")
        nome_fazenda = st.text_input("📍 Nome da Propriedade ou Retiro (Vai aparecer no cabeçalho):", value="Fazenda Esperança - Retiro Sul")
        
        if 'dashboard_html' in res:
            html_final = res['dashboard_html'].replace("__NOME_FAZENDA_PLACEHOLDER__", nome_fazenda)
            b64_html = base64.b64encode(html_final.encode('utf-8')).decode('utf-8')
            
            button_html = f"""
            <html><body>
                <button style="display:block;width:100%;padding:14px;background-color:#27ae60;color:white;text-align:center;border-radius:6px;font-weight:bold;font-size:18px;border:none;cursor:pointer;margin-bottom:10px;" onclick="printReport()">🖨️ Abrir e Imprimir Relatório Oficial</button>
                <p style="text-align:center; color:#7f8c8d; font-family:sans-serif; margin-top:0;">Dica: Na tela de impressão, você pode escolher "Salvar como PDF".</p>
                <iframe id="printIframe" style="display:none;"></iframe>
                <script>
                    function printReport() {{
                        var iframe = document.getElementById('printIframe');
                        var doc = iframe.contentWindow.document;
                        doc.open();
                        doc.write(decodeURIComponent(escape(window.atob('{b64_html}'))));
                        doc.close();
                        iframe.contentWindow.focus();
                        setTimeout(function() {{ iframe.contentWindow.print(); }}, 500);
                    }}
                </script>
            </body></html>
            """
            components.html(button_html, height=100)
        
        st.header("💾 Download das Tabelas Finais Prontas para a Avaliação Genética")
        st.markdown("Estes são os arquivos blindados. Sem erros, padronizados matematicamente e prontos para rodar no BLUP/ssGBLUP.")
        cols = st.columns(4)
        
        def convert_df(df): 
            # Exporta para CSV e garante, via Regex, que o Pandas não deixou nenhum -999.0 "escondido" em colunas numéricas contínuas (exigência do BLUPF90)
            csv_str = df.to_csv(sep=';', index=False)
            csv_str = re.sub(r'-999\.0+\b', '-999', csv_str)
            return csv_str.encode('utf-8')
            
        # Nomes dos downloads ajustados para refletir exatamente os nomes gerados no disco/workspace
        cols[0].download_button("Ambiente Corrigido", convert_df(res['ambiente']), "ambiente_tratado.csv", use_container_width=True)
        cols[1].download_button("Fenótipos Corrigidos", convert_df(res['fenotipos']), "fenotipos_tratados.csv", use_container_width=True)
        cols[2].download_button("Genótipos Padronizados", convert_df(res['genotipos']), "genotipos_tratado.csv", use_container_width=True)
        cols[3].download_button("Pedigree Limpo", convert_df(res['pedigree']), "pedigree_tratado.csv", use_container_width=True)