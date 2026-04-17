import sqlite3
import os

# Caminho do banco de dados (ajuste se necessário)
DB_DIR = r"C:\boigene\bd"
DB_PATH = os.path.join(DB_DIR, "boigene_db.db")

def atualizar_descricoes_animais():
    try:
        # Conecta ao banco de dados
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Executa o comando UPDATE
        # Em SQLite, '||' é o operador de concatenação de strings
        sql_update = """
            UPDATE cadastro_animais 
            SET descricao_animal = 'animal ' || CAST(id_animal AS TEXT)
        """
        
        cursor.execute(sql_update)
        
        # Confirma as alterações no banco
        conn.commit()
        
        # Verifica quantas linhas foram alteradas
        linhas_afetadas = cursor.rowcount
        print(f"Sucesso! {linhas_afetadas} animais foram atualizados.")
        
    except sqlite3.Error as e:
        print(f"Ocorreu um erro no banco de dados: {e}")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
    finally:
        # Fecha a conexão com o banco
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    # ⚠️ RECOMENDAÇÃO: Faça um backup do arquivo boigene_db.db antes de rodar!
    print("Iniciando atualização...")
    atualizar_descricoes_animais()