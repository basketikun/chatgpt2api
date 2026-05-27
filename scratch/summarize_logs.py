"""Summarize web_chat + web_image entries from logs.jsonl.

Usage (inside chatgpt2api container):
    docker cp scratch/summarize_logs.py chatgpt2api:/tmp/sl.py
    docker exec chatgpt2api python3 /tmp/sl.py
"""
import json

PATH = "/app/data/logs.jsonl"


def fmt_stages(stages):
    if not stages:
        return ""
    parts = []
    for k, v in stages.items():
        name = k[:-3] if k.endswith("_ms") else k
        parts.append(name + "=" + str(v))
    return " ".join(parts)


def main():
    entries = []
    with open(PATH) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") in ("web_chat", "web_image"):
                entries.append(d)
    print("=== {} structured entries ===".format(len(entries)))
    for e in entries[-25:]:
        det = e.get("detail") or {}
        pr = det.get("provider", "")
        op = det.get("op", "")
        ms = det.get("duration_ms", 0)
        plen = det.get("prompt_len", 0)
        tlen = det.get("text_len") or det.get("got") or ""
        sr = det.get("slow_reason", "")
        err = (det.get("error") or "")[:140]
        stages = det.get("stages") or {}
        ok = "OK  " if det.get("ok") else "FAIL"
        line = "{time} {pr}/{op} {ok} {ms}ms plen={plen} out={tlen}".format(
            time=e.get("time", ""), pr=pr, op=op, ok=ok,
            ms=ms, plen=plen, tlen=tlen,
        )
        if sr:
            line += "  [{0}]".format(sr)
        print(line)
        sg = fmt_stages(stages)
        if sg:
            print("   stages: " + sg)
        if err:
            print("   err   : " + err)


if __name__ == "__main__":
    main()
