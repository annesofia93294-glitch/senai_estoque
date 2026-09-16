import streamlit as st
import pandas as pd
from datetime import datetime
import psycopg2

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Controle de Estoque - SENAI", layout="wide")

# --- CONEXÃO COM O BANCO DE DADOS EM NUVEM ---
DB_URL = st.secrets["DB_URL"]

def get_connection():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id SERIAL PRIMARY KEY,
            unidade TEXT NOT NULL,
            nome_item TEXT NOT NULL,
            categoria TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            unidade_medida TEXT NOT NULL,
            imagem BYTEA
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
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
    conn.close()

try:
    init_db()
except Exception as e:
    st.error("Configure o link do banco de dados nos Segredos (Secrets) do Streamlit.")

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

# --- INTERFACE PRINCIPAL ---
st.title("📦 Sistema Integrado de Estoque - SENAI")

menu = st.sidebar.selectbox(
    "Navegação",
    ["Visualizar Estoque", "Entrada de Materiais", "Saída / Editar Estoque", "Histórico de Movimentações"]
)

UNIDADES_PADRAO = ["SENAI Barreiras", "SENAI Luis Eduardo", "Almoxarifado Central"]
CATEGORIAS_PADRAO = [
    "Rede de Distribuição", "Motores Elétricos", "Comandos Elétricos", 
    "Ferramentas de Medição", "Ferramentas Elétricas", "Kits Didáticos", "EPIs"
]

# --- TELA 1: CONSULTA DE ESTOQUE ---
if menu == "Visualizar Estoque":
    st.subheader("Catálogo de Materiais")
    
    col1, col2 = st.columns(2)
    with col1:
        filtro_unidade = st.selectbox("Filtrar por Unidade", ["Todas"] + UNIDADES_PADRAO)
    with col2:
        filtro_categoria = st.selectbox("Filtrar por Categoria", ["Todas"] + CATEGORIAS_PADRAO)
    
    query = "SELECT id, unidade, nome_item, categoria, quantidade, unidade_medida, imagem FROM estoque WHERE 1=1"
    params = []
    
    if filtro_unidade != "Todas":
        query += " AND unidade = %s"
        params.append(filtro_unidade)
    if filtro_categoria != "Todas":
        query += " AND categoria = %s"
        params.append(filtro_categoria)
        
    df_estoque = run_query(query, tuple(params))
    
    if not df_estoque.empty:
        # Cabeçalho da Lista
        c_cod, c_img, c_desc, c_cat, c_qtd = st.columns([1, 2, 4, 3, 2])
        c_cod.write("**CÓDIGO**")
        c_img.write("**IMAGEM**")
        c_desc.write("**DESCRIÇÃO (NOME)**")
        c_cat.write("**CATEGORIA**")
        c_qtd.write("**QUANTIDADE**")
        st.divider()

        # Renderiza cada item lado a lado
        for _, row in df_estoque.iterrows():
            c_cod, c_img, c_desc, c_cat, c_qtd = st.columns([1, 2, 4, 3, 2], vertical_alignment="center")
            
            c_cod.write(row["id"])
            
            # CORREÇÃO: Transformando em bytes puros
            if row["imagem"] is not None:
                try:
                    c_img.image(bytes(row["imagem"]), width=80)
                except Exception:
                    c_img.caption("Erro ao carregar")
            else:
                c_img.caption("Sem imagem")
                
            c_desc.write(row["nome_item"])
            c_cat.write(row["categoria"])
            c_qtd.write(f"{row['quantidade']} {row['unidade_medida']}")
            
            st.divider()
    else:
        st.info("Nenhum material encontrado. Cadastre itens na tela 'Entrada de Materiais'.")

# --- TELA 2: ENTRADA DE MATERIAIS ---
elif menu == "Entrada de Materiais":
    st.subheader("Cadastrar Novo Material ou Adicionar Estoque")
    
    with st.form("form_entrada", clear_on_submit=False):
        unidade = st.selectbox("Unidade", UNIDADES_PADRAO)
        nome_item = st.text_input("Nome do Material / Equipamento").strip().title()
        categoria = st.selectbox("Categoria", CATEGORIAS_PADRAO)
        quantidade = st.number_input("Quantidade a Adicionar", min_value=1, step=1)
        un_medida = st.selectbox("Unidade de Medida", ["Unidade (un)", "Metros (m)", "Quilogramas (kg)", "Litros (L)", "Caixa (cx)"])
        
        imagem_upload = st.file_uploader("Foto do Material (Opcional)", type=["png", "jpg", "jpeg"])
        
        submitted = st.form_submit_button("Registrar Entrada")
        
        if submitted:
            if not nome_item:
                st.error("Por favor, preencha o nome do material.")
            else:
                data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                imagem_bytes = psycopg2.Binary(imagem_upload.read()) if imagem_upload is not None else None
                
                item_existente = run_query(
                    "SELECT id, quantidade FROM estoque WHERE unidade = %s AND nome_item = %s",
                    (unidade, nome_item)
                )
                
                if not item_existente.empty:
                    item_id = int(item_existente.iloc[0]["id"])
                    nova_qtd = int(item_existente.iloc[0]["quantidade"]) + quantidade
                    
                    if imagem_bytes:
                        execute_db("UPDATE estoque SET quantidade = %s, imagem = %s WHERE id = %s", (nova_qtd, imagem_bytes, item_id))
                    else:
                        execute_db("UPDATE estoque SET quantidade = %s WHERE id = %s", (nova_qtd, item_id))
                else:
                    execute_db(
                        "INSERT INTO estoque (unidade, nome_item, categoria, quantidade, unidade_medida, imagem) VALUES (%s, %s, %s, %s, %s, %s)",
                        (unidade, nome_item, categoria, quantidade, un_medida, imagem_bytes)
                    )
                
                execute_db(
                    "INSERT INTO movimentacoes (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                    (data_atual, unidade, nome_item, "ENTRADA", quantidade, "Não informado")
                )
                st.success(f"Entrada de {quantidade} {un_medida} do item '{nome_item}' registrada com sucesso!")

# --- TELA 3: SAÍDA E EDIÇÃO DE MATERIAIS ---
elif menu == "Saída / Editar Estoque":
    st.subheader("Saída e Edição de Materiais Existentes")
    
    unidade_selecionada = st.selectbox("Selecione a Unidade do Material", UNIDADES_PADRAO)
    
    itens_disponiveis = run_query(
        "SELECT id, nome_item, quantidade, unidade_medida, imagem FROM estoque WHERE unidade = %s", 
        (unidade_selecionada,)
    )
    
    if itens_disponiveis.empty:
        st.warning(f"Nenhum item cadastrado na unidade {unidade_selecionada}.")
    else:
        opcoes_itens = {row["id"]: f"{row['nome_item']} (Estoque: {row['quantidade']} {row['unidade_medida']})" for _, row in itens_disponiveis.iterrows()}
        
        item_id_selecionado = st.selectbox(
            "Selecione o Material", 
            options=list(opcoes_itens.keys()), 
            format_func=lambda x: opcoes_itens[x]
        )
        
        dados_item = itens_disponiveis[itens_disponiveis["id"] == item_id_selecionado].iloc[0]
        nome_selecionado = dados_item["nome_item"]
        qtd_atual = dados_item["quantidade"]
        imagem_atual = dados_item["imagem"]
        
        # CORREÇÃO: Transformando em bytes puros
        if pd.notna(imagem_atual) and imagem_atual is not None:
            try:
                st.image(bytes(imagem_atual), caption=nome_selecionado, width=250)
            except Exception:
                st.info("Erro ao exibir a imagem.")
        else:
            st.info("Este material não possui foto cadastrada.")
        
        st.divider()
        
        acao = st.radio("O que deseja fazer com este item?", ["Dar Baixa (Saída)", "Editar Informações (Correção)"])
        
        if acao == "Dar Baixa (Saída)":
            quantidade_saida = st.number_input("Quantidade para Retirar", min_value=1, max_value=qtd_atual if qtd_atual > 0 else 1, step=1)
            
            if st.button("Confirmar Saída"):
                if quantidade_saida > qtd_atual:
                    st.error(f"Saldo insuficiente! Você só tem {qtd_atual} em estoque.")
                else:
                    nova_qtd = qtd_atual - quantidade_saida
                    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    execute_db("UPDATE estoque SET quantidade = %s WHERE id = %s", (nova_qtd, item_id_selecionado))
                    execute_db(
                        "INSERT INTO movimentacoes (data_hora, unidade, nome_item, tipo, quantidade, responsavel) VALUES (%s, %s, %s, %s, %s, %s)",
                        (data_atual, unidade_selecionada, nome_selecionado, "SAÍDA", quantidade_saida, "Não informado")
                    )
                    st.success(f"Saída de {quantidade_saida} do item '{nome_selecionado}' registrada com sucesso!")
                    st.rerun()
        
        elif acao == "Editar Informações (Correção)":
            st.info("Atenção: Esta opção altera os dados diretamente no estoque, sem gerar histórico de movimentação.")
            novo_nome = st.text_input("Corrigir Nome do Material", value=nome_selecionado)
            nova_qtd_total = st.number_input("Ajustar Quantidade Total Correta", min_value=0, value=qtd_atual, step=1)
            nova_imagem = st.file_uploader("Atualizar Foto (Deixe em branco para manter a atual)", type=["png", "jpg", "jpeg"])
            
            if st.button("Salvar Alterações"):
                if nova_imagem is not None:
                    imagem_bytes = psycopg2.Binary(nova_imagem.read())
                    execute_db(
                        "UPDATE estoque SET nome_item = %s, quantidade = %s, imagem = %s WHERE id = %s",
                        (novo_nome.strip().title(), nova_qtd_total, imagem_bytes, item_id_selecionado)
                    )
                else:
                    execute_db(
                        "UPDATE estoque SET nome_item = %s, quantidade = %s WHERE id = %s",
                        (novo_nome.strip().title(), nova_qtd_total, item_id_selecionado)
                    )
                st.success("Item atualizado com sucesso!")
                st.rerun()

# --- TELA 4: AUDITORIA E LOGS ---
elif menu == "Histórico de Movimentações":
    st.subheader("Auditoria de Entradas e Saídas")
    df_logs = run_query("SELECT data_hora, unidade, nome_item, tipo, quantidade, responsavel FROM movimentacoes ORDER BY id DESC")
    
    if not df_logs.empty:
        df_logs = df_logs.drop(columns=['responsavel'])
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma movimentação registrada até o momento.")