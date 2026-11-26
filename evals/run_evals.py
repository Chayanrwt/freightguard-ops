import json
from pathlib import Path
from app.agent.workflow import run_document_pipeline


def main() -> None:
    golden = json.loads(Path("evals/golden_dataset.json").read_text(encoding="utf-8"))
    total = len(golden)
    type_hits = 0
    ref_hits = 0
    route_hits = 0

    print(f"{'File':<35} | {'Type':<6} | {'Ref':<6} | {'Route':<6} | {'Actual Route'}")
    print("-" * 82)

    for case in golden:
        path = Path("sample_docs") / case["file_name"]
        res = run_document_pipeline(path, tenant_id=case["tenant_id"], persist=False)

        t_ok = res.record.doc_type == case["expected_doc_type"]
        actual_ref = str(res.record.reference_number.value) if res.record.reference_number else None
        r_ok = actual_ref == case["expected_ref"]
        rt_ok = res.route_action == case["expected_route"]

        type_hits += int(t_ok)
        ref_hits += int(r_ok)
        route_hits += int(rt_ok)

        print(
            f"{case['file_name']:<35} | "
            f"{'PASS' if t_ok else 'FAIL':<6} | "
            f"{'PASS' if r_ok else 'FAIL':<6} | "
            f"{'PASS' if rt_ok else 'FAIL':<6} | "
            f"{res.route_action}"
        )

    print("-" * 82)
    print(f"Doc Classification Accuracy : {type_hits}/{total} ({type_hits/total:.0%})")
    print(f"Reference Extraction Exact  : {ref_hits}/{total} ({ref_hits/total:.0%})")
    print(f"Policy Routing Accuracy     : {route_hits}/{total} ({route_hits/total:.0%})")


if __name__ == "__main__":
    main()
