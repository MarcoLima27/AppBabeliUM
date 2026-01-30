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
# VIEW 2: EDITOR DE QUESTÃO (CORRIGIDO E LIMPO)
# ==============================================================================
def render_question_editor():
    # 1. Carregar ou Criar Questão
    if "draft_q" not in st.session_state:
        if st.session_state.active_qid:
            original = get_question_by_id(st.session_state.active_qid)
            st.session_state.draft_q = copy.deepcopy(original)
        else:
            st.session_state.draft_q = Question(
                qid=new_id("q"), ui_type="Escolha múltipla (1 correta)",
                moodle_type="multichoice_single", prompt=""
            )
    
    q = st.session_state.draft_q

    # --- CABEÇALHO ---
    c_back, c_title = st.columns([1, 5])
    if c_back.button("🔙 Voltar"):
        del st.session_state.draft_q
        st.session_state.active_view = "Editor de Ficha"
        st.rerun()
    c_title.subheader("Editar Questão")

    # --- BLOCO 1: CONFIGURAÇÕES ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        
        # Tipo de Pergunta
        new_ui_type = c1.selectbox("Tipo de Pergunta", options=list(UI_TYPES.keys()), 
                                   index=list(UI_TYPES.keys()).index(q.ui_type) if q.ui_type in UI_TYPES else 0)
        
        if new_ui_type != q.ui_type:
            q.ui_type = new_ui_type
            q.moodle_type = UI_TYPES[new_ui_type]
            # Resets de segurança
            if q.moodle_type == "truefalse":
                q.options = [ChoiceOption(new_id("o"), "Verdadeiro", True), ChoiceOption(new_id("o"), "Falso", False)]
            elif "multichoice" in q.moodle_type:
                q.options = [ChoiceOption(new_id("o"), ""), ChoiceOption(new_id("o"), "")]
            elif q.moodle_type == "matching":
                q.pairs = [MatchPair(new_id("p"), "", "")]
            st.rerun()

        # Pontos
        if q.moodle_type == "description":
            c2.text_input("Pontos", value="0.0", disabled=True)
        else:
            q.meta.points = c2.number_input("Pontos", value=q.meta.points, min_value=0.1, step=0.5)

        # Secção
        q.section = c3.text_input("Secção", value=q.section, placeholder="Ex: Gramática")
        q.title = st.text_input("Título Interno (Opcional)", value=q.title, placeholder="Ex: Q1 - Passado Perfeito")

    mt = q.moodle_type

    # --- BLOCO 2: ENUNCIADO (EM CIMA) ---
    st.markdown("### 1. Enunciado")
    
    # AJUDA E EXEMPLOS (Só para Cloze)
    if mt in ["cloze", "cloze_mc"]:
        col_btn, col_help = st.columns([1, 3])
        # Botão de inserir lacuna
        if col_btn.button("➕ Inserir [ ]", help="Adiciona uma lacuna ao fim do texto", use_container_width=True):
            q.prompt += " [ ] "
            st.rerun()
            
        # Menu de Exemplos
        with col_help.expander("Ver exemplos prontos"):
            # --- A LINHA ABAIXO É A EXPLICAÇÃO QUE QUERIAS ---
            st.info("Clique num dos botões abaixo para preencher a caixa de texto com um modelo pronto:")
            
            ce1, ce2 = st.columns(2)
            if ce1.button("📝 Gramática (Verbos)"):
                q.prompt = "Ontem, o gato [ ] (beber) leite."
                st.rerun()
            if ce2.button("🌍 Vocabulário"):
                q.prompt = "O céu é [ ] (azul/verde)."
                st.rerun()

    # Área de Texto
    placeholders = {
        "cloze": "Ex: O gato [ ] (beber) leite ontem.",
        "multichoice_single": "Ex: Define ",
        "truefalse": "Ex: Classifique as afirmações sobre o texto:",
        "matching": "Ex: Associe os países às capitais:",
        "essay": "Ex: Escreva um texto sobre as suas férias."
    }
    
    q.prompt = st.text_area(
        "Escreva a pergunta aqui:", 
        value=q.prompt, 
        height=150, 
        placeholder=placeholders.get(mt, ""),
        label_visibility="collapsed"
    )

    # --- BLOCO 3: RESPOSTAS (EM BAIXO) ---
    st.markdown("### 2. Definição das Respostas")
    
    # A. CLOZE
    if mt in ["cloze", "cloze_mc"]:
        n_gaps = count_gaps(q.prompt)
        if n_gaps == 0:
            st.warning("⚠️ O texto não tem lacunas. Use o botão **Inserir [ ]** ou escreva parêntesis retos.")
        else:
            while len(q.blanks) < n_gaps:
                q.blanks.append(Blank(new_id("b"), f"L{len(q.blanks)+1}", [""], []))
            q.blanks = q.blanks[:n_gaps]

            is_mc = (mt == "cloze_mc")
            cols = st.columns(2 if is_mc else 3)
            
            for i, b in enumerate(q.blanks):
                with cols[i % len(cols)]:
                    with st.container(border=True):
                        st.markdown(f"**Lacuna {i+1}**")
                        b.answers[0] = st.text_input("Correta", value=b.answers[0] if b.answers else "", key=f"ans_{b.bid}")
                        if is_mc:
                            dist_str = "; ".join(b.distractors)
                            dists = st.text_input("Erradas (sep. por ';')", value=dist_str, key=f"dist_{b.bid}", placeholder="Ex: op1; op2")
                            b.distractors = [d.strip() for d in dists.split(";") if d.strip()]

    # B. ESCOLHA MÚLTIPLA (Lógica Corrigida)
    elif mt.startswith("multichoice"):
        for i, opt in enumerate(q.options):
            c1, c2, c3 = st.columns([0.5, 4, 1])
            
            # Botão Apagar
            if c1.button("🗑️", key=f"d_mc_{opt.oid}"):
                q.options.pop(i)
                st.rerun()
            
            # Texto da Opção
            opt.text = c2.text_input(f"Opção {i+1}", value=opt.text, label_visibility="collapsed", key=f"t_mc_{opt.oid}")
            
            # Checkbox de Correção
            # Nota: Usamos o session_state diretamente para forçar a atualização visual se necessário
            chk_key = f"c_mc_{opt.oid}"
            is_chk = c3.checkbox("Correta", value=opt.is_correct, key=chk_key)
            
            if mt == "multichoice_single":
                # Lógica Exclusiva (Só uma pode ser verdadeira)
                if is_chk and not opt.is_correct:
                    # O utilizador acabou de marcar esta caixa.
                    # 1. Marca esta como verdadeira
                    opt.is_correct = True
                    # 2. Desmarca TODAS as outras (no Modelo e na Visualização)
                    for o in q.options:
                        if o.oid != opt.oid:
                            o.is_correct = False
                            # Forçar o visual a desmarcar
                            if f"c_mc_{o.oid}" in st.session_state:
                                st.session_state[f"c_mc_{o.oid}"] = False
                    st.rerun()
                elif not is_chk and opt.is_correct:
                    # O utilizador desmarcou a opção ativa
                    opt.is_correct = False
            else:
                # Lógica Simples (Várias podem ser verdadeiras)
                opt.is_correct = is_chk
        
        if st.button("➕ Adicionar Opção"):
            q.options.append(ChoiceOption(new_id("o"), ""))
            st.rerun()

    # C. VERDADEIRO / FALSO
    elif mt == "truefalse":
        q.tf_require_correction = st.toggle("Pedir correção das Falsas?", value=q.tf_require_correction)
        for i, opt in enumerate(q.options):
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.5, 4, 2])
                if c1.button("🗑️", key=f"d_vf_{opt.oid}"):
                    q.options.pop(i)
                    st.rerun()
                opt.text = c2.text_input("Frase", value=opt.text, label_visibility="collapsed", key=f"t_vf_{opt.oid}")
                sel = c3.radio("Gabarito", ["V", "F"], index=0 if opt.is_correct else 1, horizontal=True, label_visibility="collapsed", key=f"r_vf_{opt.oid}")
                opt.is_correct = (sel == "V")
        if st.button("➕ Adicionar Frase"):
            q.options.append(ChoiceOption(new_id("o"), "", True))
            st.rerun()

    # D. MATCHING
    elif mt == "matching":
        for i, p in enumerate(q.pairs):
            c1, c2, c3 = st.columns([0.5, 2.5, 2.5])
            if c1.button("🗑️", key=f"d_mat_{p.pid}"):
                q.pairs.pop(i)
                st.rerun()
            p.left = c2.text_input("A", value=p.left, label_visibility="collapsed", key=f"pl_{p.pid}", placeholder="Pergunta")
            p.right = c3.text_input("B", value=p.right, label_visibility="collapsed", key=f"pr_{p.pid}", placeholder="Resposta")
        if st.button("➕ Adicionar Par"):
            q.pairs.append(MatchPair(new_id("p"), "", ""))
            st.rerun()

    elif mt == "shortanswer":
        st.info("Insira as respostas aceites (ex: 'Lisboa', 'lisboa').")
        current = "; ".join(q.accepted_answers)
        new_val = st.text_area("Respostas (separar por ;)", value=current)
        q.accepted_answers = [x.strip() for x in new_val.split(";") if x.strip()]

    # --- BLOCO 4: PRÉ-VISUALIZAÇÃO (CLEAN) ---
    st.divider()
    st.subheader("Pré-visualização")
    
    # Container com borda para simular "papel" branco
    with st.container(border=True):
        tab1, tab2 = st.tabs(["Vista do Aluno", "Vista do Professor"])
        
        with tab1:
            if mt == "cloze":
                preview_text = q.prompt.replace("[ ]", " `[ ________ ]` ")
                st.markdown(preview_text)
            elif mt == "cloze_mc":
                preview_text = q.prompt.replace("[ ]", " `[ Selecionar... 🔽 ]` ")
                st.markdown(preview_text)
            elif "multichoice" in mt:
                st.markdown(q.prompt)
                for o in q.options:
                    st.markdown(f"- ⚪ {o.text}")
            elif mt == "truefalse":
                st.markdown(q.prompt)
                st.write("---")
                for o in q.options:
                    st.markdown(f"- {o.text} **(V / F)**")
            elif mt == "matching":
                st.markdown(q.prompt)
                st.write("---")
                c_a, c_b = st.columns(2)
                with c_a: 
                    for p in q.pairs: st.markdown(f"- {p.left}")
                with c_b:
                    st.markdown("*(Menu de opções)*")
            else:
                st.markdown(q.prompt)

        with tab2:
            if mt in ["cloze", "cloze_mc"]:
                st.markdown("**Soluções:**")
                for i, b in enumerate(q.blanks):
                    st.markdown(f"{i+1}. **{b.answers[0] if b.answers else '?'}**")
            elif "multichoice" in mt:
                for o in q.options:
                    mark = "✅" if o.is_correct else "❌"
                    st.markdown(f"{mark} {o.text}")
            elif mt == "truefalse":
                for o in q.options:
                    ans = "VERDADEIRO" if o.is_correct else "FALSO"
                    st.markdown(f"- {o.text} -> **{ans}**")
            elif mt == "matching":
                for p in q.pairs:
                    st.markdown(f"- {p.left} 🔗 **{p.right}**")

    # --- AÇÕES FINAIS ---
    st.divider()
    col_save, col_next = st.columns(2)
    
    # 1. Guardar e Sair
    if col_save.button("💾 Guardar e Sair", type="primary", use_container_width=True):
        # LÓGICA INTEGRADA (SEM FUNÇÃO EXTERNA)
        if st.session_state.active_qid:
            for i, existing_q in enumerate(st.session_state.ta.questions):
                if existing_q.qid == st.session_state.active_qid:
                    st.session_state.ta.questions[i] = copy.deepcopy(q)
                    break
        else:
            st.session_state.ta.questions.append(copy.deepcopy(q))
            
        del st.session_state.draft_q
        st.session_state.active_view = "Editor de Ficha"
        st.session_state.active_qid = None
        st.rerun()

    # 2. Guardar e Criar Seguinte
    if col_next.button("⏩ Guardar e Criar Seguinte", help="Guarda e abre nova do mesmo tipo", use_container_width=True):
        # LÓGICA INTEGRADA (SEM FUNÇÃO EXTERNA)
        if st.session_state.active_qid:
            for i, existing_q in enumerate(st.session_state.ta.questions):
                if existing_q.qid == st.session_state.active_qid:
                    st.session_state.ta.questions[i] = copy.deepcopy(q)
                    break
        else:
            st.session_state.ta.questions.append(copy.deepcopy(q))

        # PREPARAR A PRÓXIMA
        next_q = Question(
            qid=new_id("q"), ui_type=q.ui_type, moodle_type=q.moodle_type,
            prompt="", section=q.section, meta=copy.deepcopy(q.meta)
        )
        if "multichoice" in q.moodle_type:
            next_q.options = [ChoiceOption(new_id("o"), ""), ChoiceOption(new_id("o"), "")]
        elif q.moodle_type == "truefalse":
            next_q.options = [ChoiceOption(new_id("o"), "Verdadeiro", True), ChoiceOption(new_id("o"), "Falso", False)]
        elif q.moodle_type == "matching":
            next_q.pairs = [MatchPair(new_id("p"), "", "")]
            
        st.session_state.draft_q = next_q
        st.session_state.active_qid = None 
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