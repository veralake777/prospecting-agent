import re

KEYWORDS = {
    "attractions": ["attraction","family entertainment center","amusement park","water park","trampoline park","arcade","laser tag","go kart","mini golf","indoor playground","escape room","bowling alley"],
    "climbing": ["climbing gym","rock climbing","bouldering","climbing wall"],
    "golf": ["golf course","tee times","country club golf","golf club"],
    "golf_simulator": ["golf simulator","indoor golf","trackman","virtual golf"],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def classify_vertical(text: str) -> dict:
    s = _normalize(text)
    best = ("unknown", 0.0, [])
    for v, kws in KEYWORDS.items():
        matched = [k for k in kws if _normalize(k) in s]
        score = 0.0 if not matched else min(1.0, 0.7 + (0.1 * (len(matched) - 1)))
        if score > best[1]:
            best = (v, score, matched)
    return {"primary_vertical": best[0], "sub_vertical": best[2][0] if best[2] else "", "confidence": round(best[1],2), "matched_keywords": best[2]}
