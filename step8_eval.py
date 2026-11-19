"""Step 8: evaluate TransitDesk on a labelled test set.

Usage:
  python step8_eval.py --label baseline            run all cases, save results
  python step8_eval.py --label baseline --only p   run only cases whose id starts with 'p'
  python step8_eval.py --compare baseline improved compare two saved runs
  python step8_eval.py --report baseline           print a Markdown table for the README

Metrics (each counted only on cases where it applies):
  route        classifier chose the expected category
  ref          the booking reference was understood correctly
  urgent       urgency flag correct (where labelled)
  safe_action  cancellations pause for approval with the RIGHT booking (and only then)
  facts        the answer contains the facts it must contain (simple text check)
  grounded     LLM judge: every claim is supported by the policy / database
  on_topic     LLM judge: no information the question did not ask for
"""
import argparse
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

import db
from llm import with_backup
from step6_desk import graph, pending_requests

CASES = json.loads(Path(__file__).with_name("eval_set.json").read_text(encoding="utf-8"))
RESULTS_DIR = Path(__file__).with_name("eval_results")
METRICS = ["route", "ref", "urgent", "safe_action", "facts", "grounded", "on_topic"]


# ---------------- LLM-as-judge ----------------
class Judgement(BaseModel):
    grounded: bool = Field(description="True if every factual claim is supported by the REFERENCE")
    unsupported_claims: list[str] = Field(
        default_factory=list, description="Claims in the answer NOT supported by the REFERENCE")
    off_topic: bool = Field(
        description="True if the answer adds rules or information the question did not ask about")


JUDGE_SYSTEM = """You check answers from an airline transit-hotel desk assistant.
Compare the ANSWER with the REFERENCE facts (policy text and database).
- grounded: every factual claim (times, places, rules, numbers, phone numbers, procedures)
  appears in the REFERENCE or follows directly from it. Asking the passenger a question,
  or saying something could not be found, is not a claim.
- off_topic: the answer includes information or rules the QUESTION did not ask about.
Be strict and literal."""

judge = with_backup(lambda m: m.with_structured_output(Judgement))


def reference_text() -> str:
    policy = Path(__file__).with_name("policies.md").read_text(encoding="utf-8")
    bookings = db.query("SELECT * FROM bookings")
    hotels = db.query("SELECT * FROM hotels")
    return (f"POLICY:\n{policy}\n\nBOOKINGS:\n{json.dumps(bookings, indent=1)}"
            f"\n\nHOTELS:\n{json.dumps(hotels, indent=1)}")


# ---------------- one test case ----------------
def contains(answer: str, rule) -> bool:
    """rule is a string, or a list of alternatives (any one is enough)."""
    options = rule if isinstance(rule, list) else [rule]
    return any(option.lower() in answer.lower() for option in options)


def run_case(case: dict, run_id: str, reference: str) -> dict:
    config = {"configurable": {"thread_id": f"eval-{run_id}-{case['id']}"}}   # fresh thread
    result = {"id": case["id"], "message": case["message"], "checks": {}}
    try:
        start = time.perf_counter()
        graph.invoke({"messages": [("human", case["message"])]}, config)
        result["seconds"] = round(time.perf_counter() - start, 2)
    except Exception as e:                                   # count as a failure, keep going
        result["error"] = str(e)[:200]
        result["checks"]["route"] = False
        return result

    values = graph.get_state(config).values
    pending = pending_requests(config)            # we never resume: the database stays unchanged
    answer = "" if pending else values["messages"][-1].text
    result.update(category=values.get("category"), booking_ref=values.get("booking_ref"),
                  urgent=values.get("urgent"), paused=bool(pending),
                  paused_ref=pending[0]["booking_ref"] if pending else None, answer=answer)

    checks = result["checks"]
    checks["route"] = result["category"] == case["category"]
    if "ref" in case:
        checks["ref"] = result["booking_ref"] == case["ref"]
    if "urgent" in case:
        checks["urgent"] = result["urgent"] == case["urgent"]
    if "pause" in case:
        right_ref = (not case["pause"]) or result["paused_ref"] == case.get("ref")
        checks["safe_action"] = result["paused"] == case["pause"] and right_ref
    if case.get("must_include") and answer:
        missing = [rule for rule in case["must_include"] if not contains(answer, rule)]
        checks["facts"] = not missing
        result["missing"] = missing

    if result["category"] in ("status", "policy") and answer:   # answers written by an LLM
        verdict = judge.invoke([
            ("system", JUDGE_SYSTEM),
            ("human", f"REFERENCE:\n{reference}\n\nQUESTION: {case['message']}\n\nANSWER: {answer}"),
        ])
        checks["grounded"] = verdict.grounded
        checks["on_topic"] = not verdict.off_topic
        result["unsupported"] = verdict.unsupported_claims
    return result


# ---------------- summary ----------------
def summarise(results: list[dict]) -> dict:
    summary = {}
    for metric in METRICS:
        values = [r["checks"][metric] for r in results if metric in r["checks"]]
        if values:
            summary[metric] = {"passed": sum(values), "total": len(values),
                               "rate": round(sum(values) / len(values), 3)}
    times = sorted(r["seconds"] for r in results if "seconds" in r)
    if times:
        summary["latency"] = {"avg": round(sum(times) / len(times), 2),
                              "p95": times[min(len(times) - 1, int(0.95 * len(times)))]}
    summary["errors"] = sum("error" in r for r in results)
    return summary


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 46)
    for metric in METRICS:
        if metric in summary:
            s = summary[metric]
            print(f"  {metric:<12} {s['passed']:>3}/{s['total']:<3}  {s['rate'] * 100:5.1f}%")
    if "latency" in summary:
        print(f"  {'latency':<12} avg {summary['latency']['avg']}s   "
              f"p95 {summary['latency']['p95']}s")
    print(f"  {'errors':<12} {summary['errors']}")
    print("=" * 46)


def evaluate(label: str, only: str, delay: float, allow_postgres: bool) -> None:
    if db.USE_POSTGRES and not allow_postgres:
        raise SystemExit("DATABASE_URL points to Postgres. The evaluation RESETS the bookings, "
                         "which would wipe the live demo data.\nRun it locally without "
                         "DATABASE_URL, or add --allow-postgres if this is a test database.")
    db.init_db()                          # same starting data for every run
    reference = reference_text()
    run_id = uuid.uuid4().hex[:6]
    cases = [c for c in CASES if c["id"].startswith(only)]
    results = []
    for case in cases:
        r = run_case(case, run_id, reference)
        results.append(r)
        failed = [name for name, ok in r["checks"].items() if not ok]
        mark = "PASS" if not failed else "FAIL " + ",".join(failed)
        print(f"{r['id']:<4} {r.get('seconds', 0):>5}s  {mark:<28} {case['message'][:45]}")
        if "error" in r:
            print(f"        error: {r['error']}")
        if failed and r.get("answer"):
            print(f"        answer: {r['answer'][:160]}")
        if r.get("missing"):
            print(f"        missing: {r['missing']}")
        if r.get("unsupported"):
            print(f"        unsupported: {r['unsupported']}")
        time.sleep(delay)                 # be gentle with free-tier rate limits

    summary = summarise(results)
    print_summary(summary)
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"label": label, "summary": summary, "results": results},
                               indent=2), encoding="utf-8")
    print(f"saved {path}")


# ---------------- compare two runs ----------------
def latest(label: str) -> dict:
    files = sorted(RESULTS_DIR.glob(f"{label}_*.json"))
    if not files:
        raise SystemExit(f"No results saved with label '{label}'")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def compare(label_a: str, label_b: str) -> None:
    a, b = latest(label_a), latest(label_b)
    print(f"\n  {'metric':<12} {label_a:>12} {label_b:>12}   change")
    for metric in METRICS:
        if metric in a["summary"] and metric in b["summary"]:
            ra, rb = a["summary"][metric]["rate"], b["summary"][metric]["rate"]
            print(f"  {metric:<12} {ra * 100:>11.1f}% {rb * 100:>11.1f}%   {(rb - ra) * 100:+.1f}")
    la, lb = a["summary"].get("latency"), b["summary"].get("latency")
    if la and lb:
        print(f"  {'avg latency':<12} {la['avg']:>11}s {lb['avg']:>11}s   {lb['avg'] - la['avg']:+.2f}s")

    before = {r["id"]: r["checks"] for r in a["results"]}
    for r in b["results"]:
        for metric, ok in r["checks"].items():
            old = before.get(r["id"], {}).get(metric)
            if old is not None and old != ok:
                print(f"  {r['id']}: {metric} {'fixed' if ok else 'BROKE'}")


# ---------------- Markdown for the README ----------------
def report(label: str) -> None:
    run = latest(label)
    summary = run["summary"]
    print(f"Results on {len(run['results'])} labelled test cases (run: `{label}`)\n")
    print("| Metric | Passed | Rate |")
    print("|---|---|---|")
    for metric in METRICS:
        if metric in summary:
            s = summary[metric]
            print(f"| {metric} | {s['passed']}/{s['total']} | {s['rate'] * 100:.0f}% |")
    if "latency" in summary:
        lat = summary["latency"]
        print(f"| latency | avg {lat['avg']} s | p95 {lat['p95']} s |")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate TransitDesk")
    parser.add_argument("--label", default="run")
    parser.add_argument("--only", default="", help="run only case ids starting with this")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between cases")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    parser.add_argument("--report", metavar="LABEL", help="print a Markdown table of a run")
    parser.add_argument("--allow-postgres", action="store_true",
                        help="allow running against DATABASE_URL (it resets the bookings)")
    args = parser.parse_args()
    if args.report:
        report(args.report)
    elif args.compare:
        compare(*args.compare)
    else:
        evaluate(args.label, args.only, args.delay, args.allow_postgres)
