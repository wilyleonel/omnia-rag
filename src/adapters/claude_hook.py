#!/usr/bin/env python3
import sys
import json
import re
import urllib.request
import urllib.parse

MAX_RESULTS = 5
MIN_SCORE = 0.012
MIN_WORDS = 4
MAX_MEMORIES = 3

# Si el prompt no menciona nada del dominio ni parece codigo, el RAG solo aporta ruido.
TECH_HINT = re.compile(
    r"[A-Za-z0-9_]+\.(ts|tsx|js|py|md|json)\b"       # archivo.ext
    r"|[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*"            # camelCase
    r"|\b[A-Z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b"        # PascalCase
    r"|\b(endpoint|ruta|router|service|repository|adapter|micro|microservicio"
    r"|controller|dto|model|schema|hook|componente|component|modulo|module"
    r"|funcion|función|clase|class|tabla|query|token|auth|login|deposit|withdraw"
    r"|transaction|wallet|price|precio|vela|candle|crm|bff|backoffice|admin)\b",
    re.IGNORECASE,
)


def should_search(prompt):
    """Filtra prompts conversacionales ('sigue', 'ok dale') que no anclan nada."""
    if len(prompt.split()) < MIN_WORDS:
        return False
    return bool(TECH_HINT.search(prompt))


def get_context(query):
    url = "http://127.0.0.1:8000/buscar?q={}&n={}".format(
        urllib.parse.quote(query), MAX_RESULTS
    )
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=3.0) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return ""

    results = [r for r in data.get("results", []) if r.get("score", 0) >= MIN_SCORE]
    if not results:
        return ""

    lines = [
        "\n--- PISTAS OMNIA-RAG ---",
        "Resumenes generados por el indexador, NO evidencia del codigo.",
        "Leer el archivo antes de afirmar nada en verde.",
        "",
    ]
    for r in results:
        meta = r.get("metadata") or r.get("meta") or {}
        source = meta.get("source") or r.get("id", "desconocido")
        symbol = meta.get("symbol")
        start, end = meta.get("start_line"), meta.get("end_line")

        ref = source
        if start and end:
            ref += ":{}-{}".format(start, end)
        elif start:
            ref += ":{}".format(start)
        if symbol and symbol not in ("text_chunk", "fts"):
            ref += "  ·  {}".format(symbol)

        lines.append(ref)
        lines.append(r.get("text", ""))
        lines.append("")

    lines.append("--- FIN PISTAS ---\n")
    return "\n".join(lines)


def get_memories(query):
    """Trae recuerdos episódicos (rules/decisions/insights guardados con /memory)
    relevantes al prompt. Antes solo /buscar (índice de código) llegaba al
    contexto de Claude; la memoria quedaba escrita pero nunca se leía sola."""
    url = "http://127.0.0.1:8000/memory/recall?q={}&top_k={}".format(
        urllib.parse.quote(query), MAX_MEMORIES
    )
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=3.0) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return ""

    # recall() ya filtra por PRUNE_THRESHOLD y ordena server-side, no hace
    # falta un umbral de score adicional acá (la escala de score de memoria
    # no es comparable con MIN_SCORE, que está calibrado para RRF de /buscar).
    results = data.get("results", [])
    if not results:
        return ""

    lines = [
        "\n--- MEMORIA OMNIA (recuerdos guardados en sesiones previas) ---",
        "Contexto guardado por vos u otra sesion anterior. NO es evidencia del codigo actual.",
        "",
    ]
    for m in results:
        mtype = m.get("type", "insight")
        lines.append("[{}] {}".format(mtype, m.get("content", "")))
    lines.append("--- FIN MEMORIA ---\n")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        return

    if sys.argv[1] != "UserPromptSubmit":
        print(sys.stdin.read())
        return

    input_data = sys.stdin.read()
    try:
        event = json.loads(input_data)
        user_prompt = event.get("prompt", "")

        if user_prompt and should_search(user_prompt):
            extra = get_context(user_prompt) + get_memories(user_prompt)
            if extra:
                event["prompt"] = "{}\n\n{}".format(user_prompt, extra)

        print(json.dumps(event))
    except Exception:
        print(input_data)


if __name__ == "__main__":
    main()
