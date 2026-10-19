import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from gspread import service_account, service_account_from_dict

# -------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO
# -------------------------------------------------------------------
st.set_page_config(page_title="Gestão Minimercado", layout="wide")

PLANILHA_NOME = "BD_Minimercado"  # Nome exato da sua planilha no Google Drive
CREDENTIALS_PATH = "credentials.json"  # Caso rode localmente via arquivo JSON

@st.cache_resource
def conectar_google_sheets():
    try:
        if "gcp_service_account" in st.secrets:
            secrets_dict = dict(st.secrets["gcp_service_account"])
            private_key_corrompida = secrets_dict["private_key"]
            
            private_key_limpa = private_key_corrompida.replace('\n', '').replace(' ', '')
            private_key_limpa = private_key_limpa.replace('-----BEGINPRIVATEKEY-----', '').replace('-----ENDPRIVATEKEY-----', '')
            
            padding_necessario = len(private_key_limpa) % 4
            if padding_necessario != 0:
                private_key_limpa += '=' * (4 - padding_necessario)
            
            secrets_dict["private_key"] = f"-----BEGIN PRIVATE KEY-----\n{private_key_limpa}\n-----END PRIVATE KEY-----\n"
            gc = service_account_from_dict(secrets_dict)
        else:
            gc = service_account(filename=CREDENTIALS_PATH)
            
        return gc.open(PLANILHA_NOME)
    except Exception as e:
        st.error(f"Erro crítico na autenticação do Google Sheets: {e}")
        return None

# Conecta com a planilha
sh = conectar_google_sheets()

if not sh:
    st.stop()

# Helper Functions para ler e escrever dados
def ler_aba(nome_aba):
    aba = sh.worksheet(nome_aba)
    dados = aba.get_all_records()
    return pd.DataFrame(dados)

def atualizar_aba(nome_aba, df):
    aba = sh.worksheet(nome_aba)
    aba.clear()
    aba.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# -------------------------------------------------------------------
# MENU LATERAL
# -------------------------------------------------------------------
st.title("🛒 Sistema de Gestão - Minimercado")

menu = st.sidebar.selectbox(
    "Navegação",
    ["PDV (Vendas)", "Cadastro / Entrada de Estoque", "Posição de Estoque", "Despesas Extras", "Faturamento e Financeiro"]
)

# -------------------------------------------------------------------
# 1. PDV (VENDAS)
# -------------------------------------------------------------------
if menu == "PDV (Vendas)":
    st.header("🛍️ Frente de Caixa (PDV)")
    
    df_produtos = ler_aba("Produtos_Estoque")
    
    if df_produtos.empty:
        st.info("Nenhum produto cadastrado no estoque.")
    else:
        # Garante tipos de dados corretos
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0)
        df_produtos['Preco_Venda'] = pd.to_numeric(df_produtos['Preco_Venda'], errors='coerce').fillna(0.0)
        
        produtos_disponiveis = df_produtos[df_produtos['Quantidade_Estoque'] > 0]
        
        if produtos_disponiveis.empty:
            st.warning("Não há produtos com estoque disponível para venda.")
        else:
            produto_sel = st.selectbox("Selecione o Produto", produtos_disponiveis['Nome_Produto'].tolist())
            
            if produto_sel:
                item = df_produtos[df_produtos['Nome_Produto'] == produto_sel].iloc[0]
                
                col_a, col_b = st.columns(2)
                col_a.write(f"**Preço Unitário:** R$ {item['Preco_Venda']:.2f}")
                col_b.write(f"**Estoque Disponível:** {int(item['Quantidade_Estoque'])}")
                
                qtd = st.number_input("Quantidade", min_value=1, max_value=int(item['Quantidade_Estoque']), value=1, step=1)
                total_venda = qtd * item['Preco_Venda']
                
                st.subheader(f"Total a Pagar: R$ {total_venda:.2f}")
                
                if st.button("Finalizar Venda", type="primary"):
                    # 1. Registrar Venda
                    df_vendas = ler_aba("Vendas")
                    nova_venda = pd.DataFrame([{
                        "ID_Venda": len(df_vendas) + 1,
                        "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ID_Produto": item['ID_Produto'],
                        "Nome_Produto": item['Nome_Produto'],
                        "Quantidade": qtd,
                        "Preco_Unitario": item['Preco_Venda'],
                        "Valor_Total": total_venda
                    }])
                    df_vendas_atualizado = pd.concat([df_vendas, nova_venda], ignore_index=True)
                    atualizar_aba("Vendas", df_vendas_atualizado)
                    
                    # 2. Dar baixa no estoque
                    df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] -= qtd
                    atualizar_aba("Produtos_Estoque", df_produtos)
                    
                    st.success("Venda registrada com sucesso e estoque atualizado!")
                    st.rerun()

# -------------------------------------------------------------------
# 2. CADASTRO E ENTRADA DE ESTOQUE
# -------------------------------------------------------------------
elif menu == "Cadastro / Entrada de Estoque":
    st.header("📦 Alimentar / Cadastrar Estoque")
    
    df_produtos = ler_aba("Produtos_Estoque")
    
    opcao = st.radio("Ação", ["Novo Produto", "Adicionar Unidades a Produto Existente"])
    
    if opcao == "Novo Produto":
        with st.form("form_novo_prod"):
            nome = st.text_input("Nome do Produto")
            categoria = st.text_input("Categoria (ex: Bebidas, Mercearia, Limpeza)")
            custo = st.number_input("Custo Unitário (R$)", min_value=0.0, format="%.2f")
            preco = st.number_input("Preço de Venda (R$)", min_value=0.0, format="%.2f")
            qtd_inicial = st.number_input("Quantidade Inicial", min_value=0, step=1)
            
            submitted = st.form_submit_button("Salvar Produto")
            if submitted:
                if not nome:
                    st.error("Informe o nome do produto.")
                else:
                    novo_id = len(df_produtos) + 1
                    novo_registro = pd.DataFrame([{
                        "ID_Produto": novo_id,
                        "Nome_Produto": nome,
                        "Categoria": categoria,
                        "Custo_Unitario": custo,
                        "Preco_Venda": preco,
                        "Quantidade_Estoque": qtd_inicial
                    }])
                    df_atualizado = pd.concat([df_produtos, novo_registro], ignore_index=True)
                    atualizar_aba("Produtos_Estoque", df_atualizado)
                    st.success(f"Produto '{nome}' cadastrado com sucesso!")
                    st.rerun()

    elif opcao == "Adicionar Unidades a Produto Existente":
        if df_produtos.empty:
            st.info("Nenhum produto cadastrado ainda.")
        else:
            produto_sel = st.selectbox("Selecione o Produto", df_produtos['Nome_Produto'].tolist())
            qtd_add = st.number_input("Quantidade a Adicionar", min_value=1, step=1)
            
            if st.button("Adicionar ao Estoque"):
                df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0)
                df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] += qtd_add
                atualizar_aba("Produtos_Estoque", df_produtos)
                st.success(f"Adicionadas {qtd_add} unidades ao produto '{produto_sel}'.")
                st.rerun()

# -------------------------------------------------------------------
# 3. POSIÇÃO DE ESTOQUE
# -------------------------------------------------------------------
elif menu == "Posição de Estoque":
    st.header("📊 Posição Geral do Estoque")
    
    df_produtos = ler_aba("Produtos_Estoque")
    
    if not df_produtos.empty:
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0)
        
        # Alerta de estoque baixo (ex: 5 ou menos)
        estoque_baixo = df_produtos[df_produtos['Quantidade_Estoque'] <= 5]
        if not estoque_baixo.empty:
            st.warning("⚠️ Atenção: Produtos com estoque igual ou menor a 5 unidades:")
            st.dataframe(estoque_baixo[['Nome_Produto', 'Quantidade_Estoque', 'Preco_Venda']], use_container_width=True)
            
        st.subheader("Todos os Produtos")
        st.dataframe(df_produtos, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado no estoque.")

# -------------------------------------------------------------------
# 4. DESPESAS EXTRAS
# -------------------------------------------------------------------
elif menu == "Despesas Extras":
    st.header("💸 Lançamento de Custos e Despesas Extras")
    
    with st.form("form_despesas"):
        data_despesa = st.date_input("Data da Despesa")
        categoria = st.selectbox("Categoria", ["Equipamentos (Freezer, Balcão, etc.)", "Energia Elétrica", "Aluguel", "Manutenção", "Outros"])
        descricao = st.text_input("Descrição (ex: Compra de Freezer para refrigerados)")
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Registrar Despesa"):
            if valor <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                df_despesas = ler_aba("Despesas_Extras")
                nova_despesa = pd.DataFrame([{
                    "ID_Despesa": len(df_despesas) + 1,
                    "Data": str(data_despesa),
                    "Categoria_Despesa": categoria,
                    "Descricao": descricao,
                    "Valor": valor
                }])
                df_despesas_atualizado = pd.concat([df_despesas, nova_despesa], ignore_index=True)
                atualizar_aba("Despesas_Extras", df_despesas_atualizado)
                st.success("Despesa salva com sucesso!")
                st.rerun()

# -------------------------------------------------------------------
# 5. FATURAMENTO E FINANCEIRO
# -------------------------------------------------------------------
elif menu == "Faturamento e Financeiro":
    st.header("📈 Visão Financeira e Resultados")
    
    df_vendas = ler_aba("Vendas")
    df_despesas = ler_aba("Despesas_Extras")
    df_produtos = ler_aba("Produtos_Estoque")
    
    # Conversão de valores numéricos
    faturamento_total = 0.0
    despesas_totais = 0.0
    cmv_total = 0.0
    
    if not df_vendas.empty:
        df_vendas['Valor_Total'] = pd.to_numeric(df_vendas['Valor_Total'], errors='coerce').fillna(0.0)
        df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'], errors='coerce').fillna(0)
        faturamento_total = df_vendas['Valor_Total'].sum()
        
    if not df_despesas.empty:
        df_despesas['Valor'] = pd.to_numeric(df_despesas['Valor'], errors='coerce').fillna(0.0)
        despesas_totais = df_despesas['Valor'].sum()
        
    # Cálculo do Custo de Mercadoria Vendida (CMV)
    if not df_vendas.empty and not df_produtos.empty:
        df_produtos['Custo_Unitario'] = pd.to_numeric(df_produtos['Custo_Unitario'], errors='coerce').fillna(0.0)
        df_merged = df_vendas.merge(df_produtos[['ID_Produto', 'Custo_Unitario']], on='ID_Produto', how='left')
        cmv_total = (df_merged['Quantidade'] * df_merged['Custo_Unitario']).sum()
        
    lucro_bruto = faturamento_total - cmv_total
    lucro_liquido = lucro_bruto - despesas_totais
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento Bruto", f"R$ {faturamento_total:.2f}")
    c2.metric("Custo Mercadorias (CMV)", f"R$ {cmv_total:.2f}")
    c3.metric("Despesas Extras", f"R$ {despesas_totais:.2f}")
    c4.metric("Lucro Líquido", f"R$ {lucro_liquido:.2f}")
    
    st.divider()
    
    col_vendas, col_despesas = st.columns(2)
    with col_vendas:
        st.subheader("Histórico de Vendas")
        st.dataframe(df_vendas, use_container_width=True)
        
    with col_despesas:
        st.subheader("Histórico de Despesas")
        st.dataframe(df_despesas, use_container_width=True)
