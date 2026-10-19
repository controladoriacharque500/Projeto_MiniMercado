import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from gspread import service_account_from_dict

# -------------------------------------------------------------------
# CONFIGURAÇÃO E CONEXÃO
# -------------------------------------------------------------------
st.set_page_config(page_title="Gestão Minimercado", layout="wide")

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
            
            if "spreadsheet_url" in st.secrets:
                return gc.open_by_url(st.secrets["spreadsheet_url"])
            else:
                return gc.open("BD_Minimercado")
        else:
            st.error("O bloco 'gcp_service_account' não foi encontrado nos st.secrets!")
            return None
            
    except Exception as e:
        st.error(f"Erro crítico na autenticação do Google Sheets: {e}")
        return None

sh = conectar_google_sheets()

if not sh:
    st.stop()

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
    ["PDV (Vendas)", "Cadastro / Entrada de Estoque", "Posição de Estoque", "Gerenciar Produtos", "Despesas Extras", "Faturamento e Financeiro"]
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
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
        df_produtos['Preco_Venda'] = pd.to_numeric(df_produtos['Preco_Venda'], errors='coerce').fillna(0.0)
        if 'Unidade_Medida' not in df_produtos.columns:
            df_produtos['Unidade_Medida'] = 'UN'
        
        produtos_disponiveis = df_produtos[df_produtos['Quantidade_Estoque'] > 0]
        
        if produtos_disponiveis.empty:
            st.warning("Não há produtos com estoque disponível para venda.")
        else:
            produto_sel = st.selectbox("Selecione o Produto", produtos_disponiveis['Nome_Produto'].tolist())
            
            if produto_sel:
                item = df_produtos[df_produtos['Nome_Produto'] == produto_sel].iloc[0]
                unidade = str(item['Unidade_Medida']).upper()
                
                col_a, col_b, col_c = st.columns(3)
                col_a.write(f"**Preço Unitário / Kg / L:** R$ {item['Preco_Venda']:.2f}")
                col_b.write(f"**Estoque Disponível:** {item['Quantidade_Estoque']:.3f} {unidade}")
                col_c.write(f"**Unidade de Medida:** {unidade}")
                
                if unidade in ['KG', 'L']:
                    qtd = st.number_input(
                        f"Quantidade em {unidade} (ex: 0.150 para 150g)", 
                        min_value=0.001, 
                        max_value=float(item['Quantidade_Estoque']), 
                        value=min(1.0, float(item['Quantidade_Estoque'])), 
                        step=0.050, 
                        format="%.3f"
                    )
                else:
                    qtd = st.number_input(
                        f"Quantidade em {unidade}", 
                        min_value=1, 
                        max_value=int(item['Quantidade_Estoque']), 
                        value=1, 
                        step=1
                    )
                
                total_venda = float(qtd) * float(item['Preco_Venda'])
                
                st.subheader(f"Total a Pagar: R$ {total_venda:.2f}")
                
                if st.button("Finalizar Venda", type="primary"):
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
                    
                    df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] -= qtd
                    atualizar_aba("Produtos_Estoque", df_produtos)
                    
                    st.success(f"✅ Venda realizada com sucesso! Total: R$ {total_venda:.2f} ({qtd} {unidade} de {produto_sel})")
                    st.balloons()

# -------------------------------------------------------------------
# 2. CADASTRO E ENTRADA DE ESTOQUE
# -------------------------------------------------------------------
elif menu == "Cadastro / Entrada de Estoque":
    st.header("📦 Alimentar / Cadastrar Estoque")
    
    df_produtos = ler_aba("Produtos_Estoque")
    
    opcao = st.radio("Ação", ["Novo Produto", "Adicionar Unidades / Peso a Produto Existente"])
    
    if opcao == "Novo Produto":
        with st.form("form_novo_prod"):
            nome = st.text_input("Nome do Produto")
            categoria = st.text_input("Categoria (ex: Bebidas, Mercearia, Frios)")
            unidade = st.selectbox("Unidade de Medida", ["UN", "KG", "L"])
            custo = st.number_input("Custo Unitário / por Kg / por L (R$)", min_value=0.0, format="%.2f")
            preco = st.number_input("Preço de Venda Unitário / por Kg / por L (R$)", min_value=0.0, format="%.2f")
            
            # Dinâmico conforme unidade para aceitar decimais em KG/L
            if unidade in ["KG", "L"]:
                qtd_inicial = st.number_input(f"Quantidade Inicial em {unidade} (ex: 1.500)", min_value=0.0, step=0.100, format="%.3f")
                est_minimo = st.number_input(f"Estoque Mínimo em {unidade} (ex: 0.500)", min_value=0.0, step=0.100, format="%.3f")
            else:
                qtd_inicial = st.number_input(f"Quantidade Inicial em {unidade}", min_value=0, step=1)
                est_minimo = st.number_input(f"Estoque Mínimo em {unidade}", min_value=0, step=1)
            
            submitted = st.form_submit_button("Salvar Produto")
            if submitted:
                if not nome:
                    st.error("Informe o nome do produto.")
                else:
                    novo_id = int(df_produtos['ID_Produto'].max()) + 1 if not df_produtos.empty and 'ID_Produto' in df_produtos.columns and pd.to_numeric(df_produtos['ID_Produto'], errors='coerce').max() > 0 else len(df_produtos) + 1
                    novo_registro = pd.DataFrame([{
                        "ID_Produto": novo_id,
                        "Nome_Produto": nome,
                        "Categoria": categoria,
                        "Unidade_Medida": unidade,
                        "Custo_Unitario": custo,
                        "Preco_Venda": preco,
                        "Quantidade_Estoque": qtd_inicial,
                        "Estoque_Minimo": est_minimo
                    }])
                    df_atualizado = pd.concat([df_produtos, novo_registro], ignore_index=True)
                    atualizar_aba("Produtos_Estoque", df_atualizado)
                    
                    # Salva também no histórico de entradas
                    df_entradas = ler_aba("Historico_Entradas")
                    nova_entrada = pd.DataFrame([{
                        "ID_Entrada": len(df_entradas) + 1,
                        "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ID_Produto": novo_id,
                        "Quantidade_Adicionada": qtd_inicial,
                        "Custo_Unitario": custo
                    }])
                    atualizar_aba("Historico_Entradas", pd.concat([df_entradas, nova_entrada], ignore_index=True))
                    
                    st.success(f"Produto '{nome}' cadastrado com sucesso!")
                    st.rerun()

    elif opcao == "Adicionar Unidades / Peso a Produto Existente":
        if df_produtos.empty:
            st.info("Nenhum produto cadastrado ainda.")
        else:
            if 'Unidade_Medida' not in df_produtos.columns:
                df_produtos['Unidade_Medida'] = 'UN'
                
            produto_sel = st.selectbox("Selecione o Produto", df_produtos['Nome_Produto'].tolist())
            item_sel = df_produtos[df_produtos['Nome_Produto'] == produto_sel].iloc[0]
            unidade = str(item_sel['Unidade_Medida']).upper()
            
            if unidade in ["KG", "L"]:
                qtd_add = st.number_input(f"Quantidade a Adicionar ({unidade})", min_value=0.001, step=0.100, format="%.3f")
            else:
                qtd_add = st.number_input(f"Quantidade a Adicionar ({unidade})", min_value=1, step=1)
            
            if st.button("Adicionar ao Estoque"):
                df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
                df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] += qtd_add
                atualizar_aba("Produtos_Estoque", df_produtos)
                
                # Registra no histórico de entradas
                df_entradas = ler_aba("Historico_Entradas")
                nova_entrada = pd.DataFrame([{
                    "ID_Entrada": len(df_entradas) + 1,
                    "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ID_Produto": item_sel['ID_Produto'],
                    "Quantidade_Adicionada": qtd_add,
                    "Custo_Unitario": item_sel['Custo_Unitario']
                }])
                atualizar_aba("Historico_Entradas", pd.concat([df_entradas, nova_entrada], ignore_index=True))
                
                st.success(f"Adicionadas {qtd_add} ({unidade}) ao produto '{produto_sel}'.")
                st.rerun()

# -------------------------------------------------------------------
# 3. POSIÇÃO DE ESTOQUE E ALERTAS INTELIGENTES
# -------------------------------------------------------------------
elif menu == "Posição de Estoque":
    st.header("📊 Posição Geral do Estoque e Alertas")
    
    df_produtos = ler_aba("Produtos_Estoque")
    df_vendas = ler_aba("Vendas")
    
    if not df_produtos.empty:
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
        if 'Estoque_Minimo' not in df_produtos.columns:
            df_produtos['Estoque_Minimo'] = 5.0
        else:
            df_produtos['Estoque_Minimo'] = pd.to_numeric(df_produtos['Estoque_Minimo'], errors='coerce').fillna(5.0)
            
        if 'Unidade_Medida' not in df_produtos.columns:
            df_produtos['Unidade_Medida'] = 'UN'

        col_par1, col_par2 = st.columns(2)
        with col_par1:
            pct_giro = st.slider("Alerta de Estoque Baixo (% do Giro Mensal)", min_value=10, max_value=100, value=50, step=5)
        with col_par2:
            dias_sem_giro = st.number_input("Dias sem Venda para Considerar 'Sem Saída'", min_value=7, max_value=180, value=30, step=1)

        df_vendas_30d = pd.DataFrame()
        if not df_vendas.empty:
            df_vendas['Data_Hora_dt'] = pd.to_datetime(df_vendas['Data_Hora'], errors='coerce')
            data_limite = datetime.now() - timedelta(days=30)
            df_vendas_30d = df_vendas[df_vendas['Data_Hora_dt'] >= data_limite]
        
        giro_mensal = {}
        if not df_vendas_30d.empty:
            df_vendas_30d['Quantidade'] = pd.to_numeric(df_vendas_30d['Quantidade'], errors='coerce').fillna(0.0)
            giro_mensal = df_vendas_30d.groupby('ID_Produto')['Quantidade'].sum().to_dict()

        produtos_baixo = []
        for _, prod in df_produtos.iterrows():
            p_id = prod['ID_Produto']
            est_atual = float(prod['Quantidade_Estoque'])
            est_min = float(prod['Estoque_Minimo'])
            
            giro_prod = giro_mensal.get(p_id, 0.0)
            limite_giro = (pct_giro / 100.0) * giro_prod if giro_prod > 0 else est_min
            
            if est_atual <= limite_giro or est_atual <= est_min:
                produtos_baixo.append({
                    "Nome_Produto": prod['Nome_Produto'],
                    "Estoque_Atual": est_atual,
                    "Estoque_Minimo": est_min,
                    "Vendas_Ultimos_30d": giro_prod,
                    "Unidade": prod['Unidade_Medida']
                })
        
        produtos_sem_saida = []
        data_limite_sem_saida = datetime.now() - timedelta(days=dias_sem_giro)
        
        for _, prod in df_produtos.iterrows():
            p_id = prod['ID_Produto']
            est_atual = float(prod['Quantidade_Estoque'])
            
            if est_atual > 0:
                vendas_prod = pd.DataFrame()
                if not df_vendas.empty:
                    vendas_prod = df_vendas[df_vendas['ID_Produto'] == p_id]
                
                if vendas_prod.empty:
                    produtos_sem_saida.append({
                        "Nome_Produto": prod['Nome_Produto'],
                        "Estoque_Parado": est_atual,
                        "Unidade": prod['Unidade_Medida'],
                        "Ultima_Venda": "Nunca Vendido"
                    })
                else:
                    vendas_prod['Data_Hora_dt'] = pd.to_datetime(vendas_prod['Data_Hora'], errors='coerce')
                    ultima_venda_dt = vendas_prod['Data_Hora_dt'].max()
                    if pd.notnull(ultima_venda_dt) and ultima_venda_dt < data_limite_sem_saida:
                        produtos_sem_saida.append({
                            "Nome_Produto": prod['Nome_Produto'],
                            "Estoque_Parado": est_atual,
                            "Unidade": prod['Unidade_Medida'],
                            "Ultima_Venda": ultima_venda_dt.strftime("%d/%m/%Y")
                        })

        if produtos_baixo:
            st.warning(f"⚠️ **Alerta de Estoque Baixo / Reposição necessária:**")
            st.dataframe(pd.DataFrame(produtos_baixo), use_container_width=True)
            
        if produtos_sem_saida:
            st.error(f"🛑 **Alerta de Mercadorias Sem Saída (Sem vendas há {dias_sem_giro}+ dias):**")
            st.dataframe(pd.DataFrame(produtos_sem_saida), use_container_width=True)

        st.subheader("Todos os Produtos no Estoque")
        st.dataframe(df_produtos, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado no estoque.")

# -------------------------------------------------------------------
# 4. GERENCIAR / EDITAR OU EXCLUIR PRODUTOS
# -------------------------------------------------------------------
elif menu == "Gerenciar Produtos":
    st.header("🛠️ Gerenciar / Corrigir Produtos Cadastrados")
    
    df_produtos = ler_aba("Produtos_Estoque")
    
    if df_produtos.empty:
        st.info("Nenhum produto cadastrado para gerenciar.")
    else:
        prod_edicao = st.selectbox("Selecione o Produto para Editar ou Excluir", df_produtos['Nome_Produto'].tolist())
        
        if prod_edicao:
            item_atual = df_produtos[df_produtos['Nome_Produto'] == prod_edicao].iloc[0]
            
            with st.form("form_edicao"):
                novo_nome = st.text_input("Nome do Produto", value=str(item_atual['Nome_Produto']))
                nova_cat = st.text_input("Categoria", value=str(item_atual['Categoria']))
                novo_custo = st.number_input("Custo Unitário (R$)", min_value=0.0, value=float(item_atual['Custo_Unitario']), format="%.2f")
                novo_preco = st.number_input("Preço de Venda (R$)", min_value=0.0, value=float(item_atual['Preco_Venda']), format="%.2f")
                novo_est = st.number_input("Quantidade em Estoque", min_value=0.0, value=float(item_atual['Quantidade_Estoque']), format="%.3f")
                novo_min = st.number_input("Estoque Mínimo", min_value=0.0, value=float(item_atual['Estoque_Minimo']), format="%.3f")
                
                col_btn1, col_btn2 = st.columns(2)
                salvar_alt = col_btn1.form_submit_button("Salvar Alterações")
                excluir_prod = col_btn2.form_submit_button("Excluir Produto")
                
                if salvar_alt:
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Nome_Produto'] = novo_nome
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Categoria'] = nova_cat
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Custo_Unitario'] = novo_custo
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Preco_Venda'] = novo_preco
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Quantidade_Estoque'] = novo_est
                    df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, 'Estoque_Minimo'] = novo_min
                    
                    atualizar_aba("Produtos_Estoque", df_produtos)
                    st.success("Alterações salvas com sucesso!")
                    st.rerun()
                    
                if excluir_prod:
                    df_produtos = df_produtos[df_produtos['Nome_Produto'] != prod_edicao]
                    atualizar_aba("Produtos_Estoque", df_produtos)
                    st.success(f"Produto '{prod_edicao}' excluído com sucesso!")
                    st.rerun()

# -------------------------------------------------------------------
# 5. DESPESAS EXTRAS
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
# 6. FATURAMENTO E FINANCEIRO
# -------------------------------------------------------------------
elif menu == "Faturamento e Financeiro":
    st.header("📈 Visão Financeira e Resultados (DRE)")
    
    df_vendas = ler_aba("Vendas")
    df_despesas = ler_aba("Despesas_Extras")
    df_produtos = ler_aba("Produtos_Estoque")
    
    faturamento_total = 0.0
    despesas_totais = 0.0
    cmv_total = 0.0
    valor_estoque_custo = 0.0
    valor_estoque_venda = 0.0
    
    if not df_vendas.empty:
        df_vendas['Valor_Total'] = pd.to_numeric(df_vendas['Valor_Total'], errors='coerce').fillna(0.0)
        df_vendas['Quantidade'] = pd.to_numeric(df_vendas['Quantidade'], errors='coerce').fillna(0.0)
        faturamento_total = df_vendas['Valor_Total'].sum()
        
    if not df_despesas.empty:
        df_despesas['Valor'] = pd.to_numeric(df_despesas['Valor'], errors='coerce').fillna(0.0)
        despesas_totais = df_despesas['Valor'].sum()
        
    if not df_vendas.empty and not df_produtos.empty:
        df_produtos['Custo_Unitario'] = pd.to_numeric(df_produtos['Custo_Unitario'], errors='coerce').fillna(0.0)
        df_merged = df_vendas.merge(df_produtos[['ID_Produto', 'Custo_Unitario']], on='ID_Produto', how='left')
        cmv_total = (df_merged['Quantidade'] * df_merged['Custo_Unitario']).sum()
        
    if not df_produtos.empty:
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
        df_produtos['Custo_Unitario'] = pd.to_numeric(df_produtos['Custo_Unitario'], errors='coerce').fillna(0.0)
        df_produtos['Preco_Venda'] = pd.to_numeric(df_produtos['Preco_Venda'], errors='coerce').fillna(0.0)
        
        valor_estoque_custo = (df_produtos['Quantidade_Estoque'] * df_produtos['Custo_Unitario']).sum()
        valor_estoque_venda = (df_produtos['Quantidade_Estoque'] * df_produtos['Preco_Venda']).sum()
        
    lucro_bruto = faturamento_total - cmv_total
    lucro_liquido = lucro_bruto - despesas_totais
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento Bruto", f"R$ {faturamento_total:.2f}")
    c2.metric("CMV (Custo Mercadoria Vendida)", f"R$ {cmv_total:.2f}")
    c3.metric("Despesas Extras", f"R$ {despesas_totais:.2f}")
    c4.metric("Lucro Líquido Operacional", f"R$ {lucro_liquido:.2f}")
    
    st.divider()
    
    st.subheader("📦 Capital Imobilizado em Estoque")
    e1, e2, e3 = st.columns(3)
    e1.metric("Total Estoque (a Custo de Compra)", f"R$ {valor_estoque_custo:.2f}")
    e2.metric("Total Estoque (a Preço de Venda)", f"R$ {valor_estoque_venda:.2f}")
    e3.metric("Margem Potencial em Estoque", f"R$ {(valor_estoque_venda - valor_estoque_custo):.2f}")
    
    st.divider()
    
    col_vendas, col_despesas = st.columns(2)
    with col_vendas:
        st.subheader("Histórico de Vendas")
        st.dataframe(df_vendas, use_container_width=True)
        
    with col_despesas:
        st.subheader("Histórico de Despesas")
        st.dataframe(df_despesas, use_container_width=True)
