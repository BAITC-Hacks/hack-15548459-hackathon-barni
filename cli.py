"""Командная строка.

    python cli.py check              — проверить ключи и все модели (сделайте ДО хакатона!)
    python cli.py models nvidia      — какие модели доступны у провайдера
    python cli.py chat               — диалог с агентом
    python cli.py chat "задача"      — одна задача
    python cli.py index              — проиндексировать документы из workspace/
    python cli.py stats              — статистика по логам
"""
import argparse
import json
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from harness import config  # noqa: E402


def cmd_check(_):
    from harness.providers import available_providers, client, parse_ref
    from harness.router import ROUTER

    print("Провайдеры с ключами:", ", ".join(available_providers()) or "НЕТ — заполните .env")
    ok = True
    for role in ("smart", "fast"):
        for ref in [config.ROLES[role], config.FALLBACKS.get(role)]:
            if not ref:
                continue
            t0 = time.time()
            try:
                txt = ROUTER.chat(ref, [{"role": "user", "content": "Ответь одним словом: ok"}]).text
                tools_ok = _check_tools(ref)
                print(f"✅ {role:5} {ref:50} {time.time() - t0:5.1f}с  ответ: {txt.strip()[:20]!r}  tool calling: {tools_ok}")
            except Exception as e:
                ok = False
                print(f"❌ {role:5} {ref:50} {str(e).splitlines()[-1][:150]}")
    t0 = time.time()
    try:
        dim = len(ROUTER.embed(["проверка"])[0])
        print(f"✅ embed {config.ROLES['embed']:50} {time.time() - t0:5.1f}с  размерность: {dim}")
    except Exception as e:
        ok = False
        print(f"❌ embed {config.ROLES['embed']:50} {str(e).splitlines()[-1][:150]}")
    print("\nВсё готово 🚀" if ok else "\nЕсть проблемы — поправьте модели/ключи в .env (python cli.py models <провайдер>)")


def _check_tools(ref):
    from harness.router import ROUTER
    tool = {"type": "function", "function": {"name": "get_time", "description": "Текущее время",
                                             "parameters": {"type": "object", "properties": {}}}}
    try:
        r = ROUTER.chat(ref, [{"role": "user", "content": "Который час? Вызови инструмент."}], tools=[tool])
        return "✅" if r.tool_calls else "⚠️ не вызвал"
    except Exception as e:
        return f"❌ {str(e)[:60]}"


def cmd_models(args):
    from harness.providers import client
    names = sorted(m.id for m in client(args.provider).models.list())
    print("\n".join(n for n in names if not args.filter or args.filter.lower() in n.lower()))
    print(f"\nВсего: {len(names)}")


def cmd_chat(args):
    from harness.agent import Agent

    def approve(name, tool_args):
        return input(f"\n⚠️ Разрешить {name}({json.dumps(tool_args, ensure_ascii=False)[:300]})? [y/N] ").lower() == "y"

    agent = Agent(session_id=args.session, approve=approve)
    print(f"Сессия: {agent.session_id} · модель: {config.ROLES[agent.role]} · инструменты: {len(agent.tools)}")
    if args.task:
        print("\n🤖 " + agent.run(" ".join(args.task)))
        return
    while True:
        try:
            task = input("\n👤 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if task.lower() in ("exit", "quit", "выход"):
            break
        if task == "/reset":
            agent.reset()
            print("История очищена")
        elif task:
            print("\n🤖 " + agent.run(task))


def cmd_index(args):
    from harness.rag import INDEX
    print(INDEX.build(force=args.force))


def cmd_stats(_):
    from collections import Counter
    runs, llm, tools, errors, cost, tin, tout = 0, 0, Counter(), 0, 0.0, 0, 0
    for f in sorted((config.DATA_DIR / "traces").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            ev = e["event"]
            if ev == "agent_run_start":
                runs += 1
            elif ev == "llm_call":
                llm += 1
                cost += e.get("cost_usd", 0)
                tin += e.get("tokens_in", 0)
                tout += e.get("tokens_out", 0)
            elif ev == "agent_tool_call":
                tools[e.get("name")] += 1
            elif ev in ("llm_error",) or (ev == "agent_tool_result" and e.get("is_error") == "True"):
                errors += 1
    print(f"Задач: {runs}\nВызовов моделей: {llm}\nТокенов: {tin} вход / {tout} выход\nСтоимость: ${cost:.4f}\n"
          f"Ошибок: {errors}\nИнструменты: {dict(tools.most_common())}")


def main():
    p = argparse.ArgumentParser(description="Hackathon harness CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    m = sub.add_parser("models")
    m.add_argument("provider")
    m.add_argument("filter", nargs="?", default="")
    m.set_defaults(fn=cmd_models)
    c = sub.add_parser("chat")
    c.add_argument("task", nargs="*")
    c.add_argument("--session", default="cli")
    c.set_defaults(fn=cmd_chat)
    i = sub.add_parser("index")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_index)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
