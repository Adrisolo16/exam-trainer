"""Valida el banco completo tal como lo carga la app: base + sets + tips."""
import json
import re
import sys
from pathlib import Path
from collections import Counter

DATA = Path(__file__).resolve().parent.parent / "data"
WANT = {"two": 2, "three": 3, "four": 4, "five": 5}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base = DATA / "bank.json"
    data = list(read(base)) if base.exists() else []
    n_book = len(data)

    n_var = 0
    vdir = DATA / "variants"
    if vdir.is_dir():
        for f in sorted(vdir.glob("*.json")):
            items = read(f)
            print(f"  variants/{f.name}: {len(items)}")
            data.extend(items)
            n_var += len(items)

    tips = {}
    tdir = DATA / "tips"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.json")):
            tips.update(read(f))

    for q in data:
        if not q.get("tip") and q["id"] in tips:
            q["tip"] = tips[q["id"]]

    errs = []
    ids = Counter(q["id"] for q in data)
    for qid, n in ids.items():
        if n > 1:
            errs.append(f"{qid}: id duplicado ({n} veces)")

    for q in data:
        qid = q["id"]
        if len(q["options"]) < 3:
            errs.append(f"{qid}: menos de 3 opciones")
        for letter in q["answer"]:
            if letter not in q["options"]:
                errs.append(f"{qid}: respuesta {letter} no existe en opciones")
        if len(q["text"]) < 25:
            errs.append(f"{qid}: enunciado muy corto")
        if len(q.get("explanation_en", "")) < 40:
            errs.append(f"{qid}: explicacion muy corta")
        if not q.get("tip"):
            errs.append(f"{qid}: SIN TIP")
        if q["multi"] != (len(q["answer"]) > 1):
            errs.append(f"{qid}: flag multi no coincide con la clave")
        m = re.search(r"Choose (two|three|four|five)", q["text"], re.I)
        if m and WANT[m.group(1).lower()] != len(q["answer"]):
            errs.append(f"{qid}: dice Choose {m.group(1)} pero la clave tiene {len(q['answer'])}")
        if not m and q["multi"]:
            errs.append(f"{qid}: clave multiple pero el enunciado no dice 'Choose N'")

    print(f"\nBase: {n_book}   Sets: {n_var}   TOTAL: {len(data)}")
    print(f"Tips cargados: {len(tips)}   Preguntas con tip: {sum(1 for q in data if q.get('tip'))}")

    print("\nPor dominio:")
    for dom, n in Counter(q["domain"] for q in data).most_common():
        print(f"  {n:>4}  {dom}   ({n / len(data) * 100:.1f}%)")

    print("\nMultiple respuesta:", sum(1 for q in data if q["multi"]))

    if errs:
        print(f"\n{len(errs)} PROBLEMAS:")
        for e in errs:
            print(f"  {e}")
    else:
        print("\nSin problemas.")


if __name__ == "__main__":
    main()
