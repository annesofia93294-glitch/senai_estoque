import streamlit as st
import pandas as pd
from datetime import datetime
import psycopg2
import requests
from io import BytesIO
from PIL import Image

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gestão de Estoque - SENAI Pro", 
    page_icon="■", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILO VISUAL CORPORATIVO (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button {
        background-color: #004a87;
        color: white;
        border-radius: 4px;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #003366;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM O BANCO DE DADOS EM NUVEM ---
DB_URL = st.secrets["DB_URL"]

def get_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS estoque_pro (
                    id SERIAL PRIMARY KEY,
                    unidade_origem TEXT,
                    unidade_atual TEXT,
                    nome_item TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    unidade_medida TEXT NOT NULL,
                    url_imagem TEXT
                )
            """)
            cursor.execute("ALTER TABLE estoque_pro ADD COLUMN IF NOT EXISTS unidade_origem TEXT;")
            cursor.execute("ALTER TABLE estoque_pro ADD COLUMN IF NOT EXISTS unidade_atual TEXT;")
            
            cursor.execute("""
                DO $$ 
                BEGIN 
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='estoque_pro' and column_name='unidade') THEN
                        UPDATE estoque_pro SET unidade_origem = unidade WHERE unidade_origem IS NULL;
                        UPDATE estoque_pro SET unidade_atual = unidade WHERE unidade_atual IS NULL;
                    END IF;
                END $$;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS movimentacoes_pro (
                    id SERIAL PRIMARY KEY,
                    data_hora TEXT NOT NULL,
                    unidade TEXT NOT NULL,
                    nome_item TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    responsavel TEXT NOT NULL
                )
            """)
            conn.commit()

# Inicialização segura com indicador de carregamento
with st.spinner("Inicializando o sistema e conectando ao banco de dados..."):
    try:
        init_db()
    except Exception as e:
        st.error(f"Erro ao inicializar o banco de dados: {e}")

# CACHE OTIMIZADO
@st.cache_data(ttl=300)
def run_query(query, params=()):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=columns)

def execute_db(query, params=()):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()
    st.cache_data.clear() 

# UPLOAD DE IMAGEM
def upload_imgbb(imagem_upload):
    try:
        img = Image.open(imagem_upload)
        img.thumbnail((800, 800))
        buffer = BytesIO()
        formato = img.format if img.format in ["JPEG", "PNG"] else "JPEG"
        img.save(buffer, format=formato, quality=85)
        buffer.seek(0)
        
        url = "https://api.imgbb.com/1/upload"
        params = {"key": st.secrets["IMGBB_API_KEY"]}
        files = {"image": buffer.getvalue()}
        
        with st.spinner("Enviando imagem para o servidor..."):
            resposta = requests.post(url, params=params, files=files)
            if resposta.status_code == 200:
                return resposta.json()["data"]["url"]
            else:
                st.error("Falha ao enviar imagem.")
                return None
    except Exception as e:
        st.error(f"Erro ao processar imagem: {e}")
        return None

# --- CABEÇALHO COM LOGOTIPO INSTITUCIONAL DO SENAI ---
col_logo, col_titulo = st.columns([1, 4])
with col_logo:
    # URL estável e garantida da logo corporativa do SENAI
    st.image("https://logodownload.org/wp-content/uploads/2019/08/senai-logo-1.png", width=140)
with col_titulo:
    st.title("Sistema Integrado de Estoque")
    st.caption("Controle Corporativo Multiusuário • SENAI Bahia (Barreiras & Luís Eduardo)")

st.divider()

# --- BARRA LATERAL DE NAVEGAÇÃO ---
st.sidebar.markdown("### Menu Principal")
menu = st.sidebar.selectbox(
    "Escolha uma opção",
    ["Visualizar Estoque", "Entrada de Materiais", "Saída / Empréstimo / Edição", "Histórico de Movimentações"]
)

UNIDADES_PADRAO = ["SENAI Barreiras", "SENAI Luis Eduardo", "Almoxarifado Central"]
CATEGORIAS_PADRAO = [
    "Rede de Distribuição", "Motores Elétricos", "Comandos Elétricos", 
    "Ferramentas de Medição", "Ferramentas Elétricas", "Kits Didáticos", "EPIs"
]

# --- TELA 1: CONSULTA DE ESTOQUE ---
if menu == "Visualizar Estoque":
    st.subheader("Catálogo Geral de Materiais")
    
    col1, col2 = st.columns(2)
    with col1:
        filtro_unidade = st.selectbox("Filtrar por Unidade Atual", ["Todas"] + UNIDADES_PADRAO)
    with col2:
        filtro_categoria = st.selectbox("Filtrar por Categoria", ["Todas"] + CATEGORIAS_PADRAO)
    
    query = "SELECT id, unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem FROM estoque_pro WHERE 1=1"
    params = []
    
    if filtro_unidade != "Todas":
        query += " AND unidade_atual = %s"
        params.append(filtro_unidade)
    if filtro_categoria != "Todas":
        query += " AND categoria = %s"
        params.append(filtro_categoria)
        
    with st.spinner("Carregando estoque..."):
        df_estoque = run_query(query, tuple(params))
    
    if not df_estoque.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Itens Listados", len(df_estoque))
        m2.metric("Soma de Quantidades", int(df_estoque['quantidade'].sum()))
        m3.metric("Categorias Envolvidas", df_estoque['categoria'].nunique())
        st.markdown("<br>", unsafe_allow_html=True)

        c_cod, c_img, c_desc, c_cat, c_loc, c_qtd = st.columns([1, 2, 3, 2, 2, 2])
        c_cod.write("**CÓDIGOS**")
        c_img.write("**FOTO**")
        c_desc.write("**MATERIAL**")
        c_cat.write("**CATEGORIA**")
        c_loc.write("**LOCALIZAÇÃO / ORIGEM**")
        c_qtd.write("**QUANTIDADE**")
        st.divider()

        for _, row in df_estoque.iterrows():
            c_cod, c_img, c_desc, c_cat, c_loc, c_qtd = st.columns([1, 2, 3, 2, 2, 2], vertical_alignment="center")
            
            c_cod.write(f"#{row['id']}")
            
            url_img = row.get("url_imagem")
            if url_img and str(url_img).startswith("http"):
                try:
                    c_img.image(url_img, width=70)
                except Exception:
                    c_img.caption("Indisponível")
            else:
                c_img.caption("Sem foto")
                
            c_desc.write(row["nome_item"])
            c_cat.write(row["categoria"])
            
            origem = row.get("unidade_origem", "Desconhecida")
            atual = row.get("unidade_atual", "Desconhecida")
            
            if origem != atual:
                c_loc.markdown(f"**{atual}**<br><span style='color:#c0392b; font-size:12px;'>Origem: {origem}</span>", unsafe_allow_html=True)
            else:
                c_loc.write(atual)
                
            c_qtd.write(f"**{row['quantidade']}** {row['unidade_medida']}")
            st.divider()
    else:
        st.info("Nenhum material encontrado com os filtros selecionados.")

# --- TELA 2: ENTRADA DE MATERIAIS ---
elif menu == "Entrada de Materiais":
    st.subheader("Cadastrar Novo Material ou Adicionar Lote")
    
    with st.form("form_entrada", clear_on_submit=False):
        col_a, col_b = st.columns(2)
        with col_a:
            unidade = st.selectbox("Unidade Destino / Proprietária", UNIDADES_PADRAO)
            nome_item = st.text_input("Nome do Material / Equipamento").strip().title()
            categoria = st.selectbox("Categoria", CATEGORIAS_PADRAO)
        with col_b:
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
            un_medida = st.selectbox("Unidade de Medida", ["Unidade (un)", "Metros (m)", "Quilogramas (kg)", "Litros (L)", "Caixa (cx)"])
            imagem_upload = st.file_uploader("Foto do Material (Opcional)", type=["png", "jpg", "jpeg"])
        
        submitted = st.form_submit_button("Registrar Entrada no Sistema")
        
        if submitted:
            if not nome_item:
                st.error("Por favor, preencha o nome do material.")
            else:
                data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                url_img = None
                if imagem_upload is not None:
                    url_img = upload_imgbb(imagem_upload)
                
                item_existente = run_query(
                    "SELECT id, quantidade FROM estoque_pro WHERE unidade_atual = %s AND nome_item = %s",
                    (unidade, nome_item)
                )
                
                if not item_existente.empty:
                    item_id = int(item_existente.iloc[0]["id"])
                    nova_qtd = int(item_existente.iloc[0]["quantidade"]) + quantidade
                    
                    if url_img:
                        execute_db("UPDATE estoque_pro SET quantidade = %s, url_imagem = %s WHERE id = %s", (nova_qtd, url_img, item_id))
                    else:
                        execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (nova_qtd, item_id))
                else:
                    execute_db(
                        "INSERT INTO estoque_pro (unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (unidade, unidade, nome_item, categoria, quantidade, un_medida, url_img)
                    )
                
                execute_db(
                    "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                    (data_atual, unidade, nome_item, "ENTRADA", quantidade, "Sistema")
                )
                st.success("Entrada registrada com sucesso.")

# --- TELA 3: SAÍDA, EMPRÉSTIMO E EDIÇÃO ---
elif menu == "Saída / Empréstimo / Edição":
    st.subheader("Baixa, Empréstimo entre Unidades e Edição de Cadastros")
    
    unidade_selecionada = st.selectbox("Selecione a Unidade onde o material está fisicamente", UNIDADES_PADRAO)
    
    with st.spinner("Buscando itens da unidade..."):
        itens_disponiveis = run_query(
            "SELECT id, unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem FROM estoque_pro WHERE unidade_atual = %s", 
            (unidade_selecionada,)
        )
    
    if itens_disponiveis.empty:
        st.warning("Nenhum item cadastrado nesta unidade.")
    else:
        opcoes_itens = {row["id"]: f"{row['nome_item']} (Qtd: {row['quantidade']} {row['unidade_medida']}) - Origem: {row['unidade_origem']}" for _, row in itens_disponiveis.iterrows()}
        item_id_selecionado = st.selectbox(
            "Selecione o Material", options=list(opcoes_itens.keys()), format_func=lambda x: opcoes_itens[x]
        )
        
        dados_item = itens_disponiveis[itens_disponiveis["id"] == item_id_selecionado].iloc[0]
        nome_selecionado, qtd_atual, imagem_atual = dados_item["nome_item"], dados_item["quantidade"], dados_item["url_imagem"]
        origem_atual = dados_item["unidade_origem"]
        
        col_img, col_info = st.columns([1, 2])
        with col_img:
            if imagem_atual and str(imagem_atual).startswith("http"):
                try:
                    st.image(imagem_atual, caption=nome_selecionado, width=200)
                except Exception:
                    st.caption("Sem foto válida")
            else:
                st.info("Sem foto cadastrada.")
        with col_info:
            st.markdown(f"**Item:** {nome_selecionado}")
            st.markdown(f"**Categoria:** {dados_item['categoria']}")
            st.markdown(f"**Estoque Disponível:** {qtd_atual} {dados_item['unidade_medida']}")
            st.markdown(f"**Unidade Proprietária (Origem):** {origem_atual}")
            if origem_atual != unidade_selecionada:
                st.warning(f"Este material está emprestado e pertence originalmente a {origem_atual}.")

        st.divider()
        acao = st.radio("Escolha a Operação:", ["Dar Baixa (Saída Definitiva)", "Empréstimo / Enviar para Outra Unidade", "Editar Informações do Item"])
        
        if acao == "Dar Baixa (Saída Definitiva)":
            quantidade_saida = st.number_input("Quantidade para Retirar", min_value=1, max_value=int(qtd_atual) if qtd_atual > 0 else 1, step=1)
            if st.button("Confirmar Saída"):
                if quantidade_saida > qtd_atual:
                    st.error("Quantidade solicitada maior que o estoque atual.")
                else:
                    nova_qtd = int(qtd_atual) - int(quantidade_saida)
                    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    if nova_qtd == 0:
                        execute_db("DELETE FROM estoque_pro WHERE id = %s", (item_id_selecionado,))
                    else:
                        execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (nova_qtd, item_id_selecionado))
                        
                    execute_db(
                        "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                        (data_atual, unidade_selecionada, nome_selecionado, "SAÍDA", quantidade_saida, "Responsável Local")
                    )
                    st.success("Saída registrada com sucesso.")
                    st.rerun()

        elif acao == "Empréstimo / Enviar para Outra Unidade":
            unidades_destino = [u for u in UNIDADES_PADRAO if u != unidade_selecionada]
            nova_unidade_atual = st.selectbox("Enviar para qual Unidade?", unidades_destino)
            qtd_envio = st.number_input("Quantidade a Enviar por Empréstimo", min_value=1, max_value=int(qtd_atual) if qtd_atual > 0 else 1, step=1)
            
            if st.button("Confirmar Envio / Empréstimo"):
                data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if qtd_envio == qtd_atual:
                    execute_db("UPDATE estoque_pro SET unidade_atual = %s WHERE id = %s", (nova_unidade_atual, item_id_selecionado))
                else:
                    nova_qtd_origem = int(qtd_atual) - int(qtd_envio)
                    execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (nova_qtd_origem, item_id_selecionado))
                    
                    ja_tem = run_query("SELECT id, quantidade FROM estoque_pro WHERE unidade_atual = %s AND nome_item = %s", (nova_unidade_atual, nome_selecionado))
                    if not ja_tem.empty:
                        id_destino = int(ja_tem.iloc[0]["id"])
                        q_nova = int(ja_tem.iloc[0]["quantidade"]) + int(qtd_envio)
                        execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (q_nova, id_destino))
                    else:
                        execute_db(
                            "INSERT INTO estoque_pro (unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (origem_atual, nova_unidade_atual, nome_selecionado, dados_item['categoria'], qtd_envio, dados_item['unidade_medida'], imagem_atual)
                        )

                execute_db(
                    "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                    (data_atual, f"{unidade_selecionada} -> {nova_unidade_atual}", nome_selecionado, "EMPRÉSTIMO/TRANSFERÊNCIA", qtd_envio, "Responsável Local")
                )
                st.success(f"Material transferido com sucesso para {nova_unidade_atual}.")
                st.rerun()

        elif acao == "Editar Informações do Item":
            novo_nome = st.text_input("Corrigir Nome do Material", value=nome_selecionado)
            nova_qtd_total = st.number_input("Corrigir Quantidade Total", min_value=0, value=int(qtd_atual), step=1)
            nova_imagem = st.file_uploader("Atualizar Foto", type=["png", "jpg", "jpeg"])
            
            if st.button("Salvar Alterações Cadastrais"):
                if nova_imagem is not None:
                    novo_link = upload_imgbb(nova_imagem)
                    if novo_link:
                        execute_db("UPDATE estoque_pro SET nome_item = %s, quantidade = %s, url_imagem = %s WHERE id = %s",
                                   (novo_nome.strip().title(), nova_qtd_total, novo_link, item_id_selecionado))
                else:
                    execute_db("UPDATE estoque_pro SET nome_item = %s, quantidade = %s WHERE id = %s",
                               (novo_nome.strip().title(), nova_qtd_total, item_id_selecionado))
                st.success("Alterações salvas com sucesso.")
                st.rerun()

# --- TELA 4: HISTÓRICO E AUDITORIA ---
elif menu == "Histórico de Movimentações":
    st.subheader("Auditoria de Movimentações (Entradas, Saídas e Empréstimos)")
    with st.spinner("Carregando histórico..."):
        df_logs = run_query("SELECT data_hora, unidade, nome_item, tipo, quantidade FROM movimentacoes_pro ORDER BY id DESC")
    if not df_logs.empty:
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada até o momento.")