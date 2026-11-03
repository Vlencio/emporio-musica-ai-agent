import argparse
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from agent import agent as agent_module

from agent.prompts import POLICIES

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
CASES_PATH = os.path.join(EVALS_DIR, "cases.json")
RESULTS_DIR = os.path.join(EVALS_DIR, "results")
TRANSCRIPTS_DIR = os.path.join(RESULTS_DIR, "transcripts")

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-5-5")
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

JUDGE_SYSTEM = """Você avalia respostas de um agente de atendimento da loja Empório da Música.
Você recebe: a conversa completa (incluindo chamadas de ferramentas e o que elas retornaram), o comportamento esperado escrito por quem conhece os dados, e as politicas da loja, para conferir se a resposta se encaixa nelas.
Julgue SOMENTE se a conversa atende ao comportamento esperado. Não use conhecimento próprio sobre a loja, apenas as politicas.
Seja rigoroso com fatos (preços, status, regras) e tolerante com estilo e formatação.
Responda apenas com um JSON: {"pass": true|false, "reason": "<uma frase em português>"}"""


def now_campo_grande() -> str:
    now = datetime.now(ZoneInfo("America/Campo_Grande"))
    return f"{DIAS[now.weekday()]}, {now:%d/%m/%Y %H:%M}"


def block_get(block, key):
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def run_case(case):
    """Roda os turnos do caso com histórico limpo. Devolve respostas, tools chamadas e transcrição."""
    agent_module.history.clear()
    answers, error = [], None
    try:
        for turn in case["turns"]:
            answers.append(agent_module.chat(turn))
    except Exception as e:  # um caso quebrado não derruba o resto
        error = f"{type(e).__name__}: {e}"

    tool_calls, transcript = [], []
    for msg in agent_module.history:
        content = msg["content"]
        if isinstance(content, str):
            transcript.append(f"**{msg['role']}:** {content}")
            continue
        for block in content:
            btype = block_get(block, "type")
            if btype == "text":
                transcript.append(f"**{msg['role']}:** {block_get(block, 'text')}")
            elif btype == "tool_use":
                call = {"name": block_get(block, "name"), "input": block_get(block, "input")}
                tool_calls.append(call)
                transcript.append(f"*[tool_use]* `{call['name']}` {json.dumps(call['input'], ensure_ascii=False)}")
            elif btype == "tool_result":
                result = block_get(block, "content")
                if isinstance(result, list):
                    result = " ".join(block_get(b, "text") or "" for b in result)
                transcript.append(f"*[tool_result]* {str(result)}")
    return {"answers": answers, "tool_calls": tool_calls, "transcript": "\n\n".join(transcript), "error": error}


def deterministic_checks(case, run):
    failures = []
    text = "\n".join(run["answers"]).lower()
    called = {c["name"] for c in run["tool_calls"]}

    if run["error"]:
        failures.append(f"erro na execução: {run['error']}")
    for tool in case.get("expect_tools", []):
        if tool not in called:
            failures.append(f"não chamou {tool}")
    for tool in case.get("expect_tools_not", []):
        if tool in called:
            failures.append(f"chamou {tool} indevidamente")
    if case.get("expect_no_tools") and called:
        failures.append(f"chamou ferramentas sem necessidade: {sorted(called)}")
    for pattern in case.get("must_match", []):
        if not re.search(pattern, text):
            failures.append(f"faltou /{pattern}/")
    for pattern in case.get("must_not_match", []):
        if re.search(pattern, text):
            failures.append(f"apareceu /{pattern}/")
    return failures


def judge(client, case, run):
    rubric = case["rubric"].replace("{agora}", now_campo_grande())
    prompt = (
        f"<conversa>\n{run['transcript']}\n</conversa>\n\n"
        f"<comportamento_esperado>\n{rubric}\n</comportamento_esperado>\n\n"
        f"<politicas_da_loja>\n{POLICIES}\n</politicas_da_loja>"
    )
    raw, stop = "", None
    for _ in range(2):  # uma nova tentativa se a resposta vier inválida
        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=2048,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        stop = response.stop_reason
        raw = "".join(b.text for b in response.content if b.type == "text")
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            verdict = json.loads(match.group(0))
            return bool(verdict["pass"]), str(verdict.get("reason", ""))
        except Exception:
            continue
    return False, f"juiz devolveu resposta inválida (stop_reason={stop}): {raw[:200]}"

def write_report(results, started, use_judge):
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    for r in results:
        with open(os.path.join(TRANSCRIPTS_DIR, f"{r['id']}.md"), "w", encoding="utf-8") as f:
            f.write(f"# {r['id']} ({r['category']})\n\n{r['transcript']}\n")

    total = len(results)
    passed = sum(r["pass"] for r in results)
    by_cat = {}
    for r in results:
        ok, n = by_cat.get(r["category"], (0, 0))
        by_cat[r["category"]] = (ok + r["pass"], n + 1)

    lines = [
        "# Resultados da avaliação",
        "",
        f"- Data: {started}",
        f"- Agente: `{agent_module.MODEL}`" + (f" · Juiz: `{JUDGE_MODEL}`" if use_judge else " · sem juiz LLM"),
        f"- **Aprovados: {passed}/{total} ({passed / total:.0%})**",
        "",
        "## Por categoria",
        "",
        "| Categoria | Aprovados |",
        "|---|---|",
        *[f"| {cat} | {ok}/{n} |" for cat, (ok, n) in by_cat.items()],
        "",
        "## Casos",
        "",
        "| Caso | Determinístico | Juiz | Resultado | Observação |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        det = "ok" if not r["det_failures"] else "; ".join(r["det_failures"])
        jdg = "-" if r["judge_pass"] is None else ("ok" if r["judge_pass"] else "falhou")
        status = "✅" if r["pass"] else "❌"
        lines.append(f"| [{r['id']}](transcripts/{r['id']}.md) | {det} | {jdg} | {status} | {r['judge_reason']} |")

    with open(os.path.join(RESULTS_DIR, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULTS_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return passed, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="ids dos casos a rodar")
    parser.add_argument("--no-judge", action="store_true", help="pula o juiz LLM")
    args = parser.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]

    client = anthropic.Anthropic()
    started = datetime.now(ZoneInfo("America/Campo_Grande")).strftime("%d/%m/%Y %H:%M")
    results = []

    for i, case in enumerate(cases, 1):
        t0 = time.time()
        run = run_case(case)
        det_failures = deterministic_checks(case, run)
        judge_pass, judge_reason = (None, "")
        if not args.no_judge:
            judge_pass, judge_reason = judge(client, case, run)
        ok = not det_failures and judge_pass is not False
        results.append({
            "id": case["id"], "category": case["category"], "pass": ok,
            "det_failures": det_failures, "judge_pass": judge_pass, "judge_reason": judge_reason,
            "tool_calls": run["tool_calls"], "answers": run["answers"], "transcript": run["transcript"],
        })
        print(f"[{i}/{len(cases)}] {'PASS' if ok else 'FAIL'} {case['id']} ({time.time() - t0:.1f}s)"
              + ("" if ok else f" -> {'; '.join(det_failures) or judge_reason}"))

    passed, total = write_report(results, started, not args.no_judge)
    print(f"\n{passed}/{total} aprovados. Relatório: evals/results/results.md")


if __name__ == "__main__":
    main()
