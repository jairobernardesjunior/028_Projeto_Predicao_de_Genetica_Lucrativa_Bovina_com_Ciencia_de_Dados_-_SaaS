import sqlite3
import pandas as pd

# 1. Conectar ao banco de dados
conn = sqlite3.connect('boigene_db.db')
cursor = conn.cursor()

# 2. Carregar os dados originais
df_ambiente = pd.read_sql_query("SELECT * FROM ambiente", conn)
df_fenotipos = pd.read_sql_query("SELECT * FROM fenotipos", conn)
df_pedigree = pd.read_sql_query("SELECT * FROM pedigree", conn)
df_genotipos = pd.read_sql_query("SELECT * FROM genotipos", conn)
df_relacao = pd.read_sql_query("SELECT * FROM relacao_ids", conn)

# 3. Carregar mapeamento dos cadastros
cadastros = {
    'estacao': pd.read_sql_query("SELECT id_estacao, descricao FROM cadastro_estacao", conn),
    'lote': pd.read_sql_query("SELECT id_lote, descricao FROM cadastro_lote_manejo", conn),
    'regime': pd.read_sql_query("SELECT id_regime, descricao FROM cadastro_regime_alim", conn),
    'pastagem': pd.read_sql_query("SELECT id_pastagem, descricao FROM cadastro_pastagem", conn),
    'localidade': pd.read_sql_query("SELECT id_localidade, descricao FROM cadastro_localidade", conn),
    'sexo': pd.read_sql_query("SELECT id_sexo, descricao FROM cadastro_sexo", conn),
    'raca': pd.read_sql_query("SELECT id_raca, descricao FROM cadastro_raca", conn),
    'categoria': pd.read_sql_query("SELECT id_categoria, descricao FROM cadastro_categoria", conn)
}

def criar_mapa_id(df_cadastro, col_id):
    return dict(zip(df_cadastro['descricao'], df_cadastro[col_id]))

# 4. Transformar as colunas e renomear chaves (id_...)
df_ambiente['id_estacao'] = df_ambiente['Estacao'].map(criar_mapa_id(cadastros['estacao'], 'id_estacao'))
df_ambiente['id_lote'] = df_ambiente['Lote_Manejo'].map(criar_mapa_id(cadastros['lote'], 'id_lote'))
df_ambiente['id_regime'] = df_ambiente['Regime_Alim'].map(criar_mapa_id(cadastros['regime'], 'id_regime'))
df_ambiente['id_pastagem'] = df_ambiente['Tipo_Pastagem'].map(criar_mapa_id(cadastros['pastagem'], 'id_pastagem'))
df_ambiente['id_localidade'] = df_ambiente['Localidade_Bloco'].map(criar_mapa_id(cadastros['localidade'], 'id_localidade'))
df_ambiente.rename(columns={'ID_Animal': 'id_animal', 'Fazenda': 'id_fazenda', 'Piquete': 'id_piquete'}, inplace=True)
df_ambiente.drop(columns=['Estacao', 'Lote_Manejo', 'Regime_Alim', 'Tipo_Pastagem', 'Localidade_Bloco'], inplace=True)

df_fenotipos['id_sexo'] = df_fenotipos['Sexo'].map(criar_mapa_id(cadastros['sexo'], 'id_sexo'))
df_fenotipos['id_raca'] = df_fenotipos['Raca'].map(criar_mapa_id(cadastros['raca'], 'id_raca'))
df_fenotipos.rename(columns={'ID_Animal': 'id_animal'}, inplace=True)
df_fenotipos.drop(columns=['Sexo', 'Raca'], inplace=True)

df_pedigree['id_categoria'] = df_pedigree['Categoria'].map(criar_mapa_id(cadastros['categoria'], 'id_categoria'))
df_pedigree.rename(columns={'ID_Animal': 'id_animal', 'ID_Pai': 'id_pai', 'ID_Mae': 'id_mae'}, inplace=True)
df_pedigree.drop(columns=['Categoria'], inplace=True)

df_genotipos.rename(columns={'ID_Animal': 'id_animal'}, inplace=True)
df_relacao.rename(columns={'ID_Animal_Phenotype': 'id_animal_phenotype', 'ID_Animal_Genotype': 'id_animal_genotype'}, inplace=True)

# 5. Dropar as originais e Criar as novas tabelas (com Primary Keys e Foreign Keys)
cursor.executescript("""
DROP TABLE IF EXISTS ambiente;
CREATE TABLE ambiente (
    id_animal INTEGER PRIMARY KEY,
    id_fazenda INTEGER,
    Data_Coleta_Pesagem TEXT,
    id_piquete INTEGER,
    ITU_Media REAL,
    ITU_DP REAL,
    ITU_Max REAL,
    id_estacao INTEGER,
    id_lote INTEGER,
    id_regime INTEGER,
    id_pastagem INTEGER,
    id_localidade INTEGER,
    FOREIGN KEY(id_animal) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_fazenda) REFERENCES cadastro_fazenda(id_fazenda),
    FOREIGN KEY(id_piquete) REFERENCES cadastro_piquete(id_piquete),
    FOREIGN KEY(id_estacao) REFERENCES cadastro_estacao(id_estacao),
    FOREIGN KEY(id_lote) REFERENCES cadastro_lote_manejo(id_lote),
    FOREIGN KEY(id_regime) REFERENCES cadastro_regime_alim(id_regime),
    FOREIGN KEY(id_pastagem) REFERENCES cadastro_pastagem(id_pastagem),
    FOREIGN KEY(id_localidade) REFERENCES cadastro_localidade(id_localidade)
);

DROP TABLE IF EXISTS fenotipos;
CREATE TABLE fenotipos (
    id_animal INTEGER PRIMARY KEY,
    GC TEXT,
    PN_kg REAL,
    PD_kg REAL,
    PS_kg REAL,
    "GPD_g-dia" REAL,
    PE_cm REAL,
    AOL_cm2 REAL,
    EGS_mm REAL,
    "MAR_%" REAL,
    "CAR_kg-dia" REAL,
    PREC_SEX REAL,
    IPP_dias REAL,
    "PROB_3P_%" REAL,
    "STAY_%" REAL,
    Geracao INTEGER,
    Data_Nascimento TEXT,
    id_sexo INTEGER,
    id_raca INTEGER,
    FOREIGN KEY(id_animal) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_sexo) REFERENCES cadastro_sexo(id_sexo),
    FOREIGN KEY(id_raca) REFERENCES cadastro_raca(id_raca)
);

DROP TABLE IF EXISTS pedigree;
CREATE TABLE pedigree (
    id_animal INTEGER PRIMARY KEY,
    id_pai INTEGER,
    id_mae INTEGER,
    id_categoria INTEGER,
    FOREIGN KEY(id_animal) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_pai) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_mae) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_categoria) REFERENCES cadastro_categoria(id_categoria)
);

DROP TABLE IF EXISTS genotipos;
CREATE TABLE genotipos (
    id_animal INTEGER PRIMARY KEY,
    Sequencia_SNP TEXT,
    FOREIGN KEY(id_animal) REFERENCES cadastro_animais(id_animal)
);

DROP TABLE IF EXISTS relacao_ids;
CREATE TABLE relacao_ids (
    id_animal_phenotype INTEGER,
    id_animal_genotype INTEGER,
    PRIMARY KEY (id_animal_phenotype, id_animal_genotype),
    FOREIGN KEY(id_animal_phenotype) REFERENCES cadastro_animais(id_animal),
    FOREIGN KEY(id_animal_genotype) REFERENCES cadastro_animais(id_animal)
);
""")

# 6. Inserir os dados mapeados de volta nas tabelas estruturadas
# if_exists='append' vai jogar os dados do Pandas para as tabelas que acabamos de construir acima
df_ambiente.to_sql('ambiente', conn, if_exists='append', index=False)
df_fenotipos.to_sql('fenotipos', conn, if_exists='append', index=False)
df_pedigree.to_sql('pedigree', conn, if_exists='append', index=False)
df_genotipos.to_sql('genotipos', conn, if_exists='append', index=False)
df_relacao.to_sql('relacao_ids', conn, if_exists='append', index=False)

# Confirmação da transação
conn.commit()
conn.close()

print("Recriação concluída com successo, com os identificadores padronizados e mapeados, além das PRIMARY KEYs e FOREIGN KEYs baseadas nos cadastros!")