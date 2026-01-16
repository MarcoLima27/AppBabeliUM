import uuid

# Gera um ID único (ex: "q_a1b2c3d4")
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

# Conta quantos espaços [ ] existem no texto
def count_gaps(text: str) -> int:
    return text.count("[ ]")

# Prepara texto para XML (substitui & < > " ')
def escape_xml(s: str) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))