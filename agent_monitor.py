#!/usr/bin/env python3
"""Agente de monitoramento do SMC Quant Pro.

Objetivo:
- acompanhar o funcionamento local da ferramenta
- detectar gargalos, falhas e regressões
- chamar a API do Gemini quando houver necessidade de contexto
- aplicar correções locais simples para problemas conhecidos
- persistir um relatório de observação para uso posterior
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from google import genai

APP_ROOT = Path(__file__).resolve().parent
ENV_PATH = APP_ROOT / ".env"
LOG_DIR = APP_ROOT / "logs"
REPORT_PATH = LOG_DIR / "agent_report.json"
HEARTBEAT_PATH = LOG_DIR / "agent_heartbeat.json"
LAST_ISSUE_PATH = LOG_DIR / "last_issue.txt"


def ensure_env():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY ausente em .env")
    return key


def ensure_dirs():
    LOG_DIR.mkdir(exist_ok=True)


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def list_recent_logs() -> List[str]:
    collected: List[str] = []
    for candidate in sorted(APP_ROOT.glob("*.log")) + sorted(LOG_DIR.glob("*.log")):
        collected.append(candidate.as_posix())
    return collected


def read_recent_log_tail(limit: int = 200) -> str:
    chunks: List[str] = []
    for log_path in list_recent_logs():
        content = read_text_if_exists(Path(log_path))
        if not content:
            continue
        lines = content.splitlines()
        tail = lines[-limit:]
        if tail:
            chunks.append(f"--- {log_path} ---\n" + "\n".join(tail))
    return "\n".join(chunks)


def detect_processes() -> str:
    try:
        result = subprocess.run(
            ["bash", "-lc", "pgrep -af 'main_app.py|python.*SMC_QUANT_PRO|python.*main_app' || true"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or "").strip()
    except Exception as exc:  # pragma: no cover - defensivo
        return f"process-check-error: {exc}"


def detect_error_patterns() -> str:
    signals = []
    candidates = []

    for base_dir in [APP_ROOT / "logs", APP_ROOT]:
        if not base_dir.exists():
            continue
        for file_path in sorted(base_dir.rglob("*")):
            if not file_path.is_file():
                continue
            name_l = file_path.name.lower()
            if ".venv" in file_path.parts or "__pycache__" in file_path.parts:
                continue
            if any(token in name_l for token in ["velho", "copia", "copy", "backup", "old"]):
                continue
            if file_path.name in {"agent_report.json", "agent_heartbeat.json", "last_issue.txt"}:
                continue
            if file_path.suffix.lower() not in {".log", ".out"}:
                continue
            candidates.append(file_path)

    for file_path in candidates:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in [
            "Traceback",
            "ERROR",
            "No module named 'numpy'",
            "ModuleNotFoundError",
            "API key not valid",
            "is no longer available",
            "PermissionError",
            "TimeoutError",
        ]:
            if pattern.lower() in text.lower():
                signals.append(f"{file_path.name}: {pattern}")

    return "\n".join(sorted(set(signals)))


def save_report(report: dict):
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_heartbeat(message: str):
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": message,
        "hostname": platform.node(),
    }
    HEARTBEAT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_known_fixes(issue_text: str) -> str:
    fixes: List[str] = []
    file_map = {
        "requirements-mac.txt": APP_ROOT / "requirements-mac.txt",
        "package.json": APP_ROOT / "package.json",
        "versao.json": APP_ROOT / "versao.json",
    }

    if "No module named 'numpy'" in issue_text or "numpy" in issue_text.lower():
        target = file_map["requirements-mac.txt"]
        if target.exists():
            content = target.read_text(encoding="utf-8", errors="ignore")
            if "numpy" not in content.lower():
                with target.open("a", encoding="utf-8") as fh:
                    fh.write("\n# correção automática de monitoramento\nnumpy>=2.2.0\n")
                fixes.append("adicionado numpy em requirements-mac.txt")

    if "google.genai" in issue_text or "ModuleNotFoundError" in issue_text:
        target = file_map["requirements-mac.txt"]
        if target.exists():
            content = target.read_text(encoding="utf-8", errors="ignore")
            if "google-genai" not in content.lower():
                with target.open("a", encoding="utf-8") as fh:
                    fh.write("\ngoogle-genai>=1.0.0\n")
                fixes.append("adicionado google-genai em requirements-mac.txt")

    if "models/gemini-" in issue_text or "API key not valid" in issue_text:
        env_body = "GEMINI_API_KEY=" + os.getenv("GEMINI_API_KEY", "") + "\nMODEL_NAME=gemini-3.8-flash\n"
        ENV_PATH.write_text(env_body, encoding="utf-8")
        fixes.append("ajustado modelo do Gemini para gemini-3.8-flash")

    if not fixes:
        return "nenhuma correção automática aplicada"
    return "; ".join(fixes)


def ask_gemini_for_context(issue_text: str) -> str:
    api_key = ensure_env()
    model_name = os.getenv("MODEL_NAME", "gemini-3.8-flash")
    client = genai.Client(api_key=api_key)

    prompt = f"""Você é um agente de monitoramento do SMC Quant Pro.

Contexto:
- repositório: SMC_QUANT_PRO
- objetivo da ferramenta: manter operação estável, reduzir gargalos e manter lógica de negócio da estratégia
- branch atual: feature/update-v2-85
- observações de falha:
{issue_text[:4000]}

Tarefa:
1) identifique a causa mais provável do problema
2) explique o impacto para a ferramenta
3) sugira a correção mais segura em código ou configuração
4) preserve o objetivo final da ferramenta e evite mudanças destrutivas
5) responda em português
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    if hasattr(response, "text") and response.text:
        return response.text.strip()
    if isinstance(response, dict):
        return str(response)
    return str(response)


def run_once() -> dict:
    ensure_dirs()
    ensure_env()
    proc_info = detect_processes()
    errors = detect_error_patterns()

    if not proc_info.strip():
        issue_text = "O processo principal do SMC Quant Pro não foi encontrado em execução."
        LAST_ISSUE_PATH.write_text(issue_text, encoding="utf-8")
        fix_summary = "verificar processo principal e reinicializar a aplicação"
        analysis = ask_gemini_for_context(issue_text)
        report = {
            "status": "issue_detected",
            "process_status": proc_info,
            "error_signals": issue_text,
            "fix_summary": fix_summary,
            "gemini_analysis": analysis,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        save_report(report)
        write_heartbeat("issue_detected")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    if errors:
        issue_text = "\n".join(filter(None, [proc_info, errors]))
        LAST_ISSUE_PATH.write_text(issue_text, encoding="utf-8")
        fix_summary = apply_known_fixes(issue_text)
        analysis = ask_gemini_for_context(issue_text)
        report = {
            "status": "issue_detected",
            "process_status": proc_info,
            "error_signals": errors,
            "fix_summary": fix_summary,
            "gemini_analysis": analysis,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        save_report(report)
        write_heartbeat("issue_detected")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    status = {
        "status": "ok",
        "process_status": proc_info,
        "error_signals": "",
        "fix_summary": "nenhuma correção necessária",
        "gemini_analysis": "sem sinais críticos detectados",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    save_report(status)
    write_heartbeat("healthy")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return status


def main():
    parser = argparse.ArgumentParser(description="Agente de monitoramento do SMC Quant Pro")
    parser.add_argument("--once", action="store_true", help="executa uma verificação única e sai")
    parser.add_argument("--interval", type=int, default=30, help="intervalo em segundos para loop contínuo")
    args = parser.parse_args()

    try:
        if args.once:
            run_once()
            return 0

        while True:
            try:
                run_once()
            except Exception as exc:  # pragma: no cover - proteção de runtime
                failure = {
                    "status": "monitor_error",
                    "error": str(exc),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
                save_report(failure)
                write_heartbeat("monitor_error")
                print(json.dumps(failure, ensure_ascii=False, indent=2))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Agente interrompido pelo usuário.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
