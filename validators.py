# validators.py
from typing import List
# Importa as classes que definimos no models.py
from models import TA, Question, ValidationIssue 

def validate_ficha(ta: TA) -> List[ValidationIssue]:
    """
    Analisa a ficha inteira e devolve uma lista de problemas (Erros ou Avisos).
    """
    issues: List[ValidationIssue] = []

    # 1. Validação Global da Ficha
    if len(ta.questions) == 0:
        issues.append(
            ValidationIssue("ERRO", "Ficha", "A ficha não tem questões. Adiciona pelo menos uma.")
        )
        return issues

    if not ta.ta_name.strip():
        issues.append(ValidationIssue("ERRO", "Ficha", "Nome da ficha em falta."))

    # 2. Validação Pergunta a Pergunta
    for i, q in enumerate(ta.questions, start=1):
        base_where = f"Questão {i}"
        mt = q.moodle_type

        # Enunciado (obrigatório para todos)
        if not q.prompt.strip():
            issues.append(ValidationIssue("ERRO", base_where, "Enunciado em falta.", qid=q.qid, field_key="prompt"))

        # Pontuação (exceto Description que vale 0)
        if mt != "description":
            if q.meta.points is None or q.meta.points <= 0:
                issues.append(ValidationIssue("ERRO", base_where, "Pontuação inválida (tem de ser > 0).", qid=q.qid, field_key="points"))

        # --- REGRAS ESPECÍFICAS POR TIPO ---

        if mt == "description":
            pass # Texto de apoio não requer validação extra

        elif mt == "cloze" or mt == "cloze_mc":
            if len(q.blanks) < 1:
                issues.append(ValidationIssue("ERRO", base_where, "Cloze sem lacunas. Use [ ] no texto.", qid=q.qid))
            for b_idx, b in enumerate(q.blanks, start=1):
                # Verifica se existe pelo menos uma resposta preenchida
                ans = [a.strip() for a in b.answers if a.strip()]
                if not ans:
                    issues.append(ValidationIssue("ERRO", f"{base_where} > Lacuna {b_idx}", "Lacuna sem resposta correta definida.", qid=q.qid))

        elif mt.startswith("multichoice"):
            # Verifica se há texto nas opções
            opts_with_text = [o for o in q.options if o.text.strip()]
            if len(opts_with_text) < 2:
                issues.append(ValidationIssue("ERRO", base_where, "A questão precisa de pelo menos 2 opções com texto.", qid=q.qid))
            
            # Verifica quais estão marcadas como corretas (mesmo sem texto)
            marked_correct = [o for o in q.options if o.is_correct]
            
            if not marked_correct:
                 issues.append(ValidationIssue("ERRO", base_where, "Nenhuma opção marcada como correta.", qid=q.qid))
            else:
                # Se tem marcadas, verificamos se essas marcadas têm texto
                correct_with_text = [o for o in marked_correct if o.text.strip()]
                if not correct_with_text:
                    issues.append(ValidationIssue("ERRO", base_where, "A opção correta não tem texto.", qid=q.qid))
                
                # Validação específica de Single/Multi
                if mt == "multichoice_single" and len(marked_correct) > 1:
                     issues.append(ValidationIssue("ERRO", base_where, "Neste tipo só pode haver 1 correta.", qid=q.qid))
                     
        elif mt == "truefalse":
            # Agora valida a lista de frases (V/F Múltiplo)
            valid_opts = [o for o in q.options if o.text.strip()]
            if not valid_opts:
                issues.append(ValidationIssue("ERRO", base_where, "Adicione pelo menos uma afirmação V/F.", qid=q.qid))

        elif mt == "matching":
            complete_pairs = [p for p in q.pairs if p.left.strip() and p.right.strip()]
            if len(complete_pairs) < 2:
                issues.append(ValidationIssue("ERRO", base_where, "Associação requer pelo menos 2 pares completos.", qid=q.qid))
            
            # Aviso de repetição na coluna da direita
            rights = [p.right.strip() for p in complete_pairs]
            if len(set(rights)) != len(rights):
                issues.append(ValidationIssue("AVISO", base_where, "Há respostas (coluna B) repetidas. Confirma se é intencional.", qid=q.qid))

        elif mt == "shortanswer":
            ans = [a.strip() for a in q.accepted_answers if a.strip()]
            if not ans:
                issues.append(ValidationIssue("ERRO", base_where, "Indique pelo menos uma resposta aceite.", qid=q.qid))

        elif mt == "essay":
            if not q.rubric.strip():
                issues.append(ValidationIssue("AVISO", base_where, "Sem rubrica/critério. (Recomendado)", qid=q.qid))

    return issues

def update_ficha_status(ta: TA, issues: List[ValidationIssue]):
    """Atualiza o estado da ficha (RASCUNHO/VALIDADO/COM ERROS) com base nos problemas encontrados."""
    ta.last_validation = issues
    has_errors = any(i.level == "ERRO" for i in issues)
    if has_errors:
        ta.status = "COM ERROS"
    else:
        ta.status = "VALIDADO" if ta.questions else "RASCUNHO"