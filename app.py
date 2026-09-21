import streamlit as st
import pandas as pd
from datetime import datetime, date
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

# --- ESTILO VISUAL CORPORATIVO E MENU AZUL SENAI (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    
    [data-testid="stSidebar"] {
        background-color: #004a87;
        color: white;
    }
    [data-testid="stSidebar"] .stMarkdown h3, 
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] .stSelectbox div {
        color: white !important;
    }
    
    .stButton>button {
        background-color: #004a87;
        color: white;
        border-radius: 4px;
        font-weight: 600;
        border: none;
        padding: 0.4rem 0.8rem;
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

def padronizar_unidade(nome_unidade):
    if not nome_unidade:
        return "Almoxarifado Central"
    n = str(nome_unidade).strip().title()
    if "Luiz" in n or "Luis" in n or "Eduardo" in n:
        return "SENAI Luis Eduardo"
    if "Barreiras" in n:
        return "SENAI Barreiras"
    return n

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
                    url_imagem TEXT,
                    pendente_devolucao BOOLEAN DEFAULT FALSE
                )
            """)
            
            cursor.execute("ALTER TABLE estoque_pro ADD COLUMN IF NOT EXISTS unidade_origem TEXT;")
            cursor.execute("ALTER TABLE estoque_pro ADD COLUMN IF NOT EXISTS unidade_atual TEXT;")
            cursor.execute("ALTER TABLE estoque_pro ADD COLUMN IF NOT EXISTS pendente_devolucao BOOLEAN DEFAULT FALSE;")
            
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

with st.spinner("Inicializando o sistema e conectando ao banco de dados..."):
    try:
        init_db()
    except Exception as e:
        st.error(f"Erro ao inicializar o banco de dados: {e}")

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

# --- CABEÇALHO ---
col_logo, col_titulo = st.columns([1, 4])
with col_logo:
    st.image("https://logodownload.org/wp-content/uploads/2019/08/senai-logo-1.png", width=140)
with col_titulo:
    st.title("Sistema Integrado de Estoque")
    st.caption("Controle Corporativo Multiusuário • SENAI Bahia (Barreiras & Luís Eduardo)")

st.divider()

# --- BARRA LATERAL ---
st.sidebar.markdown("### Menu Principal")
menu = st.sidebar.selectbox(
    "Escolha uma opção",
    ["Visualizar Estoque", "Entrada de Materiais", "Saída / Empréstimo", "Devolução em Lote", "Histórico de Movimentações"]
)

UNIDADES_PADRAO = ["SENAI Barreiras", "SENAI Luis Eduardo", "Almoxarifado Central"]
CATEGORIAS_PADRAO = [
    "Rede de Distribuição", "Motores Elétricos", "Comandos Elétricos", 
    "Ferramentas de Medição", "Ferramentas Elétricas", "Kits Didáticos", "EPIs"
]

# --- TELA 1: CONSULTA DE ESTOQUE ---
if menu == "Visualizar Estoque":
    st.subheader("Catálogo Geral de Materiais e Conferência")
    
    col1, col2 = st.columns(2)
    with col1:
        filtro_unidade = st.selectbox("Filtrar por Unidade Atual (Obrigatório)", ["Selecione uma Unidade"] + UNIDADES_PADRAO)
    with col2:
        filtro_categoria = st.selectbox("Filtrar por Categoria (Opcional)", ["Todas"] + CATEGORIAS_PADRAO)
    
    if filtro_unidade == "Selecione uma Unidade":
        st.info("Por favor, selecione uma unidade no filtro acima para carregar os itens correspondentes.")
    else:
        unidade_filtro_padrao = padronizar_unidade(filtro_unidade)
        query = "SELECT id, unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem, pendente_devolucao FROM estoque_pro WHERE unidade_atual = %s ORDER BY id DESC"
        params = [unidade_filtro_padrao]
        
        if filtro_categoria != "Todas":
            query += " AND categoria = %s"
            params.append(filtro_categoria)
            
        with st.spinner("Carregando estoque atualizado..."):
            df_estoque = run_query(query, tuple(params))
        
        if not df_estoque.empty:
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(f"""<div style="background-color:#eef4fb; padding:12px; border-radius:6px; border-left:4px solid #004a87;">
                    <span style="font-size:13px; color:#555;">Total de Itens Listados</span><br>
                    <span style="font-size:22px; font-weight:bold; color:#004a87;">{len(df_estoque)}</span></div>""", unsafe_allow_html=True)
            with m2:
                st.markdown(f"""<div style="background-color:#eef4fb; padding:12px; border-radius:6px; border-left:4px solid #004a87;">
                    <span style="font-size:13px; color:#555;">Soma de Quantidades</span><br>
                    <span style="font-size:22px; font-weight:bold; color:#004a87;">{int(df_estoque['quantidade'].sum())}</span></div>""", unsafe_allow_html=True)
            with m3:
                st.markdown(f"""<div style="background-color:#eef4fb; padding:12px; border-radius:6px; border-left:4px solid #004a87;">
                    <span style="font-size:13px; color:#555;">Categorias Envolvidas</span><br>
                    <span style="font-size:22px; font-weight:bold; color:#004a87;">{df_estoque['categoria'].nunique()}</span></div>""", unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if 'marcados_visualizacao' not in st.session_state:
                st.session_state['marcados_visualizacao'] = {}
            if 'editando_id' not in st.session_state:
                st.session_state['editando_id'] = None

            c_chk, c_cod, c_img, c_desc, c_cat, c_loc, c_qtd, c_acao = st.columns([1, 1, 2, 3, 2, 2, 2, 2])
            c_chk.write("**MARCAR**")
            c_cod.write("**CÓD**")
            c_img.write("**FOTO**")
            c_desc.write("**MATERIAL**")
            c_cat.write("**CATEGORIA**")
            c_loc.write("**LOCAL / ORIGEM**")
            c_qtd.write("**QTD**")
            c_acao.write("**AÇÕES**")
            st.divider()

            for _, row in df_estoque.iterrows():
                item_id = row['id']
                esta_marcado = st.session_state['marcados_visualizacao'].get(item_id, False)
                is_pendente = row.get("pendente_devolucao", False)
                
                if is_pendente:
                    bg_style = "background-color: #fff3cd; padding: 6px; border-radius: 6px; border-left: 4px solid #ffc107;"
                elif esta_marcado:
                    bg_style = "background-color: #eef4fb; padding: 6px; border-radius: 6px;"
                else:
                    bg_style = ""
                
                with st.container():
                    if bg_style:
                        st.markdown(f"<div style='{bg_style}'>", unsafe_allow_html=True)

                    c_chk, c_cod, c_img, c_desc, c_cat, c_loc, c_qtd, c_acao = st.columns([1, 1, 2, 3, 2, 2, 2, 2], vertical_alignment="center")
                    
                    marcado = c_chk.checkbox("", value=esta_marcado, key=f"marcar_{item_id}")
                    if marcado != esta_marcado:
                        st.session_state['marcados_visualizacao'][item_id] = marcado
                        st.rerun()
                    
                    c_cod.write(f"#{item_id}")
                    
                    url_img = row.get("url_imagem")
                    if url_img and pd.notna(url_img) and str(url_img).startswith("http"):
                        try:
                            c_img.image(url_img, width=50)
                        except Exception:
                            c_img.caption("Indisponível")
                    else:
                        c_img.caption("Sem foto")
                        
                    if is_pendente:
                        c_desc.markdown(f"**{row['nome_item']}** <br><span style='color:#d35400; font-size:12px; font-weight:bold;'>⏳ Na fila de devolução</span>", unsafe_allow_html=True)
                    else:
                        c_desc.write(row["nome_item"])
                        
                    c_cat.write(row["categoria"])
                    
                    origem = padronizar_unidade(row.get("unidade_origem", "Desconhecida"))
                    atual = padronizar_unidade(row.get("unidade_atual", "Desconhecida"))
                    
                    if origem != atual:
                        c_loc.markdown(f"**{atual}**<br><span style='color:#c0392b; font-size:11px;'>Origem: {origem}</span>", unsafe_allow_html=True)
                    else:
                        c_loc.write(atual)
                    
                    unidade_medida_atual = row.get("unidade_medida") if pd.notna(row.get("unidade_medida")) else "Unidade (un)"
                    c_qtd.write(f"**{row['quantidade']}** {unidade_medida_atual}")
                    
                    col_btn1, col_btn2 = c_acao.columns(2)
                    with col_btn1:
                        if st.button("✏️", key=f"btn_edit_{item_id}", help="Editar e/ou Enviar item"):
                            if st.session_state['editando_id'] == item_id:
                                st.session_state['editando_id'] = None
                            else:
                                st.session_state['editando_id'] = item_id
                            st.rerun()
                    with col_btn2:
                        if origem != atual:
                            if not is_pendente:
                                if st.button("📦", key=f"btn_fila_{item_id}", help="Enviar para a Fila de Devolução"):
                                    execute_db("UPDATE estoque_pro SET pendente_devolucao = TRUE WHERE id = %s", (item_id,))
                                    st.toast("Adicionado à fila de devolução!")
                                    st.rerun()
                            else:
                                st.button("⏳", key=f"btn_fila_dis_{item_id}", disabled=True, help="Já aguardando na fila")

                    if bg_style:
                        st.markdown("</div>", unsafe_allow_html=True)

                    # --- FORMULÁRIO DE EDIÇÃO E TRANSFERÊNCIA BLINDADO ---
                    if st.session_state.get('editando_id') == item_id:
                        with st.form(key=f"form_edicao_direta_{item_id}", clear_on_submit=False):
                            st.markdown(f"**Editar / Transferir Material #{item_id}: {row['nome_item']}**")
                            
                            e_col1, e_col2 = st.columns(2)
                            with e_col1:
                                novo_nome = st.text_input("Nome do Material", value=row['nome_item'])
                                nova_categoria = st.selectbox("Categoria", CATEGORIAS_PADRAO, index=CATEGORIAS_PADRAO.index(row['categoria']) if row['categoria'] in CATEGORIAS_PADRAO else 0)
                                nova_qtd = st.number_input("Quantidade Total", min_value=0, value=int(row['quantidade']), step=1)
                            with e_col2:
                                idx_origem = UNIDADES_PADRAO.index(origem) if origem in UNIDADES_PADRAO else 0
                                nova_origem = padronizar_unidade(st.selectbox("Unidade Proprietária (Dono)", UNIDADES_PADRAO, index=idx_origem))
                                
                                unidades_medida_lista = ["Unidade (un)", "Metros (m)", "Quilogramas (kg)", "Litros (L)", "Caixa (cx)"]
                                medida_atual_idx = unidades_medida_lista.index(row['unidade_medida']) if row.get('unidade_medida') in unidades_medida_lista else 0
                                nova_medida = st.selectbox("Unidade de Medida", unidades_medida_lista, index=medida_atual_idx)
                                
                                nova_imagem = st.file_uploader("Alterar Foto (Opcional)", type=["png", "jpg", "jpeg"], key=f"up_{item_id}")
                            
                            st.markdown("---")
                            st.markdown("##### 🚚 Transferência Imediata (Opcional)")
                            fazer_transferencia = st.checkbox("Deseja enviar parte desta quantidade para outra unidade agora?", value=False)
                            
                            unidade_destino_transf = None
                            qtd_transf = 0
                            if fazer_transferencia:
                                unidades_possiveis = [u for u in UNIDADES_PADRAO if u != atual]
                                unidade_destino_transf = padronizar_unidade(st.selectbox("Unidade de Destino", unidades_possiveis))
                                qtd_transf = st.number_input("Quantidade a Enviar", min_value=1, max_value=int(nova_qtd) if nova_qtd > 0 else 1, value=1, step=1)

                            excluir_check = st.checkbox("Excluir este lote permanentemente do banco de dados")
                            
                            sub_col1, sub_col2 = st.columns(2)
                            salvar_edicao = sub_col1.form_submit_button("Salvar Tudo")
                            cancelar_edicao = sub_col2.form_submit_button("Cancelar")
                            
                            if salvar_edicao:
                                if excluir_check or nova_qtd == 0:
                                    execute_db("DELETE FROM estoque_pro WHERE id = %s", (item_id,))
                                    execute_db(
                                        "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), atual, row['nome_item'], "EXCLUSÃO/ZERADO", row['quantidade'], "Responsável Local")
                                    )
                                    st.success("Item excluído ou zerado com sucesso.")
                                else:
                                    nome_limpo = novo_nome.strip().title()
                                    
                                    img_original = row.get('url_imagem')
                                    url_para_inserir = img_original if pd.notna(img_original) and str(img_original).strip() != "" and str(img_original).lower() != "nan" else None
                                    
                                    if fazer_transferencia and unidade_destino_transf and qtd_transf > 0:
                                        if qtd_transf > nova_qtd:
                                            st.error("A quantidade a enviar não pode ser maior que a quantidade total.")
                                        else:
                                            qtd_restante = nova_qtd - qtd_transf
                                            
                                            if qtd_restante == 0:
                                                execute_db("DELETE FROM estoque_pro WHERE id = %s", (item_id,))
                                            else:
                                                execute_db("UPDATE estoque_pro SET nome_item = %s, categoria = %s, quantidade = %s, unidade_origem = %s, unidade_medida = %s WHERE id = %s",
                                                           (nome_limpo, nova_categoria, qtd_restante, nova_origem, nova_medida, item_id))
                                            
                                            # CORREÇÃO BLINDADA: Busca exata de destino normalizada
                                            ja_tem_dest = run_query(
                                                "SELECT id, quantidade FROM estoque_pro WHERE unidade_atual = %s AND LOWER(TRIM(nome_item)) = LOWER(TRIM(%s)) AND unidade_origem = %s", 
                                                (unidade_destino_transf, nome_limpo, nova_origem)
                                            )
                                            if not ja_tem_dest.empty:
                                                id_dest = int(ja_tem_dest.iloc[0]["id"])
                                                nova_q_dest = int(ja_tem_dest.iloc[0]["quantidade"]) + int(qtd_transf)
                                                execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (nova_q_dest, id_dest))
                                            else:
                                                execute_db(
                                                    "INSERT INTO estoque_pro (unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                                    (nova_origem, unidade_destino_transf, nome_limpo, nova_categoria, qtd_transf, nova_medida, url_para_inserir)
                                                )
                                            
                                            execute_db(
                                                "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{atual} ➔ {unidade_destino_transf}", nome_limpo, "TRANSFERÊNCIA INTEGRADA", qtd_transf, "Responsável Local")
                                            )
                                    else:
                                        if nova_imagem is not None:
                                            novo_link = upload_imgbb(nova_imagem)
                                            if novo_link:
                                                execute_db("UPDATE estoque_pro SET nome_item = %s, categoria = %s, quantidade = %s, unidade_origem = %s, unidade_medida = %s, url_imagem = %s WHERE id = %s",
                                                           (nome_limpo, nova_categoria, nova_qtd, nova_origem, nova_medida, novo_link, item_id))
                                        else:
                                            execute_db("UPDATE estoque_pro SET nome_item = %s, categoria = %s, quantidade = %s, unidade_origem = %s, unidade_medida = %s WHERE id = %s",
                                                       (nome_limpo, nova_categoria, nova_qtd, nova_origem, nova_medida, item_id))
                                            
                                    st.success(f"Atualização e transferência realizada com sucesso! O item já aparece na unidade {unidade_destino_transf if fazer_transferencia else atual}.")
                                
                                st.session_state['editando_id'] = None
                                st.rerun()
                                
                            if cancelar_edicao:
                                st.session_state['editando_id'] = None
                                st.rerun()

                    st.divider()
        else:
            st.info("Nenhum material encontrado com os filtros selecionados.")

# --- TELA 2: ENTRADA DE MATERIAIS ---
elif menu == "Entrada de Materiais":
    st.subheader("Cadastrar Novo Material ou Adicionar Lote")
    
    with st.form("form_entrada", clear_on_submit=False):
        col_a, col_b = st.columns(2)
        with col_a:
            unidade = padronizar_unidade(st.selectbox("Unidade Destino / Proprietária", UNIDADES_PADRAO))
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
                    "SELECT id, quantidade FROM estoque_pro WHERE unidade_atual = %s AND LOWER(TRIM(nome_item)) = LOWER(TRIM(%s)) AND unidade_origem = %s",
                    (unidade, nome_item, unidade)
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

# --- TELA 3: SAÍDA E EMPRÉSTIMO ---
elif menu == "Saída / Empréstimo":
    st.subheader("Baixa de Materiais e Empréstimo entre Unidades")
    
    unidade_selecionada = padronizar_unidade(st.selectbox("Selecione a Unidade onde o material está fisicamente", UNIDADES_PADRAO))
    
    with st.spinner("Buscando itens da unidade..."):
        itens_disponiveis = run_query(
            "SELECT id, unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem FROM estoque_pro WHERE unidade_atual = %s", 
            (unidade_selecionada,)
        )
    
    if itens_disponiveis.empty:
        st.warning("Nenhum item cadastrado nesta unidade.")
    else:
        opcoes_itens = {row["id"]: f"#{row['id']} - {row['nome_item']} (Qtd: {row['quantidade']} {row.get('unidade_medida', 'un')}) - Origem: {row['unidade_origem']}" for _, row in itens_disponiveis.iterrows()}

        item_id_selecionado = st.selectbox(
            "Selecione o Material", options=list(opcoes_itens.keys()), format_func=lambda x: opcoes_itens[x]
        )
        
        dados_item = itens_disponiveis[itens_disponiveis["id"] == item_id_selecionado].iloc[0]
        nome_selecionado, qtd_atual, imagem_atual = dados_item["nome_item"], dados_item["quantidade"], dados_item["url_imagem"]
        origem_atual = padronizar_unidade(dados_item["unidade_origem"])
        medida_atual_item = dados_item.get("unidade_medida") if pd.notna(dados_item.get("unidade_medida")) else "Unidade (un)"
        
        col_img, col_info = st.columns([1, 2])
        with col_img:
            if imagem_atual and pd.notna(imagem_atual) and str(imagem_atual).startswith("http"):
                try:
                    st.image(imagem_atual, caption=nome_selecionado, width=200)
                except Exception:
                    st.caption("Sem foto válida")
            else:
                st.info("Sem foto cadastrada.")
        with col_info:
            st.markdown(f"**Item:** {nome_selecionado}")
            st.markdown(f"**Categoria:** {dados_item['categoria']}")
            st.markdown(f"**Estoque Disponível:** {qtd_atual} {medida_atual_item}")
            st.markdown(f"**Unidade Proprietária (Origem):** {origem_atual}")
            if origem_atual != unidade_selecionada:
                st.warning(f"Este material está emprestado e pertence originalmente a {origem_atual}.")

        st.divider()
        acao = st.radio("Escolha a Operação:", ["Dar Baixa (Saída Definitiva)", "Empréstimo / Enviar para Outra Unidade"])
        
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
            nova_unidade_atual = padronizar_unidade(st.selectbox("Enviar para qual Unidade?", unidades_destino))
            qtd_envio = st.number_input("Quantidade a Enviar por Empréstimo/Transferência", min_value=1, max_value=int(qtd_atual) if qtd_atual > 0 else 1, step=1)
            
            if st.button("Confirmar Envio / Empréstimo"):
                data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                img_original_envio = dados_item.get('url_imagem')
                url_para_inserir_envio = img_original_envio if pd.notna(img_original_envio) and str(img_original_envio).strip() != "" and str(img_original_envio).lower() != "nan" else None
                
                if qtd_envio == qtd_atual:
                    execute_db("UPDATE estoque_pro SET unidade_atual = %s WHERE id = %s", (nova_unidade_atual, item_id_selecionado))
                else:
                    nova_qtd_origem = int(qtd_atual) - int(qtd_envio)
                    execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (nova_qtd_origem, item_id_selecionado))
                    
                    # CORREÇÃO BLINDADA: Busca exata no destino considerando origem e nome normalizados
                    ja_tem = run_query(
                        "SELECT id, quantidade FROM estoque_pro WHERE unidade_atual = %s AND LOWER(TRIM(nome_item)) = LOWER(TRIM(%s)) AND unidade_origem = %s", 
                        (nova_unidade_atual, nome_selecionado, origem_atual)
                    )
                    if not ja_tem.empty:
                        id_destino = int(ja_tem.iloc[0]["id"])
                        q_nova = int(ja_tem.iloc[0]["quantidade"]) + int(qtd_envio)
                        execute_db("UPDATE estoque_pro SET quantidade = %s WHERE id = %s", (q_nova, id_destino))
                    else:
                        execute_db(
                            "INSERT INTO estoque_pro (unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida, url_imagem) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (origem_atual, nova_unidade_atual, nome_selecionado, dados_item['categoria'], qtd_envio, medida_atual_item, url_para_inserir_envio)
                        )

                # REGISTRO GARANTIDO NO HISTÓRICO
                execute_db(
                    "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                    (data_atual, f"{unidade_selecionada} ➔ {nova_unidade_atual}", nome_selecionado, "EMPRÉSTIMO/TRANSFERÊNCIA", qtd_envio, "Responsável Local")
                )
                st.success(f"Material transferido com sucesso para {nova_unidade_atual}! Já aparece no estoque de destino e no histórico.")
                st.rerun()

# --- TELA 4: FILA E CONFIRMAÇÃO DE DEVOLUÇÕES ---
elif menu == "Devolução em Lote":
    st.subheader("Fila de Devolução de Materiais")
    st.markdown("Confirme a devolução final dos itens que foram enviados para esta fila ou reverta envios acidentais.")
    
    unidade_atual_filtro = padronizar_unidade(st.selectbox("Selecione a Unidade atual", UNIDADES_PADRAO))
    
    query_pendentes = "SELECT id, unidade_origem, unidade_atual, nome_item, categoria, quantidade, unidade_medida FROM estoque_pro WHERE pendente_devolucao = TRUE AND unidade_atual = %s"
    df_pendentes = run_query(query_pendentes, (unidade_atual_filtro,))
    
    if not df_pendentes.empty:
        st.markdown(f"**{len(df_pendentes)}** item(ns) aguardando devolução.")
        st.divider()
        
        for _, row in df_pendentes.iterrows():
            col_info, col_conf, col_rev = st.columns([5, 2, 2], vertical_alignment="center")
            medida_pendente = row.get("unidade_medida") if pd.notna(row.get("unidade_medida")) else "Unidade (un)"
            
            with col_info:
                st.write(f"📦 **{row['nome_item']}** (Qtd: {row['quantidade']} {medida_pendente})")
                st.caption(f"Destino (Origem): **{row['unidade_origem']}**")
                
            with col_conf:
                if st.button("✅ Confirmar Devolução", key=f"conf_{row['id']}", use_container_width=True):
                    execute_db("UPDATE estoque_pro SET unidade_atual = %s, pendente_devolucao = FALSE WHERE id = %s", (row['unidade_origem'], row['id']))
                    execute_db(
                        "INSERT INTO movimentacoes_pro (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{unidade_atual_filtro} ➔ {row['unidade_origem']}", row['nome_item'], "DEVOLUÇÃO", row['quantidade'], "Responsável Local")
                    )
                    st.success(f"{row['nome_item']} devolvido e retirado do seu estoque!")
                    st.rerun()
                    
            with col_rev:
                if st.button("❌ Reverter/Desfazer", key=f"rev_{row['id']}", use_container_width=True, help="Tira o item da fila de devolução e mantém na sua unidade"):
                    execute_db("UPDATE estoque_pro SET pendente_devolucao = FALSE WHERE id = %s", (row['id'],))
                    st.toast("Envio cancelado com sucesso. Item continua livre na sua lista principal.")
                    st.rerun()
            st.divider()
    else:
        st.info("Sua fila de devolução está vazia.")

# --- TELA 5: HISTÓRICO E AUDITORIA ---
elif menu == "Histórico de Movimentações":
    st.subheader("Auditoria de Movimentações (Entradas, Saídas, Empréstimos e Ajustes)")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_inicio = st.date_input("Data Inicial", value=date.today().replace(day=1))
    with col_d2:
        data_fim = st.date_input("Data Final", value=date.today())
        
    with st.spinner("Carregando histórico..."):
        df_logs = run_query("SELECT data_hora, unidade, nome_item, tipo, quantidade, responsavel FROM movimentacoes_pro ORDER BY id DESC")
        
    if not df_logs.empty:
        df_logs['data_convertida'] = pd.to_datetime(df_logs['data_hora'], errors='coerce').dt.date
        
        df_filtrado = df_logs[
            (df_logs['data_convertida'] >= data_inicio) & 
            (df_logs['data_convertida'] <= data_fim)
        ].drop(columns=['data_convertida'])
        
        if not df_filtrado.empty:
            st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma movimentação encontrada no período selecionado. Abaixo estão todas as movimentações para auditoria:")
            st.dataframe(df_logs.drop(columns=['data_convertida']), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada até o momento no banco de dados.")