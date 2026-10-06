"""Compare independent clause transcripts without correcting either source."""
from collections import defaultdict
import unicodedata


def normalized_text(value):
    # Typography/spacing only: preserve case, numbers, negation and conjunctions.
    value = unicodedata.normalize("NFKC", value).translate(str.maketrans("‘’“”", "''\"\""))
    return " ".join(value.split())


def clause_differences(metadata):
    lanes = {lane: defaultdict(list) for lane in ("llm", "vlm")}
    for record in metadata:
        if record.get("lane") in lanes:
            for clause in record.get("clause_ledger", []):
                lanes[record["lane"]][(clause["page_id"], clause["number"])].append(clause)
    differences = []
    for page_id, number in sorted(set(lanes["llm"]) | set(lanes["vlm"])):
        left, right = [lanes[lane].get((page_id, number), []) for lane in ("llm", "vlm")]
        if len(left) != 1 or len(right) != 1:
            reason = "条款缺失或重复，无法一一核对"
        elif normalized_text(left[0]["quote"]) != normalized_text(right[0]["quote"]):
            reason = "两路条款文字不一致，需人工对照原图"
        else:
            continue
        differences.append({"page_id": page_id, "number": number, "reason": reason,
                            "llm": left, "vlm": right})
    return differences
