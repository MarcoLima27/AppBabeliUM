# export.py
from typing import List
import sys
import os

# Tenta importar os modelos. Se der erro, tenta adicionar o caminho atual.
# Adiciona o diretório atual ao path para garantir que Python encontra os módulos
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from models import TA, Question, ChoiceOption, MatchPair, Blank  # type: ignore
    from utils import escape_xml, count_gaps  # type: ignore
except ImportError as e:
    print(f"Erro ao importar módulos: {e}")
    raise

def build_moodle_xml_stub(ta: TA) -> str:
    """
    Gera o XML compatível com Moodle para importação.
    Suporta: Cloze, V/F (Simples e Matriz), Escolha Múltipla, Associação, Texto e Ensaio.
    """
    
    # Cabeçalho padrão do Moodle XML
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append("<quiz>")

    # Categoria por defeito (Curso / Tema / Nome da Ficha)
    # Limpa espaços extra para evitar categorias "feias"
    cat_parts = [p.strip() for p in [ta.course, ta.theme, ta.ta_name] if p.strip()]
    default_cat = "/".join(cat_parts)

    for q in ta.questions:
        # 1. Definir Categoria (para organizar no banco de questões do Moodle)
        cat = q.meta.category.strip() or default_cat
        
        # O Moodle interpreta a categoria quando encontra uma questão do tipo "category"
        lines.append('  <question type="category">')
        lines.append("    <category>")
        lines.append(f"      <text>{escape_xml('$course$/' + cat)}</text>")
        lines.append("    </category>")
        lines.append("  </question>")

        # 2. Determinar o Tipo de Questão REAL para o XML
        mt = q.moodle_type
        xml_type = mt # Por defeito, assume o nome interno

        # Lógica de conversão inteligente
        if mt == "truefalse":
            # Se tiver mais de 1 opção, vira "Matching" (Matriz V/F)
            # Se tiver apenas 1, mantém-se "truefalse"
            if len(q.options) > 1:
                xml_type = "matching"  
            else:
                xml_type = "truefalse"
        
        elif mt == "cloze" or mt == "cloze_mc":
            xml_type = "cloze"
        
        elif mt.startswith("multichoice"):
            xml_type = "multichoice"
        
        # (matching, shortanswer, essay, description mantêm-se iguais)

        # 3. Início da Tag da Questão
        lines.append(f'  <question type="{xml_type}">')

        # Nome da Questão (Visível ao professor na lista)
        qname = q.title.strip() or f"{ta.ta_name} - Questão {q.qid[:5]}"
        lines.append("    <name>")
        lines.append(f"      <text>{escape_xml(qname)}</text>")
        lines.append("    </name>")

        # --- PROCESSAMENTO DO TEXTO (Especial para CLOZE) ---
        texto_export = q.prompt
        
        if mt == "cloze" or mt == "cloze_mc":
            # Substituir os [ ] pelos códigos do Moodle
            # Ex: "O gato [ ] leite." -> "O gato {1:SHORTANSWER:=bebe} leite."
            parts = q.prompt.split("[ ]")
            texto_export = ""
            
            for i, part in enumerate(parts):
                texto_export += part
                # Se ainda houver lacunas para preencher...
                if i < len(q.blanks):
                    b = q.blanks[i]
                    # Se não houver resposta definida, põe asterisco (aceita tudo ou erro)
                    correct = b.answers[0] if b.answers else "*"
                    
                    if hasattr(b, 'distractors') and b.distractors:
                         # Se o teu modelo Blank tiver distratores (para dropdown)
                        dists = "~".join(b.distractors)
                        texto_export += f"{{1:MULTICHOICE:={correct}~{dists}}}"
                    else:
                        # Modo Escrita (Shortanswer) - Padrão do código atual
                        # Se case_sensitive for True, usamos SHORTANSWER_C
                        sa_code = "SHORTANSWER_C" if b.case_sensitive else "SHORTANSWER"
                        texto_export += f"{{1:{sa_code}:={correct}}}"
        
        # Escrever o Enunciado Final (HTML)
        lines.append('    <questiontext format="html">')
        lines.append(f"      <text><![CDATA[{texto_export}]]></text>")
        lines.append("    </questiontext>")

        # Pontuação (Description vale 0)
        if mt == "description":
            lines.append("    <defaultgrade>0</defaultgrade>")
        else:
            lines.append(f"    <defaultgrade>{q.meta.points}</defaultgrade>")

        # Feedback Geral
        if q.meta.feedback_general.strip():
            lines.append('    <generalfeedback format="html">')
            lines.append(f"      <text><![CDATA[{q.meta.feedback_general}]]></text>")
            lines.append("    </generalfeedback>")

        # 4. Detalhes Específicos por Tipo

        # --- ESCOLHA MÚLTIPLA ---
        if xml_type == "multichoice":
            single = (mt == "multichoice_single")
            lines.append(f"    <single>{'true' if single else 'false'}</single>")
            lines.append(f"    <shuffleanswers>{'true' if q.shuffle_options else 'false'}</shuffleanswers>")
            
            correct_opts = [o for o in q.options if o.is_correct and o.text.strip()]
            # Calcula a percentagem: 
            # Se for single: 100% para a correta.
            # Se for multi: 100 / nº de corretas.
            frac_correct = 100 if single else (100 / max(1, len(correct_opts)))
            # Penalização para erradas em multi (opcional, aqui pomos 0 para simplificar ou -frac)
            
            for o in q.options:
                if not o.text.strip(): continue
                fraction = frac_correct if o.is_correct else 0
                
                # Formato: <answer fraction="100">
                lines.append(f'    <answer fraction="{fraction}" format="html">')
                lines.append(f"      <text><![CDATA[{o.text}]]></text>")
                if o.feedback.strip():
                    lines.append(f"      <feedback format='html'><text><![CDATA[{o.feedback}]]></text></feedback>")
                lines.append("    </answer>")

        # --- VERDADEIRO/FALSO (Único - Clássico) ---
        elif xml_type == "truefalse":
            # Assume a 1ª opção como referência. 
            # Se a opção[0] (ex: "A frase é bonita") for marcada como True, a resposta é 'true'.
            # Se o utilizador marcou a opção[1] (Falso) como correta, a resposta é 'false'.
            
            # Lógica defensiva: Procura qual é a opção VERDADEIRA
            # No teu UI, q.options[0] costuma ser o botão "Verdadeiro".
            is_true_correct = q.options[0].is_correct if q.options else True
            
            lines.append(f'    <answer fraction="100"><text>{"true" if is_true_correct else "false"}</text></answer>')
            lines.append(f'    <answer fraction="0"><text>{"false" if is_true_correct else "true"}</text></answer>')

        # --- MATCHING (Inclui o V/F Múltiplo / Matriz) ---
        elif xml_type == "matching":
            lines.append(f"    <shuffleanswers>{'true' if q.shuffle_options or q.shuffle_pairs else 'false'}</shuffleanswers>")
            
            # CASO A: É um V/F transformado em Matriz
            if mt == "truefalse":
                used_answers = set()
                for opt in q.options:
                    if not opt.text.strip(): continue
                    # A resposta na dropdown será "Verdadeiro" ou "Falso"
                    ans_text = "Verdadeiro" if opt.is_correct else "Falso"
                    used_answers.add(ans_text)
                    
                    lines.append('    <subquestion format="html">')
                    lines.append(f"      <text><![CDATA[{opt.text}]]></text>")
                    lines.append(f"      <answer><text>{ans_text}</text></answer>")
                    lines.append("    </subquestion>")
                
                # Truque: Se todas as frases forem "Verdadeiro", o aluno deduziria a resposta.
                # Temos de adicionar o "Falso" como resposta "órfã" (distrator) para aparecer na lista.
                if "Verdadeiro" not in used_answers:
                     lines.append('    <subquestion format="html"><text></text><answer><text>Verdadeiro</text></answer></subquestion>')
                if "Falso" not in used_answers:
                     lines.append('    <subquestion format="html"><text></text><answer><text>Falso</text></answer></subquestion>')

            # CASO B: É um Matching normal
            else:
                for p in q.pairs:
                    if not (p.left.strip() and p.right.strip()): continue
                    lines.append('    <subquestion format="html">')
                    lines.append(f"      <text><![CDATA[{p.left}]]></text>")
                    lines.append(f"      <answer><text><![CDATA[{p.right}]]></text></answer>")
                    lines.append("    </subquestion>")
                
                # Distratores (lado direito extra)
                for dist in q.distractors_right:
                    if dist.strip():
                        lines.append(f'    <subquestion format="html"><text></text><answer><text><![CDATA[{dist}]]></text></answer></subquestion>')

        # --- RESPOSTA CURTA ---
        elif xml_type == "shortanswer":
            lines.append(f"    <usecase>{'1' if q.sa_case_sensitive else '0'}</usecase>")
            ans = [a.strip() for a in q.accepted_answers if a.strip()]
            if ans:
                frac = 100  # Qualquer uma das aceites dá 100%
                for a in ans:
                    lines.append(f'    <answer fraction="{frac}" format="moodle_auto_format">')
                    lines.append(f"      <text><![CDATA[{a}]]></text>")
                    lines.append("    </answer>")

        # --- ENSAIO (Texto Livre) ---
        elif xml_type == "essay":
            lines.append("    <responseformat>editor</responseformat>")
            lines.append("    <responsetemplate format='html'><text></text></responsetemplate>")
            if q.rubric:
                 # Se houver rubrica, pode-se colocar como info para o avaliador
                 lines.append(f"    <graderinfo format='html'><text><![CDATA[{q.rubric}]]></text></graderinfo>")

        # Fecha a pergunta principal
        lines.append("  </question>")

        # 5. INJEÇÃO AUTOMÁTICA DA PERGUNTA DE CORREÇÃO (Se ativada no V/F)
        if mt == "truefalse" and q.tf_require_correction:
            lines.append('  <question type="essay">')
            name_corr = f"{q.title} (Correção)" if q.title else "Correção V/F"
            
            lines.append("    <name>")
            lines.append(f"      <text>{escape_xml(name_corr)}</text>")
            lines.append("    </name>")
            
            lines.append('    <questiontext format="html">')
            lines.append("      <text><![CDATA[<p><b>Justificação / Correção:</b></p><p>Reescreva corretamente as afirmações que classificou como Falsas na pergunta anterior.</p>]]></text>")
            lines.append("    </questiontext>")
            
            lines.append("    <defaultgrade>1.0</defaultgrade>")
            lines.append("    <responseformat>editor</responseformat>")
            # Correção das aspas para evitar erro de string
            lines.append('    <responsetemplate format="html"><text></text></responsetemplate>')
            lines.append("  </question>")

    lines.append("</quiz>")
    return "\n".join(lines)