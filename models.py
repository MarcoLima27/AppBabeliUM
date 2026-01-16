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