"""Wrap the standalone live-server scripts as the pytest 'live' tier.

Each script hits localhost:8000 (started via ./start.sh) using the dev
x-test-user bypass. They stay directly runnable too: python3 test_system.py.
"""
import pathlib
import subprocess
import sys

import pytest

pytestmark = pytest.mark.live

API_ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPTS = [
    "test_system.py",
    "test_memory.py",
    "test_rag_pipeline.py",
    "test_e2e_pipeline.py",
    "test_agent_prompts.py",
    "test_agent_specialization.py",
    "test_agent_evolution.py",
    "test_workflow_ir.py",
    "test_workflow_compiler.py",
    "test_workflow_generator.py",
    "test_workflow_routes.py",
    "test_n8n_client.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_live_script(script):
    proc = subprocess.run(
        [sys.executable, str(API_ROOT / script)],
        capture_output=True, text=True, timeout=1800,
    )
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
    assert proc.returncode == 0, f"{script} failed:\n{tail}"


def test_content_agent_suite():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(API_ROOT / "test_content_agent.py"), "-q"],
        capture_output=True, text=True, timeout=1800,
    )
    tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
    assert proc.returncode == 0, f"test_content_agent.py failed:\n{tail}"
