import streamlit as st
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import tempfile
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gemini ChatApp - Análise de Arquivos",
    page_icon="🤖",
    layout="wide"
)

def init_api():
    """Inicializa a API do Gemini lendo a chave de forma segura."""
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        genai.configure(api_key=api_key)
    except KeyError:
        st.error("⚠️ Chave da API não encontrada. Crie o arquivo `.streamlit/secrets.toml` com sua chave gratuita.")
        st.stop()

def initialize_session_state():
    """Inicializa o histórico e busca dinamicamente um modelo válido."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "arquivo_gemini" not in st.session_state:
        st.session_state.arquivo_gemini = None
    
    if "chat_session" not in st.session_state:
        with st.spinner("Buscando modelos disponíveis na sua conta..."):
            modelos_disponiveis = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            if not modelos_disponiveis:
                st.error("⚠️ Nenhum modelo de texto habilitado encontrado para esta chave de API.")
                st.stop()
            
            nome_modelo = next(
                (m for m in modelos_disponiveis if 'flash' in m), 
                next((m for m in modelos_disponiveis if 'pro' in m), modelos_disponiveis[0])
            )
            
            nome_modelo_limpo = nome_modelo.replace("models/", "")
            model = genai.GenerativeModel(nome_modelo_limpo)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.modelo_em_uso = nome_modelo_limpo

def upload_para_gemini(uploaded_file):
    """Salva o arquivo do Streamlit temporariamente e envia para a API do Gemini."""
    try:
        # Cria um arquivo temporário preservando a extensão original
        extensao = uploaded_file.name.split('.')[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extensao}") as temp_file:
            temp_file.write(uploaded_file.read())
            caminho_temp = temp_file.name

        # Envia para o Google
        with st.spinner(f"Fazendo upload de '{uploaded_file.name}' para a nuvem do Google..."):
            arquivo_gemini = genai.upload_file(path=caminho_temp, display_name=uploaded_file.name)
        
        # Remove o arquivo temporário do seu disco
        os.remove(caminho_temp)
        return arquivo_gemini
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        return None

def setup_sidebar():
    """Configura o menu lateral com uploader de arquivos e controles."""
    with st.sidebar:
        st.title("⚙️ Configurações & Arquivos")
        st.markdown(f"**Modelo ativo:** `{st.session_state.get('modelo_em_uso', 'Desconhecido')}`")
        st.markdown("---")
        
        # --- UPLOAD DE ARQUIVOS ---
        st.subheader("📎 Anexar Contexto")
        arquivo_usuario = st.file_uploader(
            "Faça upload de um arquivo para o Gemini avaliar", 
            type=["pdf", "png", "jpg", "jpeg", "txt", "csv", "py"]
        )
        
        if arquivo_usuario:
            # Só faz o upload se for um arquivo novo
            if st.session_state.arquivo_gemini is None or st.session_state.arquivo_gemini.display_name != arquivo_usuario.name:
                novo_arquivo = upload_para_gemini(arquivo_usuario)
                if novo_arquivo:
                    st.session_state.arquivo_gemini = novo_arquivo
                    st.success("✅ Arquivo carregado e pronto para análise!")
        else:
            # Limpa o arquivo da sessão se o usuário remover do uploader
            st.session_state.arquivo_gemini = None
            
        st.markdown("---")
        
        if st.button("🗑️ Limpar Conversa", use_container_width=True):
            st.session_state.messages = []
            # Correção: usando o modelo descoberto em vez do nome fixo que dava erro 404
            model = genai.GenerativeModel(st.session_state.modelo_em_uso)
            st.session_state.chat_session = model.start_chat(history=[])
            st.success("Histórico limpo!")
            st.rerun()

def render_chat_interface():
    """Renderiza a interface de chat lidando com texto e arquivos anexados."""
    st.title("🤖 Chat Avançado com Gemini")
    
    if st.session_state.arquivo_gemini:
        st.info(f"📄 O arquivo **{st.session_state.arquivo_gemini.display_name}** está anexado. Você pode fazer perguntas sobre ele!")
    else:
        st.markdown("Faça suas perguntas. Lembre-se do limite de 15 mensagens por minuto na versão Free.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Digite sua pergunta ou instrução sobre o arquivo..."):
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analisando e gerando resposta..."):
                try:
                    # Se houver um arquivo no state, enviamos ele JUNTO com o prompt em uma lista
                    conteudo_envio = prompt
                    if st.session_state.arquivo_gemini:
                        conteudo_envio = [st.session_state.arquivo_gemini, prompt]
                        
                    response = st.session_state.chat_session.send_message(conteudo_envio)
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                except ResourceExhausted:
                    st.error("⏳ **Limite de requisições atingido!** Aguarde alguns segundos e tente novamente.")
                    st.session_state.messages.pop()
                except Exception as e:
                    st.error(f"⚠️ Ocorreu um erro: {e}")
                    st.session_state.messages.pop()

def main():
    init_api()
    initialize_session_state()
    setup_sidebar()
    render_chat_interface()

if __name__ == "__main__":
    main()