"""Merge pathology/persona routes and build active dynamic Qwen-target cases."""
from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path

def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]

def atomic_jsonl(path, rows):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as h:
        for row in rows: h.write(json.dumps(row, ensure_ascii=False)+"\n")
        tmp=Path(h.name)
    tmp.replace(path)

def candidate_payload(c):
    return {"source":c["source"],"persona_id":c.get("id",c.get("persona_id")),"score":c["score"],
            "grounding":c["grounding"],"axis_scores":c["axis_scores"],
            "persona_pathology":c["persona_pathology"],"distortion_bridge":c["distortion_bridge"]}

def merge_routes(rows, routed_rows):
    routes={r["goal_id"]:r for r in routed_rows}; output=[]
    for source in rows:
        row=json.loads(json.dumps(source,ensure_ascii=False)); route=routes.get(row["source_goal_id"])
        if route:
            candidates=route.get("persona_candidates") or []
            if not candidates: raise ValueError(f"route has no persona candidate: {row['source_goal_id']}")
            row["goal_pathology"]=route["pathology"]; row["persona_match"]=candidate_payload(candidates[0])
        output.append(row)
    return output

def adapt_matched_row(row):
    """Build retrieval input only; no target-visible persona seed is created here."""
    if not row.get("goal_pathology"):
        raise ValueError(f"{row.get('set_id')}: goal pathology is incomplete")
    goal=row["goal_pathology"]
    return {"case_id":row["set_id"],"source_goal_id":row["source_goal_id"],
            "crisis_label":row["crisis_label"],"original_request":row["goal_private"],
            "evaluation":{
              **row.get("evaluation",{}),
              "cares_input_prompt":"exact final target prompt",
              "cares_input_response":"exact final target response"},
            "provenance":{"goal_pathology":goal,
              "persona_construction":"pending_full_pool_retrieval_and_dynamic_history",
              "persona_generation_status":"pending",
              "qwen_role":"goal_aware_dynamic_question_generation",
              "target_role":"all_substantive_persona_analysis_and_final_responses"}}

def status(rows):
    matched=sum(bool(r.get("goal_pathology")) for r in rows)
    return {"rows":len(rows),"matched":matched,"pending_match":len(rows)-matched,
            "active_qwen_target_ready":matched==len(rows)}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("command",choices=["status","merge","adapt"])
    p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path)
    p.add_argument("--routed",type=Path); p.add_argument("--allow-partial",action="store_true"); a=p.parse_args()
    rows=read_jsonl(a.input)
    if a.command=="status": print(json.dumps(status(rows),ensure_ascii=False,indent=2)); return
    if not a.output: p.error("--output is required")
    if a.command=="merge":
        if not a.routed: p.error("--routed is required for merge")
        rows=merge_routes(rows,read_jsonl(a.routed)); atomic_jsonl(a.output,rows)
    else:
        selected=[r for r in rows if r.get("goal_pathology")] if a.allow_partial else rows
        cases=[adapt_matched_row(r) for r in selected]; a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(cases,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(a.output),**status(rows)},ensure_ascii=False))

if __name__=="__main__": main()
