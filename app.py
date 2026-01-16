# app.py
# BabeliUM — Criador de Fichas de Exercícios
# Interface Gráfica (Streamlit)

import streamlit as st
import copy
import sys
import os

# --- GARANTIR QUE OS IMPORTS FUNCIONAM ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from models import TA, Question, ChoiceOption, Blank, MatchPair, QuestionMeta, new_id_default
    from utils import new_id, count_gaps
    from validators import validate_ficha, update_ficha_status
    from export import build_moodle_xml_stub
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}")
    st.stop()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="BabeliUM Editor",
    page_icon="⚡",
    layout="wide"
)

# --- CONSTANTES DE UI ---
UI_TYPES = {
    "Texto com lacunas (Escrever)": "cloze",
    "Texto com lacunas (Menu/Seleção)": "cloze_mc", # NOVO
    "Escolha múltipla (1 correta)": "multichoice_single",
    "Escolha múltipla (várias corretas)": "multichoice_multi",
    "Verdadeiro/Falso": "truefalse",
    "Associação (Matching)": "matching",
    "Resposta Curta": "shortanswer",
    "Ensaio (Texto livre)": "essay",
    "Texto de Apoio / Instrução (sem resposta)": "description" # NOVO
}

# Inverter o dicionário para lookups fáceis
TYPE_TO_LABEL = {v: k for k, v in UI_TYPES.items()}

# --- GESTÃO DE ESTADO (SESSION STATE) ---
if "ta" not in st.session_state:
    # Cria uma nova ficha vazia ao iniciar
    st.session_state.ta = TA(ta_id=new_id("ta"))

if "active_view" not in st.session_state:
    st.session_state.active_view = "Editor de Ficha" # "Editor de Ficha" | "Editor de Questão"

if "active_qid" not in st.session_state:
    st.session_state.active_qid = None # ID da questão a ser editada

# Atalho para variáveis
ta = st.session_state.ta

# --- FUNÇÕES AUXILIARES DE UI ---
def get_question_by_id(qid):
    for q in ta.questions:
        if q.qid == qid:
            return q
    return None

def move_question(idx, direction):
    # direction: -1 (cima), +1 (baixo)
    new_idx = idx + direction
    if 0 <= new_idx < len(ta.questions):
        ta.questions[idx], ta.questions[new_idx] = ta.questions[new_idx], ta.questions[idx]

def delete_question(idx):
    ta.questions.pop(idx)

# ==============================================================================
# VIEW 1: EDITOR DE FICHA (DASHBOARD)
# ==============================================================================
def render_ficha_editor():
    st.title("⚡ BabeliUM Editor")
    
    # 1. Cabeçalho da Ficha
    with st.container():
        c1, c2, c3 = st.columns([3, 2, 2])
        ta.ta_name = c1.text_input("Nome da Ficha", value=ta.ta_name)
        ta.course = c2.text_input("Curso / Nível", value=ta.course)
        
        with c3:
            st.write(" ") 
            if st.button("➕ Nova Questão", use_container_width=True, type="primary"):
                st.session_state.active_qid = None # None significa "criar nova"
                st.session_state.active_view = "Editor de Questão"
                st.rerun()

    st.divider()

    # 2. Barra de Ferramentas da Lista
    col_info, col_view = st.columns([3, 1])
    with col_info:
        st.caption(f"Total: **{len(ta.questions)}** itens na ficha.")
    with col_view:
        view_mode = st.radio("Ver como:", ["Lista Compacta", "Cartões Abertos"], horizontal=True, label_visibility="collapsed")

    # 3. Listagem das Questões
    if not ta.questions:
        st.info("A ficha está vazia. Clique em 'Nova Questão' para começar.")
    else:
        for idx, q in enumerate(ta.questions):
            
            # Ícones Visuais
            icon = "❓"
            if q.moodle_type == "cloze": icon = "📝"
            elif q.moodle_type == "cloze_mc": icon = "🔽"
            elif q.moodle_type.startswith("multichoice"): icon = "🔘"
            elif q.moodle_type == "truefalse": icon = "⚖️"
            elif q.moodle_type == "matching": icon = "🔗"
            elif q.moodle_type == "description": icon = "📄"
            elif q.moodle_type == "essay": icon = "✍️"

            titulo = q.title if q.title.strip() else f"(Sem título - {idx+1})"
            pontos = f"{q.meta.points} pts" if q.moodle_type != "description" else "Info"

            # --- MODO LISTA COMPACTA (ACORDEÃO) ---
            if view_mode == "Lista Compacta":
                with st.expander(f"{idx+1}. {icon} {titulo}  —  {pontos}", expanded=False):
                    c_prev, c_acts = st.columns([4, 1])
                    with c_prev:
                        st.caption(f"**Tipo:** {TYPE_TO_LABEL.get(q.ui_type, q.ui_type)} | **Secção:** {q.section}")
                        clean_text = q.prompt.replace("\n", " ")
                        st.markdown(f"_{clean_text[:150] + '...' if len(clean_text)>150 else clean_text}_")
                    
                    with c_acts:
                        if st.button("✏️ Editar", key=f"ed_c_{q.qid}", use_container_width=True):
                            st.session_state.active_qid = q.qid
                            st.session_state.active_view = "Editor de Questão"
                            st.rerun()
                        if st.button("🗑️ Apagar", key=f"del_c_{q.qid}", use_container_width=True):
                            delete_question(idx)
                            st.rerun()
                        # Setas
                        c_up, c_down = st.columns(2)
                        with c_up:
                            if idx > 0 and st.button("⬆️", key=f"up_{q.qid}"):
                                move_question(idx, -1)
                                st.rerun()
                        with c_down:
                            if idx < len(ta.questions)-1 and st.button("⬇️", key=f"dw_{q.qid}"):
                                move_question(idx, 1)
                                st.rerun()

            # --- MODO CARTÕES ABERTOS ---
            else:
                with st.container(border=True):
                    st.markdown(f"### {idx+1}. {icon} {titulo}")
                    st.markdown(q.prompt, unsafe_allow_html=True)
                    b1, b2 = st.columns([1, 4])
                    if b1.button("Editar", key=f"ed_d_{q.qid}"):
                        st.session_state.active_qid = q.qid
                        st.session_state.active_view = "Editor de Questão"
                        st.rerun()
    
    st.divider()
    
    # 4. Botão de Exportação
    if st.button("📦 Gerar MoodleXML Final", use_container_width=True, type="secondary"):
        st.session_state.active_view = "Exportar"
        st.rerun()


# ==============================================================================
# VIEW 2: EDITOR DE QUESTÃO
# ==============================================================================
def render_question_editor():
    # 1. Carregar ou Criar Questão de Rascunho
    if "draft_q" not in st.session_state:
        if st.session_state.active_qid:
            # Editar existente: criar cópia profunda para não alterar direto antes de salvar
            original = get_question_by_id(st.session_state.active_qid)
            st.session_state.draft_q = copy.deepcopy(original)
        else:
            # Nova questão
            st.session_state.draft_q = Question(
                qid=new_id("q"),
                ui_type="Escolha múltipla (1 correta)",
                moodle_type="multichoice_single",
                prompt=""
            )
    
    q = st.session_state.draft_q

    # Cabeçalho com Botão Voltar
    c_back, c_title = st.columns([1, 5])
    if c_back.button("🔙 Voltar"):
        del st.session_state.draft_q
        st.session_state.active_view = "Editor de Ficha"
        st.rerun()
    c_title.subheader("Editar Questão")

    # --- CONFIGURAÇÕES GERAIS ---
    with st.container(border=True):
        col_type, col_sec, col_pts = st.columns([2, 1, 1])
        
        # Seletor de Tipo (Reseta campos se mudar)
        new_ui_type = col_type.selectbox(
            "Tipo de Pergunta", 
            options=list(UI_TYPES.keys()), 
            index=list(UI_TYPES.keys()).index(q.ui_type) if q.ui_type in UI_TYPES else 0
        )
        
        # Reset lógico se o tipo mudar
        if new_ui_type != q.ui_type:
            q.ui_type = new_ui_type
            q.moodle_type = UI_TYPES[new_ui_type]
            # Reset específico
            if q.moodle_type == "description": 
                q.meta.points = 0.0
                q.blanks = []
                q.options = []
            elif q.moodle_type == "truefalse":
                q.options = [ChoiceOption(new_id("o"), "", True), ChoiceOption(new_id("o"), "", False)]
                q.tf_require_correction = False
            st.rerun()

        q.section = col_sec.text_input("Secção / Grupo", value=q.section)
        
        if q.moodle_type == "description":
            col_pts.text_input("Pontos", value="0.0", disabled=True)
        else:
            q.meta.points = col_pts.number_input("Pontos", value=q.meta.points, min_value=0.1, step=0.5)

        q.title = st.text_input("Título Interno (não aparece para o aluno)", value=q.title, placeholder="Ex: Q1 - Interpretação")

    # --- ENUNCIADO DINÂMICO ---
    mt = q.moodle_type
    st.markdown("### 1. Enunciado / Texto")
    
    placeholder_txt = "Escreva a pergunta aqui..."
    if mt == "truefalse": placeholder_txt = "Ex: Classifique as seguintes afirmações como Verdadeiras ou Falsas..."
    elif mt.startswith("multichoice"): placeholder_txt = "Ex: Qual a capital de França?"
    elif mt == "cloze" or mt == "cloze_mc": placeholder_txt = "Escreva o texto e use [ ] onde quer criar as lacunas/menus."
    elif mt == "description": placeholder_txt = "Cole aqui o texto de leitura..."

    q.prompt = st.text_area("Texto", value=q.prompt, height=150, placeholder=placeholder_txt, label_visibility="collapsed")

    # --- EDITORES ESPECÍFICOS POR TIPO ---
    
    # === A. CLOZE (ESCREVER & MENUS) ===
    if mt == "cloze" or mt == "cloze_mc":
        st.divider()
        is_dropdown = (mt == "cloze_mc")
        st.markdown(f"### 2. Configurar {'Menus' if is_dropdown else 'Lacunas'}")
        
        n_gaps = count_gaps(q.prompt)
        if n_gaps == 0:
            st.warning("⚠️ Insira `[ ]` no texto acima para criar lacunas.")
        else:
            # Sincronizar lista de blanks
            current_len = len(q.blanks)
            if current_len < n_gaps:
                for i in range(current_len, n_gaps):
                    q.blanks.append(Blank(bid=new_id("b"), label=f"L{i+1}", answers=[""], distractors=[]))
            elif current_len > n_gaps:
                q.blanks = q.blanks[:n_gaps]

            # Mostrar Grelha
            cols = st.columns(2 if is_dropdown else 3)
            for i, b in enumerate(q.blanks):
                with cols[i % len(cols)]:
                    with st.container(border=True):
                        st.markdown(f"**Lacuna {i+1}**")
                        # Resposta Correta
                        ans_val = b.answers[0] if b.answers else ""
                        new_ans = st.text_input(f"✅ Correta", value=ans_val, key=f"ans_{b.bid}")
                        b.answers = [new_ans]
                        
                        # Se for Menu, pedir distratores
                        if is_dropdown:
                            dist_val = "; ".join(b.distractors)
                            new_dist = st.text_input(f"❌ Erradas (sep. por ';')", value=dist_val, key=f"dist_{b.bid}")
                            b.distractors = [d.strip() for d in new_dist.split(";") if d.strip()]

    # === B. ESCOLHA MÚLTIPLA ===
    elif mt.startswith("multichoice"):
        st.divider()
        st.markdown("### 2. Opções de Resposta")
        
        for i, opt in enumerate(q.options):
            c_del, c_txt, c_corr = st.columns([0.5, 4, 1.5])
            if c_del.button("🗑️", key=f"del_mc_{opt.oid}"):
                q.options.pop(i)
                st.rerun()
            
            opt.text = c_txt.text_input(f"Opção {i+1}", value=opt.text, key=f"txt_mc_{opt.oid}", label_visibility="collapsed")
            
            # Checkbox para correta
            if mt == "multichoice_single":
                # Lógica de Radio Button simulada
                is_checked = c_corr.checkbox("Correta", value=opt.is_correct, key=f"chk_mc_{opt.oid}")
                if is_checked and not opt.is_correct:
                    # Desmarcar as outras
                    for o in q.options: o.is_correct = False
                    opt.is_correct = True
                    st.rerun()
            else:
                opt.is_correct = c_corr.checkbox("Correta", value=opt.is_correct, key=f"chk_mc_{opt.oid}")

        if st.button("➕ Adicionar Opção"):
            q.options.append(ChoiceOption(new_id("o"), ""))
            st.rerun()

    # === C. VERDADEIRO / FALSO (MATRIZ) ===
    elif mt == "truefalse":
        st.divider()
        st.markdown("### 2. Afirmações")
        
        c_help, c_toggle = st.columns([2, 2])
        c_help.info("Adicione frases para o aluno classificar.")
        q.tf_require_correction = c_toggle.toggle("Pedir correção das falsas?", value=q.tf_require_correction)

        if not q.options:
            st.warning("Adicione pelo menos uma afirmação.")

        for i, opt in enumerate(q.options):
            with st.container(border=True):
                c_del, c_txt, c_rad = st.columns([0.5, 4, 2])
                if c_del.button("🗑️", key=f"del_vf_{opt.oid}"):
                    q.options.pop(i)
                    st.rerun()
                
                opt.text = c_txt.text_input("Frase", value=opt.text, key=f"txt_vf_{opt.oid}", label_visibility="collapsed")
                
                sel = c_rad.radio("Gabarito", ["V", "F"], 
                                  index=0 if opt.is_correct else 1, 
                                  key=f"rad_vf_{opt.oid}", horizontal=True, label_visibility="collapsed")
                opt.is_correct = (sel == "V")
        
        if st.button("➕ Adicionar Afirmação"):
            q.options.append(ChoiceOption(new_id("o"), "", True))
            st.rerun()

    # === D. ASSOCIAÇÃO ===
    elif mt == "matching":
        st.divider()
        st.markdown("### 2. Pares de Associação")
        for i, p in enumerate(q.pairs):
            c_del, c_left, c_right = st.columns([0.5, 2.5, 2.5])
            if c_del.button("🗑️", key=f"del_mat_{p.pid}"):
                q.pairs.pop(i)
                st.rerun()
            p.left = c_left.text_input("Pergunta (A)", value=p.left, key=f"l_{p.pid}", label_visibility="collapsed")
            p.right = c_right.text_input("Resposta (B)", value=p.right, key=f"r_{p.pid}", label_visibility="collapsed")
        
        if st.button("➕ Adicionar Par"):
            q.pairs.append(MatchPair(new_id("p"), "", ""))
            st.rerun()

    # === E. TEXTO DE APOIO ===
    elif mt == "description":
        st.info("ℹ️ Este item serve apenas para mostrar texto ou imagens. Não tem perguntas nem notas.")

    # --- RODAPÉ: GUARDAR ---
    st.divider()
    c_save, c_save_new = st.columns(2)
    
    if c_save.button("💾 Guardar Alterações", type="primary", use_container_width=True):
        # Lógica de salvar
        if st.session_state.active_qid:
            # Atualizar existente
            for i, existing_q in enumerate(ta.questions):
                if existing_q.qid == st.session_state.active_qid:
                    ta.questions[i] = copy.deepcopy(q)
                    break
        else:
            # Adicionar nova
            ta.questions.append(copy.deepcopy(q))
        
        del st.session_state.draft_q
        st.session_state.active_view = "Editor de Ficha"
        st.session_state.active_qid = None
        st.rerun()
    
    if c_save_new.button("💾 Guardar e Criar Nova", use_container_width=True):
        # Adicionar a atual à lista
        if st.session_state.active_qid:
            for i, existing_q in enumerate(ta.questions):
                if existing_q.qid == st.session_state.active_qid:
                    ta.questions[i] = copy.deepcopy(q)
                    break
        else:
            ta.questions.append(copy.deepcopy(q))
        
        # Preparar a próxima (Limpar campos mas manter tipo)
        next_q = Question(new_id("q"), q.ui_type, q.moodle_type, prompt="", section=q.section)
        # Se for V/F ou Matching, inicializar listas
        if next_q.moodle_type == "truefalse":
            next_q.options = [ChoiceOption(new_id("o"), "", True)]
        
        st.session_state.draft_q = next_q
        st.session_state.active_qid = None # Passa a ser uma criação nova
        st.rerun()


# ==============================================================================
# VIEW 3: EXPORTAR E VALIDAR
# ==============================================================================
def render_export_view():
    st.title("📦 Exportar para Moodle")
    if st.button("🔙 Voltar ao Editor"):
        st.session_state.active_view = "Editor de Ficha"
        st.rerun()
    
    st.divider()
    
    # 1. Validar
    issues = validate_ficha(ta)
    update_ficha_status(ta, issues)
    
    has_errors = any(i.level == "ERRO" for i in issues)
    
    if has_errors:
        st.error("⚠️ Foram encontrados erros que impedem a exportação correta.")
    else:
        st.success("✅ A ficha está válida e pronta a exportar!")

    # Mostrar relatório
    for i in issues:
        color = "red" if i.level == "ERRO" else "orange"
        st.markdown(f":{color}[**{i.level}**] em _{i.where}_: {i.message}")

    # 2. Gerar XML
    xml_output = build_moodle_xml_stub(ta)
    
    st.subheader("Pré-visualização do XML")
    with st.expander("Ver código XML"):
        st.code(xml_output, language="xml")

    # 3. Download
    st.download_button(
        label="📥 Descarregar Ficheiro (.xml)",
        data=xml_output,
        file_name=f"ficha_{ta.ta_name.replace(' ', '_')}.xml",
        mime="application/xml"
    )

# ==============================================================================
# CONTROLADOR PRINCIPAL
# ==============================================================================
if st.session_state.active_view == "Editor de Ficha":
    render_ficha_editor()
elif st.session_state.active_view == "Editor de Questão":
    render_question_editor()
elif st.session_state.active_view == "Exportar":
    render_export_view()