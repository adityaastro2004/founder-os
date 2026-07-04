"""
Unit tests for the IR → n8n compiler (app/workflows/compiler.py) — ADR-008 Track D2.

Standalone, runnable, no live n8n / no LLM / no DB (per standards/testing.md):
    cd founder-os/apps/api && source .venv/bin/activate && python3 test_workflow_compiler.py

Covers (Contract 2):
  - manual trigger → a Manual Trigger node
  - cron trigger → a Schedule Trigger node carrying the cron, plus Manual Trigger
  - one HTTP node per IR step, plus start + finish callback nodes
  - every step node POSTs to the callback URL built from callback_base_url
    (host.docker.internal form), NOT localhost
  - the X-FOS-Workflow-Token header is present on every callback node, sourced
    from the injected sign_token_fn (a fake here — HMAC is Wave 3, not the compiler)
  - the master secret never leaks into the emitted JSON
  - linear depends_on chain → sequential connections
"""

import hashlib
import json
import sys

from app.workflows.compiler import compile_ir_to_n8n

_passed = 0
_failed = 0

# Host-reachable callback base (what WORKFLOW_CALLBACK_BASE_URL holds so n8n in a
# container can reach the host API — NOT localhost).
CALLBACK_BASE = "http://host.docker.internal:8000"

# A fake master secret that must NEVER appear in the compiled JSON.
FAKE_MASTER_SECRET = "super-secret-master-key-do-not-leak-0123456789"

WORKFLOW_ID = "wf-1234-abcd"
USER_ID = "user-9999"


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


def fake_sign_token_fn(workflow_id: str, user_id: str, step_id) -> str:
    """
    Stand-in for the Wave-3 HMAC signer. Returns an opaque per-node token that is
    derived-looking but NEVER contains the master secret OR the raw user_id —
    exactly the properties the real HMAC token preserves (C-5; user identity is
    derived server-side from the verified token, never readable from it). The
    test asserts both the master secret and the plaintext user_id are absent from
    the JSON, so a correct fake (like a real HMAC) must not echo them.
    """
    # Deterministic, distinct per (workflow, user, step); opaque digest — does not
    # echo the master secret or the plaintext user_id.
    digest = hashlib.sha256(
        f"{FAKE_MASTER_SECRET}:{workflow_id}:{user_id}:{step_id or 'boundary'}".encode()
    ).hexdigest()
    return f"tok.{digest}"


def manual_ir() -> dict:
    return {
        "ir_version": 1,
        "trigger": {"type": "manual"},
        "steps": [
            {
                "id": "s1",
                "type": "agent",
                "agent": "research",
                "instruction": "Summarise last week's support tickets.",
                "inputs": {},
                "depends_on": [],
            },
            {
                "id": "s2",
                "type": "action",
                "agent": "support",
                "tool": "search_knowledge",  # LOW-risk
                "arguments": {"query": "tickets"},
                "depends_on": ["s1"],
            },
        ],
    }


def cron_ir() -> dict:
    ir = manual_ir()
    ir["trigger"] = {"type": "cron", "cron": "0 3 * * 1", "timezone": "Asia/Kolkata"}
    return ir


def _nodes_by_type(compiled: dict, node_type: str) -> list:
    return [n for n in compiled["nodes"] if n["type"] == node_type]


def _step_callback_nodes(compiled: dict) -> list:
    """HTTP nodes whose URL is the /callback/step endpoint."""
    out = []
    for n in compiled["nodes"]:
        if n["type"] != "n8n-nodes-base.httpRequest":
            continue
        if n["parameters"].get("url", "").endswith("/api/workflows/callback/step"):
            out.append(n)
    return out


def _header_value(node: dict, header_name: str):
    params = node["parameters"].get("headerParameters", {}).get("parameters", [])
    for p in params:
        if p.get("name") == header_name:
            return p.get("value")
    return None


def main() -> None:
    # ---- manual trigger ----
    print("== compile: manual trigger ==")
    compiled = compile_ir_to_n8n(
        WORKFLOW_ID,
        manual_ir(),
        user_id=USER_ID,
        callback_base_url=CALLBACK_BASE,
        sign_token_fn=fake_sign_token_fn,
    )
    manual = _nodes_by_type(compiled, "n8n-nodes-base.manualTrigger")
    schedule = _nodes_by_type(compiled, "n8n-nodes-base.scheduleTrigger")
    check("manual IR emits exactly one Manual Trigger node", len(manual) == 1)
    check("manual IR emits NO Schedule Trigger node", len(schedule) == 0)

    step_nodes = _step_callback_nodes(compiled)
    check("one /callback/step HTTP node per IR step (2)", len(step_nodes) == 2,
          detail=f"got {len(step_nodes)}")

    # start + finish callback nodes present
    urls = [n["parameters"].get("url") for n in compiled["nodes"]
            if n["type"] == "n8n-nodes-base.httpRequest"]
    check("a /callback/start node exists",
          any(u.endswith("/api/workflows/callback/start") for u in urls))
    check("a /callback/finish node exists",
          any(u.endswith("/api/workflows/callback/finish") for u in urls))

    # ---- callback URL uses host.docker.internal, not localhost ----
    print("== callback URL is host-reachable (not localhost) ==")
    all_http_urls = urls
    check("every callback URL is built from callback_base_url",
          all(u.startswith(CALLBACK_BASE) for u in all_http_urls),
          detail=str(all_http_urls))
    check("no callback URL contains 'localhost'",
          all("localhost" not in u for u in all_http_urls),
          detail=str(all_http_urls))
    check("step node URL is exactly the callback/step endpoint",
          step_nodes[0]["parameters"]["url"]
          == f"{CALLBACK_BASE}/api/workflows/callback/step")

    # ---- signed-token header present via injected fn ----
    print("== signed-token header present on every callback node ==")
    callback_http = [n for n in compiled["nodes"]
                     if n["type"] == "n8n-nodes-base.httpRequest"]
    all_have_token = all(
        _header_value(n, "X-FOS-Workflow-Token") for n in callback_http
    )
    check("every callback HTTP node carries X-FOS-Workflow-Token", all_have_token)
    # token came from the injected fn (its distinctive prefix)
    s1_node = next(n for n in step_nodes
                   if "s1" in json.dumps(n["parameters"]))
    s1_token = _header_value(s1_node, "X-FOS-Workflow-Token")
    check("step token is the value returned by the injected sign_token_fn",
          s1_token == fake_sign_token_fn(WORKFLOW_ID, USER_ID, "s1"),
          detail=str(s1_token))

    # ---- master secret never leaks ----
    print("== master secret never appears in the compiled JSON ==")
    blob = json.dumps(compiled)
    check("FAKE_MASTER_SECRET is absent from the compiled JSON",
          FAKE_MASTER_SECRET not in blob)
    # user_id must NOT be baked into node bodies (derived from token server-side)
    check("user_id is not written into the compiled JSON",
          USER_ID not in blob)

    # ---- linear chain wiring ----
    print("== linear depends_on chain → sequential connections ==")
    conns = compiled["connections"]
    # Manual Trigger → FOS Start
    check("Manual Trigger connects to FOS Start",
          _connects_to(conns, "Manual Trigger", "FOS Start"))
    # FOS Start → first step
    start_targets = _targets(conns, "FOS Start")
    check("FOS Start connects to exactly one downstream node",
          len(start_targets) == 1, detail=str(start_targets))
    # last step → FOS Finish
    check("a node connects to FOS Finish",
          any("FOS Finish" in _targets(conns, src) for src in conns))

    # ---- cron trigger ----
    print("== compile: cron trigger → Schedule Trigger node ==")
    compiled_cron = compile_ir_to_n8n(
        WORKFLOW_ID,
        cron_ir(),
        user_id=USER_ID,
        callback_base_url=CALLBACK_BASE,
        sign_token_fn=fake_sign_token_fn,
    )
    sched = _nodes_by_type(compiled_cron, "n8n-nodes-base.scheduleTrigger")
    check("cron IR emits exactly one Schedule Trigger node", len(sched) == 1)
    check("cron IR still emits a Manual Trigger (run-now path)",
          len(_nodes_by_type(compiled_cron, "n8n-nodes-base.manualTrigger")) == 1)
    sched_blob = json.dumps(sched[0]) if sched else ""
    check("Schedule Trigger carries the cron expression '0 3 * * 1'",
          "0 3 * * 1" in sched_blob, detail=sched_blob)
    check("both triggers connect into FOS Start",
          _connects_to(compiled_cron["connections"], "Manual Trigger", "FOS Start")
          and _connects_to(compiled_cron["connections"], "Schedule Trigger", "FOS Start"))

    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


def _targets(conns: dict, from_name: str) -> list:
    entry = conns.get(from_name, {})
    main = entry.get("main", [[]])
    return [t["node"] for group in main for t in group]


def _connects_to(conns: dict, from_name: str, to_name: str) -> bool:
    return to_name in _targets(conns, from_name)


if __name__ == "__main__":
    main()
