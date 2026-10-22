import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
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
    try:
        aba = sh.worksheet(nome_aba)
        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        if not df.empty:
            df.columns = [str(c).strip() for c in df.columns]
        return df
    except gspread.exceptions.WorksheetNotFound:
        nova_aba = sh.add_worksheet(title=nome_aba, rows="100", cols="20")
        if nome_aba == "Usuarios":
            nova_aba.update([["Usuario", "Senha", "Perfil", "Abas_Permitidas"], 
                             ["admin", "4D1m206570", "Admin", "Todas"]])
        return pd.DataFrame(sh.worksheet(nome_aba).get_all_records())

def atualizar_aba(nome_aba, df):
    aba = sh.worksheet(nome_aba)
    aba.clear()
    if not df.empty:
        aba.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

FUSO_BR = timezone(timedelta(hours=-3))

# -------------------------------------------------------------------
# SISTEMA DE AUTENTICAÇÃO (LOGIN)
# -------------------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_logado = ""
    st.session_state.perfil_logado = ""
    st.session_state.abas_permitidas = []

if not st.session_state.autenticado:
    st.title("🔐 Login - Sistema de Gestão Minimercado")
    
    with st.form("form_login"):
        user_input = st.text_input("Usuário").strip()
        senha_input = st.text_input("Senha", type="password").strip()
        btn_login = st.form_submit_button("Entrar", type="primary")
        
        if btn_login:
            df_usuarios = ler_aba("Usuarios")
            
            # Se a aba estiver totalmente vazia, cria o admin padrão
            if df_usuarios.empty or 'Usuario' not in df_usuarios.columns:
                df_usuarios = pd.DataFrame([{
                    "Usuario": "admin", "Senha": "4D1m206570", "Perfil": "Admin", "Abas_Permitidas": "Todas"
                }])
                atualizar_aba("Usuarios", df_usuarios)
            
            # Limpa espaços em branco dos dados vindos da planilha
            df_usuarios['Usuario'] = df_usuarios['Usuario'].astype(str).str.strip()
            df_usuarios['Senha'] = df_usuarios['Senha'].astype(str).str.strip()
            
            # Procura o usuário ignorando maiúsculas/minúsculas
            usuario_encontrado = df_usuarios[df_usuarios['Usuario'].str.lower() == user_input.lower()]
            
            if not usuario_encontrado.empty:
                senha_cadastrada = str(usuario_encontrado.iloc[0]['Senha'])
                if senha_input == senha_cadastrada:
                    st.session_state.autenticado = True
                    st.session_state.usuario_logado = user_input
                    st.session_state.perfil_logado = str(usuario_encontrado.iloc[0]['Perfil']).strip()
                    abas_str = str(usuario_encontrado.iloc[0]['Abas_Permitidas']).strip()
                    
                    if abas_str == "Todas":
                        st.session_state.abas_permitidas = [
                            "PDV (Saída de Estoque)", 
                            "Cadastro / Entrada de Estoque", 
                            "Posição de Estoque", 
                            "Gerenciar Produtos", 
                            "Despesas Extras", 
                            "Faturamento e Financeiro",
                            "Fechamento Diário & Curva ABC",
                            "Gerenciar Usuários"
                        ]
                    else:
                        st.session_state.abas_permitidas = [a.strip() for a in abas_str.split(",")]
                    
                    st.success("Login realizado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta.")
            else:
                st.error("❌ Usuário não encontrado.")
    st.stop()

# -------------------------------------------------------------------
# MENU LATERAL E CONTROLE DE ACESSOS
# -------------------------------------------------------------------
st.sidebar.write(f"👤 Logado como: **{st.session_state.usuario_logado}** ({st.session_state.perfil_logado})")
if st.sidebar.button("🚪 Sair / Logout"):
    st.session_state.autenticado = False
    st.rerun()

st.sidebar.divider()
st.title("🛒 Sistema de Gestão - Minimercado")

todas_abas = [
    "PDV (Saída de Estoque)", 
    "Cadastro / Entrada de Estoque", 
    "Posição de Estoque", 
    "Gerenciar Produtos", 
    "Despesas Extras", 
    "Faturamento e Financeiro",
    "Fechamento Diário & Curva ABC"
]

if st.session_state.perfil_logado == "Admin":
    todas_abas.append("Gerenciar Usuários")

abas_disponiveis = [aba for aba in todas_abas if aba in st.session_state.abas_permitidas or st.session_state.perfil_logado == "Admin"]

if not abas_disponiveis:
    st.error("⚠️ Este usuário não possui permissão para acessar nenhuma aba do sistema. Contate o Administrador.")
    st.stop()

menu = st.sidebar.selectbox("Navegação", abas_disponiveis)

# -------------------------------------------------------------------
# 1. PDV (VENDAS / CONSUMO / BONIFICAÇÃO / CANCELAMENTO)
# -------------------------------------------------------------------
if menu == "PDV (Saída de Estoque)":
    st.header("🛍️ Frente de Caixa e Saída de Estoque")
    
    sub_pdv = st.radio("Ação no Caixa", ["Registrar Saída / Venda", "Cancelar Venda Recente"], horizontal=True)
    df_produtos = ler_aba("Produtos_Estoque")
    
    if sub_pdv == "Registrar Saída / Venda":
        if df_produtos.empty:
            st.info("Nenhum produto cadastrado no estoque.")
        else:
            df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
            df_produtos['Preco_Venda'] = pd.to_numeric(df_produtos['Preco_Venda'], errors='coerce').fillna(0.0)
            df_produtos['Custo_Unitario'] = pd.to_numeric(df_produtos['Custo_Unitario'], errors='coerce').fillna(0.0)
            if 'Unidade_Medida' not in df_produtos.columns:
                df_produtos['Unidade_Medida'] = 'UN'
            
            produtos_disponiveis = df_produtos[df_produtos['Quantidade_Estoque'] > 0]
            
            if produtos_disponiveis.empty:
                st.warning("Não há produtos com estoque disponível.")
            else:
                tipo_operacao = st.radio("Tipo de Saída", ["🛒 Venda Normal", "🏠 Consumo Próprio / Uso Interno", "🎁 Bonificação / Cortesia"])
                produto_sel = st.selectbox("Selecione o Produto", produtos_disponiveis['Nome_Produto'].tolist())
                
                if produto_sel:
                    item = df_produtos[df_produtos['Nome_Produto'] == produto_sel].iloc[0]
                    unidade = str(item['Unidade_Medida']).upper()
                    
                    col_a, col_b, col_c = st.columns(3)
                    col_a.write(f"**Preço Venda:** R$ {item['Preco_Venda']:.2f}")
                    col_b.write(f"**Custo Unitário:** R$ {item['Custo_Unitario']:.2f}")
                    col_c.write(f"**Estoque Disponível:** {item['Quantidade_Estoque']:.3f} {unidade}")
                    
                    if unidade in ['KG', 'L']:
                        qtd = st.number_input(f"Quantidade em {unidade} (ex: 0.150 para 150g)", min_value=0.001, max_value=float(item['Quantidade_Estoque']), value=min(1.0, float(item['Quantidade_Estoque'])), step=0.050, format="%.3f")
                    else:
                        qtd = st.number_input(f"Quantidade em {unidade}", min_value=1, max_value=int(item['Quantidade_Estoque']), value=1, step=1)
                    
                    if "Venda Normal" in tipo_operacao:
                        total_operacao = float(qtd) * float(item['Preco_Venda'])
                        st.subheader(f"Total a Cobrar: R$ {total_operacao:.2f}")
                    else:
                        custo_total_consumo = float(qtd) * float(item['Custo_Unitario'])
                        st.warning(f"⚠️ **Saída sem cobrança.** Custo gerado para o caixa: **R$ {custo_total_consumo:.2f}**")
                        total_operacao = 0.0
                    
                    if "processando_venda" not in st.session_state:
                        st.session_state.processando_venda = False

                    if st.button("Confirmar Operação", type="primary", disabled=st.session_state.processando_venda):
                        st.session_state.processando_venda = True
                        
                        with st.spinner("Processando operação e atualizando estoque..."):
                            df_vendas = ler_aba("Vendas")
                            if 'Tipo_Saida' not in df_vendas.columns:
                                df_vendas['Tipo_Saida'] = "Venda Normal"
                                
                            hora_brasil = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
                            nova_venda = pd.DataFrame([{
                                "ID_Venda": len(df_vendas) + 1,
                                "Data_Hora": hora_brasil,
                                "ID_Produto": item['ID_Produto'],
                                "Nome_Produto": item['Nome_Produto'],
                                "Quantidade": qtd,
                                "Preco_Unitario": item['Preco_Venda'] if "Venda Normal" in tipo_operacao else 0.0,
                                "Valor_Total": total_operacao,
                                "Tipo_Saida": tipo_operacao
                            }])
                            atualizar_aba("Vendas", pd.concat([df_vendas, nova_venda], ignore_index=True))
                            
                            if "Venda Normal" not in tipo_operacao:
                                df_despesas = ler_aba("Despesas_Extras")
                                data_brasil = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
                                nova_despesa = pd.DataFrame([{
                                    "ID_Despesa": len(df_despesas) + 1,
                                    "Data": data_brasil,
                                    "Categoria_Despesa": tipo_operacao.replace("🛒 ", "").replace("🏠 ", "").replace("🎁 ", ""),
                                    "Descricao": f"Custo de {qtd} {unidade} de {item['Nome_Produto']}",
                                    "Valor": float(qtd) * float(item['Custo_Unitario'])
                                }])
                                atualizar_aba("Despesas_Extras", pd.concat([df_despesas, nova_despesa], ignore_index=True))
                            
                            df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] -= qtd
                            atualizar_aba("Produtos_Estoque", df_produtos)
                        
                        st.session_state.processando_venda = False
                        st.success(f"✅ Operação '{tipo_operacao}' registrada com sucesso! ({qtd} {unidade} de {produto_sel})")
                        st.balloons()

    elif sub_pdv == "Cancelar Venda Recente":
        st.subheader("🚫 Cancelamento de Venda no Caixa")
        df_vendas = ler_aba("Vendas")
        df_canceladas = ler_aba("Vendas_Canceladas")
        
        if df_vendas.empty:
            st.info("Não há vendas registradas para cancelar.")
        else:
            df_vendas['Label_Cancel'] = df_vendas.apply(lambda row: f"ID: {row['ID_Venda']} | Data: {row['Data_Hora']} | Produto: {row['Nome_Produto']} | Qtd: {row['Quantidade']} | Total: R$ {float(row['Valor_Total']):.2f}", axis=1)
            venda_para_cancelar = st.selectbox("Selecione a Venda para Cancelar", df_vendas['Label_Cancel'].tolist())
            motivo_cancelamento = st.text_input("Motivo Obrigatório (ex: Erro de digitação)")
            
            if st.button("⚠️ Confirmar Cancelamento", type="secondary"):
                if not motivo_cancelamento.strip():
                    st.error("⚠️ Informe o motivo.")
                else:
                    venda_sel = df_vendas[df_vendas['Label_Cancel'] == venda_para_cancelar].iloc[0]
                    id_venda_alvo = venda_sel['ID_Venda']
                    id_produto_alvo = venda_sel['ID_Produto']
                    qtd_estornar = float(venda_sel['Quantidade'])
                    
                    hora_cancel = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
                    registro_cancelado = pd.DataFrame([{
                        "ID_Venda_Original": id_venda_alvo,
                        "Data_Hora_Venda": venda_sel['Data_Hora'],
                        "Data_Hora_Cancelamento": hora_cancel,
                        "ID_Produto": id_produto_alvo,
                        "Nome_Produto": venda_sel['Nome_Produto'],
                        "Quantidade_Estornada": qtd_estornar,
                        "Valor_Total": venda_sel['Valor_Total'],
                        "Motivo": motivo_cancelamento
                    }])
                    atualizar_aba("Vendas_Canceladas", pd.concat([df_canceladas, registro_cancelado], ignore_index=True))
                    
                    df_produtos['ID_Produto'] = pd.to_numeric(df_produtos['ID_Produto'], errors='coerce')
                    df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
                    mask_prod = df_produtos['ID_Produto'] == id_produto_alvo
                    if mask_prod.any():
                        df_produtos.loc[mask_prod, 'Quantidade_Estoque'] += qtd_estornar
                        atualizar_aba("Produtos_Estoque", df_produtos)
                    
                    df_vendas_novo = df_vendas[df_vendas['ID_Venda'] != id_venda_alvo].drop(columns=['Label_Cancel'], errors='ignore')
                    atualizar_aba("Vendas", df_vendas_novo)
                    st.success(f"✅ Venda ID {id_venda_alvo} cancelada e estoque estornado!")

# -------------------------------------------------------------------
# 2. CADASTRO E ENTRADA DE ESTOQUE
# -------------------------------------------------------------------
elif menu == "Cadastro / Entrada de Estoque":
    st.header("📦 Alimentar / Cadastrar Estoque")
    df_produtos = ler_aba("Produtos_Estoque")
    opcao = st.radio("Ação", ["Novo Produto", "Adicionar Unidades / Peso a Produto Existente"])
    
    if opcao == "Novo Produto":
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Produto")
            categoria = st.text_input("Categoria")
            unidade = st.selectbox("Unidade", ["UN", "KG", "L"])
        with col2:
            custo = st.number_input("Custo Unitário (R$)", min_value=0.0, format="%.2f")
            preco = st.number_input("Preço de Venda (R$)", min_value=0.0, format="%.2f")
            qtd_inicial = st.number_input("Quantidade Inicial", min_value=0.0, step=0.1 if unidade in ["KG", "L"] else 1.0, format="%.3f" if unidade in ["KG", "L"] else "%.0f")
            
        if st.button("Salvar Produto", type="primary"):
            if not nome.strip():
                st.error("Informe o nome do produto.")
            else:
                novo_id = int(pd.to_numeric(df_produtos['ID_Produto'], errors='coerce').max()) + 1 if not df_produtos.empty and pd.to_numeric(df_produtos['ID_Produto'], errors='coerce').max() > 0 else len(df_produtos) + 1
                novo_registro = pd.DataFrame([{"ID_Produto": novo_id, "Nome_Produto": nome, "Categoria": categoria, "Unidade_Medida": unidade, "Custo_Unitario": custo, "Preco_Venda": preco, "Quantidade_Estoque": float(qtd_inicial), "Estoque_Minimo": 0.0}])
                atualizar_aba("Produtos_Estoque", pd.concat([df_produtos, novo_registro], ignore_index=True))
                
                df_entradas = ler_aba("Historico_Entradas")
                hora_brasil = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
                nova_entrada = pd.DataFrame([{"ID_Entrada": len(df_entradas) + 1, "Data": hora_brasil, "ID_Produto": novo_id, "Quantidade_Adicionada": float(qtd_inicial), "Custo_Unitario": custo}])
                atualizar_aba("Historico_Entradas", pd.concat([df_entradas, nova_entrada], ignore_index=True))
                st.success(f"✅ Produto '{nome}' cadastrado!")
                st.balloons()

    elif opcao == "Adicionar Unidades / Peso a Produto Existente":
        if df_produtos.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            produto_sel = st.selectbox("Produto", df_produtos['Nome_Produto'].tolist())
            item_sel = df_produtos[df_produtos['Nome_Produto'] == produto_sel].iloc[0]
            unidade = str(item_sel['Unidade_Medida']).upper()
            qtd_add = st.number_input(f"Quantidade a Adicionar ({unidade})", min_value=0.001, step=0.1 if unidade in ["KG", "L"] else 1.0, format="%.3f" if unidade in ["KG", "L"] else "%.0f")
            
            if st.button("Adicionar ao Estoque", type="primary"):
                df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
                df_produtos.loc[df_produtos['Nome_Produto'] == produto_sel, 'Quantidade_Estoque'] += float(qtd_add)
                atualizar_aba("Produtos_Estoque", df_produtos)
                
                df_entradas = ler_aba("Historico_Entradas")
                hora_brasil = datetime.now(FUSO_BR).strftime("%Y-%m-%d %H:%M:%S")
                nova_entrada = pd.DataFrame([{"ID_Entrada": len(df_entradas) + 1, "Data": hora_brasil, "ID_Produto": item_sel['ID_Produto'], "Quantidade_Adicionada": float(qtd_add), "Custo_Unitario": item_sel['Custo_Unitario']}])
                atualizar_aba("Historico_Entradas", pd.concat([df_entradas, nova_entrada], ignore_index=True))
                st.success(f"✅ Adicionado com sucesso!")

# -------------------------------------------------------------------
# 3. POSIÇÃO DE ESTOQUE
# -------------------------------------------------------------------
elif menu == "Posição de Estoque":
    st.header("📊 Posição Geral do Estoque e Alertas")
    df_produtos = ler_aba("Produtos_Estoque")
    df_vendas = ler_aba("Vendas")
    
    if not df_produtos.empty:
        df_produtos['Quantidade_Estoque'] = pd.to_numeric(df_produtos['Quantidade_Estoque'], errors='coerce').fillna(0.0)
        df_produtos['Estoque_Minimo'] = pd.to_numeric(df_produtos.get('Estoque_Minimo', 0), errors='coerce').fillna(0.0)
        
        col1, col2 = st.columns(2)
        with col1:
            pct_giro = st.slider("Alerta de Estoque Baixo (% do Giro)", 10, 100, 50, 5)
        with col2:
            dias_sem_giro = st.number_input("Dias sem Venda ('Sem Saída')", 7, 180, 30, 1)

        df_vendas_30d = pd.DataFrame()
        if not df_vendas.empty:
            df_vendas['Data_Hora_dt'] = pd.to_datetime(df_vendas['Data_Hora'], errors='coerce')
            data_limite = datetime.now(FUSO_BR).replace(tzinfo=None) - timedelta(days=30)
            df_vendas_30d = df_vendas[df_vendas['Data_Hora_dt'] >= data_limite]
        
        giro_mensal = df_vendas_30d.groupby('ID_Produto')['Quantidade'].sum().to_dict() if not df_vendas_30d.empty else {}
        
        produtos_baixo = []
        for _, prod in df_produtos.iterrows():
            est_atual = float(prod['Quantidade_Estoque'])
            est_min = float(prod['Estoque_Minimo'])
            unidade = str(prod['Unidade_Medida']).upper()
            giro_prod = giro_mensal.get(prod['ID_Produto'], 0.0)
            
            limite = est_min if est_min > 0 else (giro_prod * (pct_giro / 100.0) if giro_prod > 0 else (1.0 if unidade in ['KG', 'L'] else 10.0))
            if est_atual <= limite:
                produtos_baixo.append({"Nome_Produto": prod['Nome_Produto'], "Estoque_Atual": est_atual, "Limite": limite, "Unidade": unidade})
                
        if produtos_baixo:
            st.warning("⚠️ **Alerta de Estoque Baixo:**")
            st.dataframe(pd.DataFrame(produtos_baixo), use_container_width=True)
            
        st.subheader("Estoque Completo")
        st.dataframe(df_produtos, use_container_width=True)

# -------------------------------------------------------------------
# 4. GERENCIAR PRODUTOS
# -------------------------------------------------------------------
elif menu == "Gerenciar Produtos":
    st.header("🛠️ Gerenciar / Corrigir Produtos")
    df_produtos = ler_aba("Produtos_Estoque")
    if df_produtos.empty:
        st.info("Nenhum produto cadastrado.")
    else:
        prod_edicao = st.selectbox("Selecione o Produto", df_produtos['Nome_Produto'].tolist())
        item_atual = df_produtos[df_produtos['Nome_Produto'] == prod_edicao].iloc[0]
        
        with st.form("form_edicao"):
            novo_nome = st.text_input("Nome", value=str(item_atual['Nome_Produto']))
            nova_cat = st.text_input("Categoria", value=str(item_atual['Categoria']))
            novo_custo = st.number_input("Custo (R$)", value=float(item_atual['Custo_Unitario']), format="%.2f")
            novo_preco = st.number_input("Preço Venda (R$)", value=float(item_atual['Preco_Venda']), format="%.2f")
            novo_est = st.number_input("Qtd Estoque", value=float(item_atual['Quantidade_Estoque']), format="%.3f")
            
            c1, c2 = st.columns(2)
            salvar = c1.form_submit_button("Salvar")
            excluir = c2.form_submit_button("Excluir")
            
            if salvar:
                df_produtos.loc[df_produtos['Nome_Produto'] == prod_edicao, ['Nome_Produto', 'Categoria', 'Custo_Unitario', 'Preco_Venda', 'Quantidade_Estoque']] = [novo_nome, nova_cat, novo_custo, novo_preco, novo_est]
                atualizar_aba("Produtos_Estoque", df_produtos)
                st.success("Atualizado!")
            if excluir:
                atualizar_aba("Produtos_Estoque", df_produtos[df_produtos['Nome_Produto'] != prod_edicao])
                st.success("Excluído!")

# -------------------------------------------------------------------
# 5. DESPESAS EXTRAS
# -------------------------------------------------------------------
elif menu == "Despesas Extras":
    st.header("💸 Despesas Extras")
    with st.form("form_despesas"):
        data_desp = st.date_input("Data")
        cat = st.selectbox("Categoria", ["Equipamentos", "Energia Elétrica", "Aluguel", "Manutenção", "Outros"])
        desc = st.text_input("Descrição")
        val = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        if st.form_submit_button("Registrar"):
            df_desp = ler_aba("Despesas_Extras")
            nova = pd.DataFrame([{"ID_Despesa": len(df_desp) + 1, "Data": str(data_desp), "Categoria_Despesa": cat, "Descricao": desc, "Valor": val}])
            atualizar_aba("Despesas_Extras", pd.concat([df_desp, nova], ignore_index=True))
            st.success("Despesa registrada!")

# -------------------------------------------------------------------
# 6. FATURAMENTO E FINANCEIRO
# -------------------------------------------------------------------
elif menu == "Faturamento e Financeiro":
    st.header("📈 Visão Financeira & Auditoria")
    df_vendas = ler_aba("Vendas")
    df_despesas = ler_aba("Despesas_Extras")
    df_canceladas = ler_aba("Vendas_Canceladas")
    
    faturamento = df_vendas[df_vendas['Tipo_Saida'].str.contains("Venda Normal", na=False)]['Valor_Total'].astype(float).sum() if not df_vendas.empty else 0.0
    despesas = df_despesas['Valor'].astype(float).sum() if not df_despesas.empty else 0.0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Faturamento Bruto", f"R$ {faturamento:.2f}")
    c2.metric("Despesas Totais", f"R$ {despesas:.2f}")
    c3.metric("Resultado Operacional", f"R$ {(faturamento - despesas):.2f}")
    
    st.divider()
    st.subheader("Histórico de Vendas Ativas")
    st.dataframe(df_vendas, use_container_width=True)
    
    if not df_canceladas.empty:
        st.subheader("🕵️ Auditoria de Vendas Canceladas")
        st.dataframe(df_canceladas, use_container_width=True)

# -------------------------------------------------------------------
# 7. FECHAMENTO DIÁRIO & CURVA ABC
# -------------------------------------------------------------------
elif menu == "Fechamento Diário & Curva ABC":
    st.header("📆 Fechamento Diário & Curva ABC")
    df_vendas = ler_aba("Vendas")
    tab1, tab2 = st.tabs(["Caixa Diário", "Curva ABC"])
    
    with tab1:
        data_sel = st.date_input("Data", value=datetime.now(FUSO_BR))
        if not df_vendas.empty:
            df_vendas['Data_Sem_Hora'] = pd.to_datetime(df_vendas['Data_Hora'], errors='coerce').dt.strftime("%Y-%m-%d")
            vendas_dia = df_vendas[df_vendas['Data_Sem_Hora'] == data_sel.strftime("%Y-%m-%d")]
            st.metric("Faturamento do Dia", f"R$ {vendas_dia['Valor_Total'].astype(float).sum():.2f}")
            st.dataframe(vendas_dia, use_container_width=True)
            
    with tab2:
        if not df_vendas.empty:
            ranking = df_vendas.groupby('Nome_Produto')['Valor_Total'].astype(float).sum().reset_index().sort_values(by='Valor_Total', ascending=False)
            st.dataframe(ranking, use_container_width=True)

# -------------------------------------------------------------------
# 8. GERENCIAR USUÁRIOS (Exclusivo para Admins)
# -------------------------------------------------------------------
elif menu == "Gerenciar Usuários":
    st.header("👥 Controle de Usuários e Permissões")
    df_usuarios = ler_aba("Usuarios")
    
    st.subheader("Usuários Cadastrados")
    st.dataframe(df_usuarios, use_container_width=True)
    
    st.divider()
    st.subheader("Cadastrar Novo Usuário / Operador")
    
    with st.form("form_novo_usuario"):
        novo_user = st.text_input("Nome do Usuário (ex: operador1)")
        nova_senha = st.text_input("Senha", type="password")
        perfil = st.selectbox("Perfil", ["Operador", "Admin"])
        
        st.write("**Selecione as abas que este usuário poderá acessar:**")
        p_pdv = st.checkbox("PDV (Saída de Estoque)", value=True)
        p_est = st.checkbox("Cadastro / Entrada de Estoque", value=False)
        p_pos = st.checkbox("Posição de Estoque", value=True)
        p_ger = st.checkbox("Gerenciar Produtos", value=False)
        p_des = st.checkbox("Despesas Extras", value=False)
        p_fin = st.checkbox("Faturamento e Financeiro", value=False)
        p_fec = st.checkbox("Fechamento Diário & Curva ABC", value=False)
        
        btn_salvar_user = st.form_submit_button("Cadastrar Usuário", type="primary")
        
        if btn_salvar_user:
            if not novo_user.strip() or not nova_senha.strip():
                st.error("Preencha o usuário e a senha.")
            else:
                lista_abas = []
                if p_pdv: lista_abas.append("PDV (Saída de Estoque)")
                if p_est: lista_abas.append("Cadastro / Entrada de Estoque")
                if p_pos: lista_abas.append("Posição de Estoque")
                if p_ger: lista_abas.append("Gerenciar Produtos")
                if p_des: lista_abas.append("Despesas Extras")
                if p_fin: lista_abas.append("Faturamento e Financeiro")
                if p_fec: lista_abas.append("Fechamento Diário & Curva ABC")
                
                abas_string = "Todas" if perfil == "Admin" else ", ".join(lista_abas)
                
                novo_reg = pd.DataFrame([{
                    "Usuario": novo_user.strip(),
                    "Senha": nova_senha.strip(),
                    "Perfil": perfil,
                    "Abas_Permitidas": abas_string
                }])
                
                atualizar_aba("Usuarios", pd.concat([df_usuarios, novo_reg], ignore_index=True))
                st.success(f"✅ Usuário '{novo_user}' cadastrado com sucesso!")
                st.rerun()
