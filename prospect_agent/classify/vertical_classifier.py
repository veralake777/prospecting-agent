KEYWORDS = {
    "attractions": ["attraction","family entertainment center","amusement park","water park","trampoline park","arcade","laser tag","go kart","mini golf","indoor playground","escape room","bowling alley"],
    "climbing": ["climbing gym","rock climbing","bouldering","climbing wall"],
    "golf": ["golf course","tee times","country club golf","golf club"],
    "golf_simulator": ["golf simulator","indoor golf","trackman","virtual golf"],
}

def classify_vertical(text: str) -> dict:
    s = text.lower()
    best = ("unknown",0,[])
    for v, kws in KEYWORDS.items():
        matched = [k for k in kws if k in s]
        score = len(matched) / max(1, len(kws))
        if score > best[1]:
            best = (v, score, matched)
    return {"primary_vertical": best[0], "sub_vertical": best[2][0] if best[2] else "", "confidence": round(best[1],2), "matched_keywords": best[2]}
