# app.py
# BabeliUM — Criador de Fichas de Exercícios (Streamlit)
# Interface + validação + export MoodleXML (ainda stub em partes, sobretudo Cloze)

from __future__ import annotations
import copy
import uuid
import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

import streamlit as st

# -----------------------------
# Branding / Tema (leve)
# -----------------------------
BABELIUM_NAME = "BabeliUM — Criador de Fichas de Exercícios"
BRAND_PRIMARY = "#1E5AA8"   # azul (placeholder)
BRAND_ACCENT = "#F2B705"    # amarelo (placeholder)
BRAND_DANGER = "#D7263D"
BRAND_OK = "#2E7D32"
BRAND_WARN = "#ED6C02"

# -----------------------------
# Tipos UI (≈12) -> Moodle (núcleo)
# -----------------------------
UI_TYPES = {
    "Texto com lacunas (Cloze)": "cloze",
    "Completar frase com verbo (template Cloze)": "cloze",
    "Escolha múltipla (1 correta)": "multichoice_single",
    "Escolha múltipla (várias corretas)": "multichoice_multi",
    "Verdadeiro/Falso": "truefalse",
    "Associação (Matching A↔B)": "matching",
    "Resposta curta": "shortanswer",
    "Corrigir erros (subitens)": "shortanswer",
    "Ordenar (palavras/frases)": "essay",  # se quiseres correção rígida, troca para shortanswer depois
    "Transformar frase": "shortanswer",
    "Resposta aberta curta": "essay",
    "Produção escrita": "essay",
}



# -----------------------------
# Modelos de dados
# -----------------------------
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

@dataclass
class ValidationIssue:
    level: str  # "ERRO" | "AVISO"
    where: str
    message: str
    qid: Optional[str] = None
    field_key: Optional[str] = None

@dataclass
class Blank:
    bid: str
    label: str  # L1, L2...
    answers: List[str] = field(default_factory=list)
    case_sensitive: bool = False
    feedback: str = ""

@dataclass
class ChoiceOption:
    oid: str
    text: str
    is_correct: bool = False
    feedback: str = ""

@dataclass
class MatchPair:
    pid: str
    left: str
    right: str

@dataclass
class QuestionMeta:
    category: str = ""
    difficulty: str = "A2"
    points: float = 1.0
    feedback_general: str = ""

@dataclass
class Question:
    qid: str
    ui_type: str
    moodle_type: str
    title: str = ""
    section: str = "Sem secção"
    prompt: str = ""
    meta: QuestionMeta = field(default_factory=QuestionMeta)
    truefalse_answer: Optional[bool] = None
    tf_require_correction: bool = False

    # Cloze
    blanks: List[Blank] = field(default_factory=list)

    # Multichoice
    options: List[ChoiceOption] = field(default_factory=list)
    shuffle_options: bool = True

    # True/False
    truefalse_answer: Optional[bool] = None

    # Matching
    pairs: List[MatchPair] = field(default_factory=list)
    distractors_right: List[str] = field(default_factory=list)
    shuffle_pairs: bool = True

    # Shortanswer
    accepted_answers: List[str] = field(default_factory=list)
    sa_case_sensitive: bool = False

    # Essay
    rubric: str = ""
    word_limit: Optional[int] = None

@dataclass
class TA:
    ta_id: str
    course: str = "PLE A2"
    theme: str = "Tema 1"
    ta_name: str = "Ficha 1"  # UI chama-lhe Ficha
    created_at: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    status: str = "RASCUNHO"  # RASCUNHO | VALIDADO | EXPORTADO | COM ERROS
    questions: List[Question] = field(default_factory=list)
    last_validation: List[ValidationIssue] = field(default_factory=list)

# -----------------------------
# Estado (session)
# -----------------------------
def init_state():
    if "tas" not in st.session_state:
        ficha = TA(ta_id=new_id("ta"), theme="Tema 1", ta_name="Ficha 1")
        st.session_state.tas = {ficha.ta_id: ficha}

    if "active_ta_id" not in st.session_state:
        st.session_state.active_ta_id = list(st.session_state.tas.keys())[0]

    if "active_view" not in st.session_state:
        st.session_state.active_view = "Dashboard"  # Dashboard | Editor de Ficha | Editor de Questão

    if "active_qid" not in st.session_state:
        st.session_state.active_qid = None

    if "toast" not in st.session_state:
        st.session_state.toast = None

init_state()

# -----------------------------
# Helpers
# -----------------------------
def count_gaps(text: str) -> int:
    # Agora aceita [ ] que é muito mais rápido de escrever
    return text.count("[ ]")

def sync_cloze_blanks(q: Question):
    # Ajusta q.blanks ao número de lacunas no enunciado
    n = count_gaps(q.prompt)
    if n <= 0:
        q.blanks = []
        return

    # manter respostas já inseridas, cortar ou adicionar
    current = q.blanks[:]
    if len(current) > n:
        q.blanks = current[:n]
    else:
        while len(current) < n:
            current.append(Blank(bid=new_id("b"), label=f"L{len(current)+1}", answers=[""]))
        q.blanks = current

def get_active_ta() -> TA:
    return st.session_state.tas[st.session_state.active_ta_id]

def set_toast(msg: str):
    st.session_state.toast = msg

def show_toast_if_any():
    if st.session_state.toast:
        st.info(st.session_state.toast)
        st.session_state.toast = None

def find_question(ta: TA, qid: str) -> Optional[Question]:
    for q in ta.questions:
        if q.qid == qid:
            return q
    return None

def move_question(ta: TA, qid: str, direction: int):
    idx = next((i for i, q in enumerate(ta.questions) if q.qid == qid), None)
    if idx is None:
        return
    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(ta.questions):
        return
    ta.questions[idx], ta.questions[new_idx] = ta.questions[new_idx], ta.questions[idx]

def duplicate_question(ta: TA, qid: str):
    q = find_question(ta, qid)
    if not q:
        return
    
    # 1. Cria uma cópia exata do objeto, preservando as classes (QuestionMeta, etc.)
    new_q = copy.deepcopy(q)
    
    # 2. Gera um novo ID único para a questão
    new_q.qid = new_id("q")
    
    # 3. Precisamos de novos IDs para os elementos internos para evitar conflitos na UI
    if new_q.moodle_type == "cloze":
        for b in new_q.blanks:
            b.bid = new_id("b")
            
    elif new_q.moodle_type.startswith("multichoice"):
        for o in new_q.options:
            o.oid = new_id("o")
            
    elif new_q.moodle_type == "matching":
        for p in new_q.pairs:
            p.pid = new_id("p")

    # 4. Adiciona à lista
    ta.questions.append(new_q)

def reset_fields_for_moodle_type(q: Question, moodle_type: str):
    q.moodle_type = moodle_type

    q.blanks = []
    q.options = []
    q.truefalse_answer = None
    q.pairs = []
    q.distractors_right = []
    q.accepted_answers = []
    q.rubric = ""
    q.word_limit = None

    if moodle_type == "cloze":
        q.blanks = [Blank(bid=new_id("b"), label="L1", answers=[""], case_sensitive=False)]
    elif moodle_type.startswith("multichoice"):
        q.options = [
            ChoiceOption(oid=new_id("o"), text="", is_correct=True),
            ChoiceOption(oid=new_id("o"), text="", is_correct=False),
        ]
        q.shuffle_options = True
    elif moodle_type == "truefalse":
        q.options = [
            ChoiceOption(oid=new_id("o"), text="", is_correct=True),
            ChoiceOption(oid=new_id("o"), text="", is_correct=False),
        ]
        q.shuffle_options = False
        q.tf_require_correction = False # <--- RESET
        

        q.shuffle_options = False # Geralmente não baralhamos a ordem das frases V/F, mas pode ativar
    elif moodle_type == "matching":
        q.pairs = [
            MatchPair(pid=new_id("p"), left="", right=""),
            MatchPair(pid=new_id("p"), left="", right=""),
        ]
        q.shuffle_pairs = True
    elif moodle_type == "shortanswer":
        q.accepted_answers = [""]
        q.sa_case_sensitive = False
    elif moodle_type == "essay":
        q.rubric = ""
        q.word_limit = None

def migrate_when_possible(old: Question, new_moodle_type: str) -> Question:
    q = old

    if q.moodle_type == "truefalse" and new_moodle_type.startswith("multichoice"):
        tf = q.truefalse_answer
        reset_fields_for_moodle_type(q, new_moodle_type)
        q.options[0].text = "Verdadeiro"
        q.options[1].text = "Falso"
        if tf is True:
            q.options[0].is_correct = True
            q.options[1].is_correct = False
        else:
            q.options[0].is_correct = False
            q.options[1].is_correct = True
        return q

    if q.moodle_type == "shortanswer" and new_moodle_type == "cloze":
        answers = [a for a in q.accepted_answers if a.strip()]
        reset_fields_for_moodle_type(q, "cloze")
        if answers:
            q.blanks[0].answers = answers
        return q

    if q.moodle_type == "cloze" and new_moodle_type == "shortanswer":
        if len(q.blanks) == 1:
            answers = [a for a in q.blanks[0].answers if a.strip()]
            reset_fields_for_moodle_type(q, "shortanswer")
            if answers:
                q.accepted_answers = answers
            return q

    reset_fields_for_moodle_type(q, new_moodle_type)
    return q

# -----------------------------
# Validação
# -----------------------------
def validate_ficha(ta: TA) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    # Ficha sem questões = ERRO (bloqueia export)
    if len(ta.questions) == 0:
        issues.append(
            ValidationIssue(
                "ERRO",
                "Ficha",
                "A ficha não tem questões. Adiciona pelo menos uma questão."
            )
        )
        return issues

    if not ta.ta_name.strip():
        issues.append(ValidationIssue("ERRO", "Ficha", "Nome da ficha em falta."))

    for i, q in enumerate(ta.questions, start=1):
        base_where = f"Ficha > Questão {i}"

        if not q.prompt.strip():
            issues.append(ValidationIssue("ERRO", base_where, "Enunciado em falta.", qid=q.qid, field_key="prompt"))

        if q.meta.points is None or q.meta.points <= 0:
            issues.append(ValidationIssue("ERRO", base_where, "Pontuação inválida (tem de ser > 0).", qid=q.qid, field_key="points"))

        mt = q.moodle_type

        if mt == "cloze":
            if len(q.blanks) < 1:
                issues.append(ValidationIssue("ERRO", base_where, "Cloze sem lacunas.", qid=q.qid))
            for b_idx, b in enumerate(q.blanks, start=1):
                ans = [a.strip() for a in b.answers if a.strip()]
                if not ans:
                    issues.append(ValidationIssue("ERRO", f"{base_where} > Lacuna {b_idx}", "Lacuna sem resposta correta.", qid=q.qid))

        elif mt.startswith("multichoice"):
            opts = [o for o in q.options if o.text.strip()]
            if len(opts) < 2:
                issues.append(ValidationIssue("ERRO", base_where, "Escolha múltipla requer pelo menos 2 opções com texto.", qid=q.qid))
            correct = [o for o in q.options if o.is_correct and o.text.strip()]
            if mt == "multichoice_single":
                if len(correct) != 1:
                    issues.append(ValidationIssue("ERRO", base_where, "Tem de existir exatamente 1 opção correta.", qid=q.qid))
            else:
                if len(correct) < 1:
                    issues.append(ValidationIssue("ERRO", base_where, "Tem de existir pelo menos 1 opção correta.", qid=q.qid))

        elif mt == "truefalse":
            if not q.options:
                issues.append(ValidationIssue("ERRO", base_where, "Adicione pelo menos uma afirmação.", qid=q.qid))
            else:
                for idx, opt in enumerate(q.options):
                    if not opt.text.strip():
                        issues.append(ValidationIssue("ERRO", base_where, f"Afirmação {idx+1} sem texto.", qid=q.qid))

        elif mt == "matching":
            complete_pairs = [p for p in q.pairs if p.left.strip() and p.right.strip()]
            if len(complete_pairs) < 2:
                issues.append(ValidationIssue("ERRO", base_where, "Matching requer pelo menos 2 pares completos.", qid=q.qid))
            rights = [p.right.strip() for p in complete_pairs]
            if len(set(rights)) != len(rights):
                issues.append(ValidationIssue("AVISO", base_where, "Há respostas (coluna B) repetidas. Confirma se é intencional.", qid=q.qid))

        elif mt == "shortanswer":
            ans = [a.strip() for a in q.accepted_answers if a.strip()]
            if not ans:
                issues.append(ValidationIssue("ERRO", base_where, "Resposta curta sem respostas aceites.", qid=q.qid))

        elif mt == "essay":
            if not q.rubric.strip():
                issues.append(ValidationIssue("AVISO", base_where, "Sem rubrica/critério. (Recomendado)", qid=q.qid))

    return issues


def update_ficha_status(ta: TA, issues: List[ValidationIssue]):
    ta.last_validation = issues
    has_errors = any(i.level == "ERRO" for i in issues)
    if has_errors:
        ta.status = "COM ERROS"
    else:
        ta.status = "VALIDADO" if ta.questions else "RASCUNHO"

# -----------------------------
# Export (stub)
# -----------------------------
def escape_xml(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

def build_moodle_xml_stub(ta: TA) -> str:
    default_cat = f"{ta.course}/{ta.theme}/{ta.ta_name}"
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<quiz>")

    for q in ta.questions:
        cat = q.meta.category.strip() or default_cat

        lines.append('  <question type="category">')
        lines.append("    <category>")
        lines.append(f"      <text>{escape_xml('$course$/' + cat)}</text>")
        lines.append("    </category>")
        lines.append("  </question>")
        lines.append("  </question>") # Esta linha já existe no seu código

        lines.append("  </question>") # (Esta linha já existe, é o fecho da pergunta anterior)

        # --- CÓDIGO NOVO: INJEÇÃO DA PERGUNTA DE CORREÇÃO ---
        if mt == "truefalse" and q.tf_require_correction:
            # Criamos uma pergunta EXTRA automática do tipo ESSAY
            lines.append('  <question type="essay">')
            
            # Título da pergunta
            name_corr = f"{q.title} (Correção)" if q.title else f"{ta.ta_name} - Correção V/F"
            lines.append("    <name>")
            lines.append(f"      <text>{escape_xml(name_corr)}</text>")
            lines.append("    </name>")
            
            # Enunciado da correção
            lines.append('    <questiontext format="html">')
            lines.append("      <text><![CDATA[<p><b>Justificação / Correção:</b></p><p>Reescreva corretamente as afirmações que classificou como Falsas na pergunta anterior.</p>]]></text>")
            lines.append("    </questiontext>")
            
            lines.append("    <defaultgrade>1.0</defaultgrade>") 
            lines.append("    <responseformat>editor</responseformat>")
            
            # --- A LINHA QUE DAVA ERRO (CORRIGIDA COM ASPAS SIMPLES) ---
            lines.append('    <responsetemplate format="html"><text></text></responsetemplate>')
            
            lines.append("  </question>")
        # ----------------------------------------------------
        # --- CÓDIGO NOVO (PONTO 4) ---
        
        # 1. Determinar o tipo REAL para o Moodle
        mt = q.moodle_type
        moodle_xml_type = mt # Default

        # Lógica especial para V/F Múltiplo -> Vira Matching
        if mt == "truefalse" and len(q.options) > 1:
            moodle_xml_type = "matching"
        
        # Mapeamento dos restantes tipos
        elif mt == "multichoice_single" or mt == "multichoice_multi":
            moodle_xml_type = "multichoice"
        elif mt == "cloze":
            moodle_xml_type = "cloze"
        elif mt == "matching":
            moodle_xml_type = "matching"
        elif mt == "shortanswer":
            moodle_xml_type = "shortanswer"
        elif mt == "essay":
            moodle_xml_type = "essay"
        elif mt == "truefalse":
            moodle_xml_type = "truefalse" # Caso seja só 1 pergunta V/F simples

        # 2. Escrever a tag correta no XML
        lines.append(f'  <question type="{moodle_xml_type}">')
        qname = q.title.strip() or f"{ta.ta_name} - {q.ui_type}"
        lines.append("    <name>")
        lines.append(f"      <text>{escape_xml(qname)}</text>")
        lines.append("    </name>")

        lines.append('    <questiontext format="html">')
        lines.append(f"      <text><![CDATA[{q.prompt}]]></text>")
        lines.append("    </questiontext>")

        lines.append(f"    <defaultgrade>{q.meta.points}</defaultgrade>")

        if q.meta.feedback_general.strip():
            lines.append('    <generalfeedback format="html">')
            lines.append(f"      <text><![CDATA[{q.meta.feedback_general}]]></text>")
            lines.append("    </generalfeedback>")

        if mt.startswith("multichoice"):
            single = (mt == "multichoice_single")
            lines.append(f"    <single>{'true' if single else 'false'}</single>")
            lines.append(f"    <shuffleanswers>{'true' if q.shuffle_options else 'false'}</shuffleanswers>")

            correct_opts = [o for o in q.options if o.is_correct and o.text.strip()]
            frac_correct = 100 if single else (100 / max(1, len(correct_opts)))

            for o in q.options:
                if not o.text.strip():
                    continue
                fraction = frac_correct if o.is_correct else 0
                lines.append(f'    <answer fraction="{fraction}" format="html">')
                lines.append(f"      <text><![CDATA[{o.text}]]></text>")
                if o.feedback.strip():
                    lines.append('      <feedback format="html">')
                    lines.append(f"        <text><![CDATA[{o.feedback}]]></text>")
                    lines.append("      </feedback>")
                lines.append("    </answer>")

        elif mt == "truefalse":
            # LÓGICA HÍBRIDA:
            # Se só tiver 1 opção -> Exporta como True/False nativo do Moodle
            # Se tiver > 1 opções -> Exporta como Matching (Associação) simulando V/F
            
            if len(q.options) == 1:
                # --- MODO SIMPLES (1 pergunta) ---
                opt = q.options[0]
                # O prompt deve incluir a afirmação se for única
                final_text = f"{q.prompt}<br/><br/><b>{opt.text}</b>"
                
                # Reescrevemos o questiontext para incluir a frase
                # Nota: Removemos as linhas anteriores de questiontext para não duplicar, 
                # ou assumimos que o utilizador põe o enunciado genérico no prompt.
                # Vamos simplificar: exportamos como 'truefalse' mas ajustamos o texto.
                
                # Removemos a tag <question type="truefalse"> que já foi aberta lá cima?
                # Não, o código original já abriu a tag baseada no qtype map. 
                # Mas espera, se formos mudar para matching, o qtype lá em cima estaria errado.
                
                # CORREÇÃO: O ideal é ajustar o qtype map ou fechar e abrir tags.
                # Como o script segue linearmente, vamos assumir que o qtype="truefalse" já foi escrito.
                # Se tivermos múltiplas, isto vai dar erro no Moodle se usarmos type="truefalse".
                pass 
                # (Nota: Para corrigir isto perfeitamente, o mapeamento de tipos lá em cima
                # tem de saber se é single ou multi. Vamos alterar o mapeamento no início do loop)

                tf = "true" if opt.is_correct else "false"
                lines.append(f'    <answer fraction="100"><text>{tf}</text></answer>')
                lines.append(f'    <answer fraction="0"><text>{"false" if tf=="true" else "true"}</text></answer>')
            
            else:
                # --- MODO MÚLTIPLO (Hack: Fechamos a tag truefalse e abrimos matching) ---
                # Isto é um pouco "sujo" mas evita reescrever a função toda.
                # Removemos a última linha que diz <question type="truefalse"> se possível? 
                # Não, já foi adicionada à lista lines.
                
                # SOLUÇÃO LIMPA: Altere o 'moodle_type_map' no início do loop para:
                # "truefalse": "matching" if len(q.options) > 1 else "truefalse"
                pass 

                # Vamos assumir que fez a alteração sugerida abaixo no início do loop.
                
                lines.append(f"    <shuffleanswers>{'true' if q.shuffle_options else 'false'}</shuffleanswers>")
                
                used_answers = set()
                for opt in q.options:
                    if not opt.text.strip(): continue
                    ans_text = "Verdadeiro" if opt.is_correct else "Falso"
                    used_answers.add(ans_text)
                    
                    lines.append('    <subquestion format="html">')
                    lines.append(f'      <text><![CDATA[{opt.text}]]></text>')
                    lines.append('      <answer>')
                    lines.append(f'        <text>{ans_text}</text>')
                    lines.append('      </answer>')
                    lines.append('    </subquestion>')
                
                # GARANTIA: O Moodle Matching cria uma dropdown com as respostas usadas.
                # Se todas forem "Verdadeiro", o aluno só vê "Verdadeiro" na lista.
                # Temos de adicionar o "Falso" como distrator (resposta sem pergunta) se não for usado.
                
                if "Verdadeiro" not in used_answers:
                    lines.append('    <subquestion format="html"><text></text><answer><text>Verdadeiro</text></answer></subquestion>')
                if "Falso" not in used_answers:
                    lines.append('    <subquestion format="html"><text></text><answer><text>Falso</text></answer></subquestion>')

        elif mt == "matching":
            lines.append(f"    <shuffleanswers>{'true' if q.shuffle_pairs else 'false'}</shuffleanswers>")
            for p in q.pairs:
                if not (p.left.strip() and p.right.strip()):
                    continue
                lines.append('    <subquestion format="html">')
                lines.append(f"      <text><![CDATA[{p.left}]]></text>")
                lines.append("      <answer>")
                lines.append(f"        <text><![CDATA[{p.right}]]></text>")
                lines.append("      </answer>")
                lines.append("    </subquestion>")
            if q.distractors_right:
                lines.append("    <!-- Distratores (UI): " + escape_xml(", ".join(q.distractors_right)) + " -->")

        elif mt == "shortanswer":
            lines.append(f"    <usecase>{'1' if q.sa_case_sensitive else '0'}</usecase>")
            ans = [a.strip() for a in q.accepted_answers if a.strip()]
            if ans:
                frac = 100 / len(ans)
                for a in ans:
                    lines.append(f'    <answer fraction="{frac}" format="moodle_auto_format">')
                    lines.append(f"      <text>{escape_xml(a)}</text>")
                    lines.append("    </answer>")

        elif mt == "essay":
            lines.append('    <responseformat>editor</responseformat>')
            if q.rubric.strip():
                lines.append('    <responsetemplate format="html">')
                lines.append(f"      <text><![CDATA[{q.rubric}]]></text>")
                lines.append("    </responsetemplate>")
            if q.word_limit:
                lines.append(f"    <!-- Limite de palavras (UI): {q.word_limit} -->")

        elif mt == "cloze":
            lines.append("    <!-- Cloze placeholders (UI) -->")
            for b in q.blanks:
                ans = [a.strip() for a in b.answers if a.strip()]
                lines.append(f"    <!-- {b.label}: answers={escape_xml('|'.join(ans))} case={b.case_sensitive} -->")

        lines.append("  </question>")

    lines.append("</quiz>")
    return "\n".join(lines)

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="BabeliUM — Fichas", layout="wide")

st.markdown(
    f"""
    <style>
      .babelium-header {{
        padding: 12px 16px; border-radius: 16px;
        background: linear-gradient(90deg, {BRAND_PRIMARY}, #0f2b55);
        color: white; font-weight: 800; margin-bottom: 12px;
        display:flex; align-items:center; justify-content:space-between;
      }}
      .babelium-tag {{
        background: rgba(255,255,255,0.15);
        padding: 4px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 700;
      }}
      .status-pill {{
        display:inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 800; margin-left: 8px;
      }}
      .pill-draft {{ background: #e3f2fd; color: #0d47a1; }}
      .pill-valid {{ background: #e8f5e9; color: #1b5e20; }}
      .pill-exp {{ background: #ede7f6; color: #4527a0; }}
      .pill-err {{ background: #ffebee; color: #b71c1c; }}
      .small-muted {{ color: #8a8a8a; font-size: 12px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='babelium-header'><div>{BABELIUM_NAME}</div><div class='babelium-tag'>Preview • Streamlit</div></div>",
    unsafe_allow_html=True
)

with st.sidebar:
    st.subheader("Navegação")

    # ✅ Não deixes o radio sobrescrever quando estás no Editor de Questão
    if st.session_state.active_view == "Editor de Questão":
        st.info("A editar uma questão.")
        if st.button("⬅️ Voltar ao Editor de Ficha", use_container_width=True):
            st.session_state.active_view = "Editor de Ficha"
            st.session_state.active_qid = None
            st.rerun()
    else:
        view = st.radio(
            "Onde estás?",
            ["Dashboard", "Editor de Ficha"],
            index=0 if st.session_state.active_view == "Dashboard" else 1,
        )
        st.session_state.active_view = view


    fichas = list(st.session_state.tas.values())
    ficha_labels = []
    for f in fichas:
        ficha_labels.append(f"{f.ta_name} • {f.course} • {f.theme} • {f.status}")

    selected_idx = 0
    for i, f in enumerate(fichas):
        if f.ta_id == st.session_state.active_ta_id:
            selected_idx = i
            break

    choice = st.selectbox(
        "Seleciona uma ficha",
        options=list(range(len(fichas))),
        format_func=lambda i: ficha_labels[i],
        index=selected_idx
    )
    st.session_state.active_ta_id = fichas[choice].ta_id

    col_new, col_del = st.columns(2)
    with col_new:
        if st.button("➕ Nova ficha", use_container_width=True):
            f = TA(ta_id=new_id("ta"), theme="Tema 1", ta_name=f"Ficha {len(st.session_state.tas)+1}")
            st.session_state.tas[f.ta_id] = f
            st.session_state.active_ta_id = f.ta_id
            st.session_state.active_view = "Editor de Ficha"
            st.rerun()
    with col_del:
        if st.button("🗑️ Apagar ficha", use_container_width=True):
            if len(st.session_state.tas) > 1:
                del st.session_state.tas[st.session_state.active_ta_id]
                st.session_state.active_ta_id = list(st.session_state.tas.keys())[0]
                st.session_state.active_qid = None
                st.session_state.active_view = "Dashboard"
                st.rerun()
            else:
                set_toast("Não podes apagar a única ficha existente.")
                st.rerun()

    st.divider()
    st.caption("Export MoodleXML só quando a ficha estiver VALIDADA (sem ERROS).")

# -----------------------------
# Main (Execução Principal)
# -----------------------------
ta = get_active_ta()
show_toast_if_any()

# --- ATACAR O ERRO PELA RAIZ: Inicialização de q ---
q = None # q começa sempre como "nada" para não dar erro de definição

# Se estivermos no editor, tentamos encontrar a questão imediatamente
if st.session_state.active_view == "Editor de Questão":
    if st.session_state.active_qid is None:
        # É uma questão nova, usamos o rascunho
        if "draft_q" not in st.session_state:
            first_ui = list(UI_TYPES.keys())[0]
            st.session_state.draft_q = Question(qid=new_id("q"), ui_type=first_ui, moodle_type=UI_TYPES[first_ui])
        q = st.session_state.draft_q
    else:
        # É uma questão existente
        q = find_question(ta, st.session_state.active_qid)
    
    # Se q continuar a ser None (ex: questão apagada), voltamos para a ficha
    if q is None:
        st.session_state.active_view = "Editor de Ficha"
        st.rerun()
# --------------------------------------------------

# -----------------------------
# Dashboard
# -----------------------------
if st.session_state.active_view == "Dashboard":
    colA, colB, colC = st.columns([2, 2, 2])
    with colA:
        ta.course = st.text_input("Curso", value=ta.course, key=f"course_{ta.ta_id}")
    with colB:
        ta.theme = st.text_input("Tema/Unidade", value=ta.theme, key=f"theme_{ta.ta_id}")
    with colC:
        ta.ta_name = st.text_input("Nome da ficha", value=ta.ta_name, key=f"fichaname_{ta.ta_id}")

    st.divider()

    left, right = st.columns([1, 2])
    with left:
        if st.button("✅ Validar ficha", use_container_width=True):
            issues = validate_ficha(ta)
            update_ficha_status(ta, issues)
            if ta.status == "COM ERROS":
                set_toast("Há erros. Corrige-os antes de exportar.")
            else:
                set_toast("Validação concluída. Ficha pronta para export.")
            st.rerun()

        can_export = (ta.status == "VALIDADO")
        if st.button("📦 Export MoodleXML", use_container_width=True, disabled=not can_export):
            xml = build_moodle_xml_stub(ta)
            ta.status = "EXPORTADO"
            filename = f"{ta.course}_{ta.theme}_{ta.ta_name}.xml".replace(" ", "_")
            st.download_button(
                "⬇️ Descarregar MoodleXML",
                data=xml,
                file_name=filename,
                mime="application/xml",
                use_container_width=True
            )
            st.caption("Export feito. (Estado marcado como EXPORTADO)")
    with right:
        st.subheader("Validação")
        if not ta.last_validation:
            st.write("Sem validação ainda. Clica em **Validar ficha**.")
        else:
            errors = [i for i in ta.last_validation if i.level == "ERRO"]
            warns = [i for i in ta.last_validation if i.level == "AVISO"]
            st.write(f"Erros: **{len(errors)}** • Avisos: **{len(warns)}**")

            for iss in ta.last_validation:
                badge = "🟥 ERRO" if iss.level == "ERRO" else "🟧 AVISO"
                cols = st.columns([1, 5, 1])
                cols[0].markdown(f"**{badge}**")
                cols[1].write(f"{iss.where} — {iss.message}")
                if iss.qid:
                    if cols[2].button("Ir", key=f"go_{iss.qid}_{iss.where}"):
                        st.session_state.active_view = "Editor de Ficha"
                        st.session_state.active_qid = iss.qid
                        st.rerun()

    st.divider()
    st.subheader("Resumo")
    st.write(f"- Questões: **{len(ta.questions)}**")
    st.write(f"- Criado em: `{ta.created_at}`")

elif st.session_state.active_view == "Editor de Ficha":
    # 1. CABEÇALHO (Simples e alinhado)
    with st.container():
        c1, c2, c3 = st.columns([3, 2, 2])
        ta.ta_name = c1.text_input("Nome da Ficha", value=ta.ta_name)
        ta.course = c2.text_input("Curso/Nível", value=ta.course)
        with c3:
            st.write(" ") # Espaçador para alinhar com os inputs
            if st.button("➕ Nova Questão", use_container_width=True, type="primary"):
                st.session_state.active_qid = None
                st.session_state.active_view = "Editor de Questão"
                st.rerun()

    st.divider()

    if not ta.questions:
        st.info("Ainda não existem questões nesta ficha.")
    else:
        for idx, q in enumerate(ta.questions):
            # O 'border=True' cria o cartão automaticamente sem precisar de CSS
            with st.container(border=True):
                
                # LINHA 1: Título e Ordem
                cab1, cab2 = st.columns([5, 1])
                cab1.markdown(f"### {idx + 1}. {q.title or 'Questão sem título'}")
                cab1.caption(f"📂 {q.section}  |  💎 {q.meta.points} pontos")
                
                # Ordem da questão
                nova_pos = cab2.number_input("Ordem", min_value=1, max_value=len(ta.questions), value=idx+1, key=f"pos_{q.qid}")
                if nova_pos != idx + 1:
                    temp_q = ta.questions.pop(idx)
                    ta.questions.insert(nova_pos - 1, temp_q)
                    st.rerun()

                # LINHA 2: O PREVIEW (Atacando o fundo branco e o corte de texto)
                # Usamos .strip() para colar à esquerda e pre-wrap para os parágrafos
                texto_aluno = q.prompt.strip().replace('[ ]', '<u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u>')
                
                st.markdown(f"""
                    <div style="
                        background-color: #0e1117; 
                        padding: 15px; 
                        border-radius: 5px; 
                        border: 1px solid #30363d;
                        white-space: pre-wrap;
                        line-height: 1.6;
                    ">{texto_aluno}</div>
                """, unsafe_allow_html=True)

                # LINHA 3: OS BOTÕES (Dando espaço real para o texto)
                st.write("") # Respiro
                # Criamos apenas 3 colunas largas. O "Apagar" terá espaço de sobra.
                b1, b2, b3 = st.columns(3)
                
                if b1.button("Editar Questão", key=f"ed_{q.qid}", use_container_width=True):
                    st.session_state.active_qid = q.qid
                    st.session_state.active_view = "Editor de Questão"
                    st.rerun()
                
                if b2.button("Duplicar", key=f"dp_{q.qid}", use_container_width=True):
                    duplicate_question(ta, q.qid)
                    st.rerun()
                    
                if b3.button("Apagar", key=f"del_{q.qid}", use_container_width=True):
                    ta.questions.pop(idx)
                    st.rerun()

    st.divider()
    st.button("📦 Gerar MoodleXML Final", use_container_width=True)

# -----------------------------
# Editor de Questão (Proteção Total)
# -----------------------------
else:
    # FILTRO DE SEGURANÇA RAIZ
    if q is None:
        st.error("⚠️ Erro de sessão: Questão não carregada.")
        if st.button("⬅️ Voltar para a Ficha"):
            st.session_state.active_view = "Editor de Ficha"
            st.rerun()
        st.stop()  # O código pára aqui se q for None, impedindo o erro técnico

    mt = q.moodle_type
    creating_new = st.session_state.active_qid is None
    st.title(f"✍️ Configurar: {q.ui_type}")

    # --- ORGANIZAÇÃO INICIAL ---
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1]) # Adicionada 4ª coluna
        q.title = c1.text_input("Título da Atividade", value=q.title, placeholder="Ex: Exercício de Verbos")
        
        # --- NOVO: SELETOR DE TIPO ---
        tipo_selecionado = c2.selectbox("Tipo de Questão", options=list(UI_TYPES.keys()), index=list(UI_TYPES.keys()).index(q.ui_type))
        if tipo_selecionado != q.ui_type:
            q.ui_type = tipo_selecionado
            # Atualiza o tipo interno do Moodle e reseta campos específicos
            reset_fields_for_moodle_type(q, UI_TYPES[tipo_selecionado])
            st.rerun()
        
        seccoes = ["Gramática", "Vocabulário", "Leitura", "Escrita"]
        q.section = c3.selectbox("Tipo de Conteúdo", options=sorted(list(set(seccoes + [q.section]))))
        q.meta.points = c4.number_input("Valor (Pontos)", min_value=0.0, value=float(q.meta.points), step=0.5)

    st.divider()

    # --- ENUNCIADO (com ou sem guia, dependendo do tipo) ---
    if mt == "cloze":
        st.markdown("### 1. Elaborar Enunciado")
        
        # Ponto: Explicação e Exemplos para o Professor
        with st.expander("❓ Não sabe como começar? Veja estes exemplos rápidos", expanded=False):
            st.markdown("""
            Para criar os espaços onde o aluno vai responder, basta escrever **[ ]** (parênteses retos com um espaço no meio).
            """)
            
            tab_gram, tab_voc = st.tabs(["📝 Gramática", "📖 Vocabulário"])
            
            with tab_gram:
                st.write("**Como escrever:**")
                st.code("O gato [ ] (beber) leite ontem à noite.")
                st.write("**O que o aluno verá:**")
                st.markdown("O gato <u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u> (beber) leite ontem à noite.", unsafe_allow_html=True)
                
            with tab_voc:
                st.write("**Como escrever:**")
                st.code("A capital de Portugal é [ ].")
                st.write("**O que o aluno verá:**")
                st.markdown("A capital de Portugal é <u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u>.", unsafe_allow_html=True)
            
            st.info("💡 **Dica:** Pode usar o botão 'Inserir Lacuna' abaixo para colocar o símbolo automaticamente onde estiver o cursor.")

        # --- CAMPO DE INPUT E BOTÕES (só para Cloze) ---
        col_input, col_tools = st.columns([4, 1])
        
        with col_tools:
            st.write("") # Alinhamento
            if st.button("➕ Inserir Lacuna", use_container_width=True, help="Adiciona [ ] ao final do seu texto"):
                q.prompt += " [ ] "
                st.rerun()
            
            if st.button("🔄 Atualizar", use_container_width=True, help="Clique aqui após escrever para gerar os campos de resposta"):
                sync_cloze_blanks(q)
                st.toast("Campos de resposta atualizados!")

        with col_input:
            q.prompt = st.text_area(
                "Texto da Pergunta:", 
                value=q.prompt, 
                height=250, 
                placeholder="Ex: O João [ ] (comprar) um carro novo ontem.",
                label_visibility="collapsed"
            )

        # Nota subtil para o professor
        st.caption("⚠️ Lembre-se: Após escrever ou colar o seu texto, clique no botão **'Atualizar'** para definir as respostas corretas.")
    
    else:
        # Para todos os outros tipos (escolha múltipla, V/F, etc.)
        st.markdown("### 1. Elaborar Enunciado")
        q.prompt = st.text_area(
            "Texto da Pergunta:", 
            value=q.prompt, 
            height=150, 
            placeholder="Ex: Qual é a capital de Portugal?",
            label_visibility="collapsed"
        )

    # --- CONFIGURAÇÃO DE RESPOSTAS (CLOZE) ---
    if mt == "cloze":
        st.divider()
        st.markdown("### 2. Definir Respostas Corretas")
        n_lacunas = count_gaps(q.prompt)
        
        if n_lacunas > 0:
            # Sincroniza se o número de lacunas mudou
            if len(q.blanks) != n_lacunas:
                sync_cloze_blanks(q)
            
            # Design em grelha mais leve
            cols = st.columns(3)
            for i, b in enumerate(q.blanks):
                with cols[i % 3]:
                    ans = b.answers[0] if b.answers else ""
                    b.answers = [st.text_input(f"Resposta para o espaço {i+1}", value=ans, key=f"ans_{b.bid}")]
        else:
            st.warning("Ainda não inseriu nenhuma lacuna [ ] no texto acima.")

    # --- CONFIGURAÇÃO DE ESCOLHA MÚLTIPLA ---
    elif mt.startswith("multichoice"):
        st.divider()
        st.markdown("### 2. Configurar Opções de Resposta")
        
        is_single = (mt == "multichoice_single")
        
        # Explicação do tipo
        with st.container(border=True):
            if is_single:
                st.info("ℹ️ **Escolha Múltipla (1 correta):** O aluno só pode selecionar UMA resposta. Selecione qual é a opção correta.")
            else:
                st.info("ℹ️ **Escolha Múltipla (várias corretas):** O aluno pode selecionar VÁRIAS respostas. Marque todas as opções que são corretas.")
        
        st.write("")  # Espaçamento

        # Botão para adicionar nova opção
        col_add, col_shuffle = st.columns([2, 3])
        with col_add:
            if st.button("➕ Adicionar Opção", use_container_width=True, type="secondary"):
                q.options.append(ChoiceOption(oid=new_id("o"), text="", is_correct=False))
                st.rerun()
        with col_shuffle:
            q.shuffle_options = st.toggle("🔀 Baralhar opções automaticamente no Moodle", value=q.shuffle_options)

        st.write("")  # Espaçamento

        # Listagem das opções existentes
        if not q.options:
            st.warning("⚠️ Ainda não criou nenhuma opção. Clique em '➕ Adicionar Opção' para começar.")
        else:
            # Contador de corretas para validação visual
            n_corretas = sum(1 for o in q.options if o.is_correct and o.text.strip())
            
            # Aviso se não houver corretas marcadas
            if n_corretas == 0:
                st.warning("⚠️ Nenhuma opção está marcada como correta!")
            elif is_single and n_corretas > 1:
                st.error("❌ Só pode ter UMA opção correta neste tipo de pergunta!")
            
            st.caption(f"**{len(q.options)} opções criadas** • {n_corretas} marcada(s) como correta(s)")
            
            # ========== MODO 1: UMA SÓ CORRETA (com radio) ==========
            if is_single:
                # Encontrar qual está marcada (se alguma)
                correct_idx = next((i for i, o in enumerate(q.options) if o.is_correct), None)

                # Radio para selecionar qual é a correta
                st.write("**Selecione a opção correta:**")
                selected = st.radio(
                    "Qual é a resposta correta?",
                    options=range(len(q.options)),
                    format_func=lambda i: f"● Opção {i+1}" if q.options[i].text.strip() else f"○ Opção {i+1} (vazia)",
                    index=correct_idx if correct_idx is not None else 0,
                    key="radio_correct",
                    label_visibility="collapsed"
                )

                # Atualizar qual é a correta baseado no radio
                if selected is not None:
                    for i, opt in enumerate(q.options):
                        opt.is_correct = (i == selected)

                st.divider()

                # Mostrar campos de texto para cada opção
                for i, opt in enumerate(q.options):
                    with st.container(border=True):
                        col_txt, col_del = st.columns([6, 0.6])

                        # Indicador visual se é a correta
                        label_visual = "🟢 **OPÇÃO CORRETA**" if opt.is_correct else f"Opção {i+1}"

                        with col_txt:
                            st.markdown(label_visual)
                            opt.text = st.text_input(
                                "Texto",
                                value=opt.text,
                                key=f"txt_{opt.oid}",
                                placeholder=f"Ex: Esta é a opção {chr(65+i)}",
                                label_visibility="collapsed"
                            )

                        with col_del:
                            st.write("")  # Alinhamento
                            if st.button("🗑️", key=f"del_{opt.oid}", help="Apagar esta opção"):
                                q.options.pop(i)
                                st.rerun()

                        # Feedback opcional
                        with st.expander("💬 Adicionar feedback (opcional)", expanded=False):
                            opt.feedback = st.text_area(
                                "Feedback",
                                value=opt.feedback,
                                key=f"feed_{opt.oid}",
                                placeholder="Explicação que aparece quando o aluno escolhe esta opção",
                                height=80,
                                label_visibility="collapsed"
                            )

            # ========== MODO 2: VÁRIAS CORRETAS (com checkboxes) ==========
            else:
                for i, opt in enumerate(q.options):
                    with st.container(border=True):
                        col_check, col_txt, col_del = st.columns([0.4, 6, 0.6])

                        with col_check:
                            st.write("")  # Alinhamento
                            new_val = st.checkbox(
                                "✓",
                                value=opt.is_correct,
                                key=f"check_{opt.oid}",
                                help="Marcar/desmarcar como correta",
                                label_visibility="collapsed"
                            )
                            if new_val != opt.is_correct:
                                opt.is_correct = new_val
                                st.rerun()

                        with col_txt:
                            label_visual = "🟢 Opção CORRETA" if opt.is_correct else f"Opção {i+1}"
                            opt.text = st.text_input(
                                label_visual,
                                value=opt.text,
                                key=f"txt_{opt.oid}",
                                placeholder=f"Ex: Esta é a opção {chr(65+i)}",
                                label_visibility="visible"
                            )

                        with col_del:
                            st.write("")  # Alinhamento
                            if st.button("🗑️", key=f"del_{opt.oid}", help="Apagar esta opção"):
                                q.options.pop(i)
                                st.rerun()

                        with st.expander("💬 Adicionar feedback (opcional)", expanded=False):
                            opt.feedback = st.text_area(
                                "Feedback",
                                value=opt.feedback,
                                key=f"feed_{opt.oid}",
                                placeholder="Explicação que aparece quando o aluno escolhe esta opção",
                                height=80,
                                label_visibility="collapsed"
                            )

    # --- CONFIGURAÇÃO DE VERDADEIRO/FALSO (Múltiplo) ---
    elif mt == "truefalse":
        st.divider()
        st.markdown("### 2. Definir Afirmações e Veracidade")
        
        # Checkbox para a funcionalidade extra
        col_help, col_check = st.columns([2, 1])
        with col_help:
             st.info("ℹ️ **Matriz V/F:** O aluno classifica várias frases. Adicione afirmações abaixo.")
        with col_check:
             # A tal opção extra
             q.tf_require_correction = st.toggle("Pedir correção das falsas?", value=q.tf_require_correction)
             if q.tf_require_correction:
                 st.caption("Será criada uma caixa de texto extra no Moodle.")

        # Botão para adicionar nova afirmação
        if st.button("➕ Adicionar Afirmação", use_container_width=True, type="secondary"):
            q.options.append(ChoiceOption(oid=new_id("o"), text="", is_correct=True))
            st.rerun()

        st.write("") 

        if not q.options:
            st.warning("⚠️ Nenhuma afirmação criada.")
        
        # Exemplos mais realistas no placeholder
        exemplos_texto = [
            "O Brasil situa-se no continente europeu.",
            "A água ferve a 100 graus Celsius.",
            "O autor de 'Os Lusíadas' é Fernando Pessoa.",
            "Lisboa é a capital de Portugal."
        ]
        
        for i, opt in enumerate(q.options):
            with st.container(border=True):
                c_del, c_txt, c_bool = st.columns([0.6, 5, 2])
                
                with c_del:
                    st.write("") 
                    if st.button("🗑️", key=f"del_vf_{opt.oid}"):
                        q.options.pop(i)
                        st.rerun()
                
                with c_txt:
                    # Usar um exemplo rotativo para inspirar o professor
                    placeholder_ex = exemplos_texto[i % len(exemplos_texto)]
                    opt.text = st.text_input(
                        f"Afirmação {i+1}", 
                        value=opt.text, 
                        key=f"txt_vf_{opt.oid}",
                        placeholder=f"Ex: {placeholder_ex}", # <--- EXEMPLO MELHORADO
                        label_visibility="collapsed"
                    )
                
                with c_bool:
                    # Toggle Verdadeiro/Falso
                    val = "Verdadeiro" if opt.is_correct else "Falso"
                    sel = st.radio(
                        "Gabarito",
                        ["Verdadeiro", "Falso"],
                        index=0 if opt.is_correct else 1,
                        key=f"rad_vf_{opt.oid}",
                        horizontal=True,
                        label_visibility="collapsed"
                    )
                    opt.is_correct = (sel == "Verdadeiro")

  # --- PREVIEW UNIVERSAL E CHECKLIST ---
    st.divider()
    st.markdown("### 3. Revisão do Assistente")

    col_prev, col_ai = st.columns([1, 1])
    # --- LÓGICA DE CÁLCULOS E EXPLICAÇÕES (Dinâmica por tipo) ---
    pontos_totais = float(q.meta.points or 0)
    n_elementos = 0
    preenchidos = 0
    mensagem_ajuda = ""

    if mt == "cloze":
        n_elementos = count_gaps(q.prompt)
        preenchidos = sum(1 for b in q.blanks if b.answers and b.answers[0].strip())
        val_unitario = pontos_totais / n_elementos if n_elementos > 0 else 0
        mensagem_ajuda = f"💡 **Lógica Cloze:** O sistema criará lacunas automáticas. Cada lacuna correta vale **{val_unitario:.2f} pts**."

    elif mt.startswith("multichoice"):
        n_elementos = len([o for o in q.options if o.text.strip()])
        preenchidos = len([o for o in q.options if o.is_correct and o.text.strip()])
        if mt == "multichoice_single":
            mensagem_ajuda = f"💡 **Lógica Escolha Múltipla:** Apenas uma resposta é válida. O aluno recebe **{pontos_totais} pts** se acertar."
        else:
            val_por_opcao = pontos_totais / max(1, preenchidos)
            mensagem_ajuda = f"💡 **Lógica Seleção Múltipla:** Existem várias corretas. Cada opção certa selecionada vale **{val_por_opcao:.2f} pts**."

    elif mt == "matching":
        n_elementos = len([p for p in q.pairs if p.left.strip() and p.right.strip()])
        val_unitario = pontos_totais / n_elementos if n_elementos > 0 else 0
        mensagem_ajuda = f"💡 **Lógica Associação:** O aluno deve ligar os pares. Cada par correto vale **{val_unitario:.2f} pts**."

    with col_prev:
        st.caption("🔍 Pré-visualização para o Aluno")
        # Renderização do Enunciado limpa
        html_text = q.prompt.replace('\n', '<br>').replace('[ ]', '<u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u>')
        st.markdown(f"""
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px; border-left: 5px solid #1E5AA8; color: #333; margin-bottom: 15px;">
                {html_text}
            </div>
        """, unsafe_allow_html=True)

        # Elementos Visuais Específicos
        if mt.startswith("multichoice"):
            icon = "🔘" if mt == "multichoice_single" else "🟦"
            for opt in q.options:
                if opt.text.strip(): st.markdown(f"{icon} {opt.text}")
        elif mt == "matching":
            for p in q.pairs:
                if p.left.strip(): st.markdown(f"🔸 {p.left}  ➔  [ Escolha ]")
        elif mt == "truefalse":
            for opt in q.options:
                if opt.text.strip():
                    st.markdown(f"❓ {opt.text} — **[ V ] [ F ]**")

    with col_ai:
        st.markdown("### 📋 Checklist de Qualidade")
        with st.container(border=True):
            # Validação Geral: Enunciado
            if q.prompt.strip():
                st.write("✅ **Enunciado:** Preenchido.")
            else:
                st.write("❌ **Enunciado:** Está vazio.")

            # Validação Exclusiva por Tipo
            if mt == "cloze":
                if n_elementos > 0:
                    st.write(f"✅ **Lacunas:** {n_elementos} encontradas.")
                    if preenchidos == n_elementos:
                        st.write("✅ **Respostas:** Todas as lacunas têm gabarito.")
                    else:
                        st.write(f"⚠️ **Respostas:** Faltam {n_elementos - preenchidos} gabaritos.")
                else:
                    st.write("❌ **Lacunas:** Use `[ ]` no texto para criar espaços.")

            elif mt.startswith("multichoice"):
                if n_elementos >= 2:
                    st.write(f"✅ **Opções:** {n_elementos} alternativas criadas.")
                else:
                    st.write("❌ **Opções:** Crie pelo menos 2 alternativas.")
                
                if preenchidos > 0:
                    st.write(f"✅ **Gabarito:** {preenchidos} resposta(s) correta(s).")
                else:
                    st.write("❌ **Gabarito:** Marque qual é a opção correta.")

        st.markdown("### 🎓 Resumo da Pontuação")
        with st.chat_message("assistant"):
            st.write(mensagem_ajuda if mensagem_ajuda else "Configure a questão para ver os detalhes.")

    # --- BOTÃO FINAL DE GUARDAR (Indispensável) ---
    st.divider()
    if creating_new:
        if st.button("💾 Adicionar Questão à Ficha", type="primary", use_container_width=True):
            ta.questions.append(copy.deepcopy(q))
            st.session_state.active_view = "Editor de Ficha"
            st.session_state.active_qid = None
            if "draft_q" in st.session_state: del st.session_state.draft_q
            st.rerun()
    else:
        if st.button("✅ Concluir Edição", type="primary", use_container_width=True):
            st.session_state.active_view = "Editor de Ficha"
            st.session_state.active_qid = None
            st.rerun()