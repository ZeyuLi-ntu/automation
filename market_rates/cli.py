from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from .common import load, save
from .store import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="SGD利率调研：证据采集、双路验证、人工复核、模板计划")
    parser.add_argument("--db", default="data/research.sqlite3", help="跨期状态库；演示默认使用独立库")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("doctor", help="检查运行环境和所选模型，不显示密钥")
    p.add_argument("--config", help="按指定项目配置检查；默认检查本地Ollama")
    p = commands.add_parser("init", help="从现有文件生成待确认来源和模板候选")
    p.add_argument("--links", required=True); p.add_argument("--template", required=True); p.add_argument("--out", default="config/imported")
    p = commands.add_parser("demo", help="无网络演示，使用合成报价")
    p.add_argument("--out", default="runs/demo")
    p = commands.add_parser("run", help="真实采集和文字/视觉双路提取，生成待复核结果")
    p.add_argument("--config", required=True); p.add_argument("--out", required=True); p.add_argument("--as-of", required=True)
    for name in ("review", "publish"):
        p = commands.add_parser(name, help="刷新复核" if name == "review" else "保存已复核数据快照与并列顺序")
        p.add_argument("--run", required=True)
    p = commands.add_parser("decide", help="导入review.html下载的人工决定")
    p.add_argument("--run", required=True); p.add_argument("--file", required=True)
    p = commands.add_parser("override-revoke", help="停止指定报价的跨期人工修正")
    p.add_argument("--offer-key", required=True); p.add_argument("--author", required=True); p.add_argument("--reason", required=True)
    p = commands.add_parser("plan", help="验证映射，生成Excel写入计划，不启动Excel")
    p.add_argument("--run", required=True); p.add_argument("--mapping", required=True)
    p.add_argument("--template", required=True); p.add_argument("--rainbow", required=True); p.add_argument("--out", required=True)
    p = commands.add_parser("export", help="通过本机Excel生成两个新的SGD试点工作簿")
    p.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            import importlib.util
            for name, status in [("Python >=3.11", sys.version_info >= (3, 11)),
                                 ("Playwright", bool(importlib.util.find_spec("playwright"))),
                                 ("PDF渲染", bool(importlib.util.find_spec("pymupdf")))]:
                print(f'{name}: {"已配置" if status else "未配置"}')
            from .model_adapter import provider, preflight
            config = load(args.config) if args.config else {}
            print("模型服务: " + provider(config))
            print("运行策略: 仅本机推理；云端模型入口已禁用；token仅表示本地处理量。")
            status = preflight(config)
            for model in status.get("models", []):
                print(f'本地模型: {model["name"]}；能力: {", ".join(model["capabilities"])}')
            if status.get("same_model_two_modalities"):
                print("采用同一模型的文字/视觉独立输入；不代表两个不同模型，也不保证错误独立。")
            if provider(config) == "ollama":
                from .ollama_adapter import runtime_status
                loaded = runtime_status(config)
                if not loaded:
                    print("尚无已加载模型；还不能确认GPU是否实际参与推理。")
                for item in loaded:
                    placement = "GPU参与推理" if item["gpu_in_use"] else "仅CPU，未使用GPU；批量采集前请检查加速环境"
                    print(f'运行状态: {item["name"]}；{placement}；上下文{item["context_length"]}')
            print("模型配置检查通过；此检查不代表实际提取准确率已验证。")
            return
        if args.command == "init":
            from .xlsx_read import import_links, template_candidates
            out = Path(args.out)
            if out.exists():
                raise ValueError("初始化目录已存在，避免覆盖已确认配置")
            save(out / "sources.json", import_links(args.links))
            save(out / "template-candidates.json", template_candidates(args.template))
            print(f"已导入候选到{out}；来源默认未启用，产品/模板映射须先确认")
            return
        if args.command == "export":
            if os.name != "nt":
                raise ValueError("模板导出需要Windows桌面Excel；其他平台可完成采集、复核及计划生成")
            script = Path(__file__).parent.parent / "scripts/export_excel.ps1"
            subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script), "-PlanPath", str(Path(args.plan).resolve())], check=True)
            return
        db = str(Path(args.out) / "demo.sqlite3") if args.command == "demo" else args.db
        # demo directory must not be created by Store before its existence check.
        if args.command == "demo":
            if Path(args.out).exists():
                raise ValueError("演示目录已存在，请指定新目录")
            db = str(Path(args.out).parent / (Path(args.out).name + ".demo.sqlite3"))
        store = Store(db)
        try:
            if args.command == "demo":
                from .demo import make_demo
                first, resolved = make_demo(args.out, store)
                print(f'演示完成：初始待复核{first["pending"]}项；示例处理后{resolved["pending"]}项。打开{args.out}/review.html和resolved-example/rainbow.preview.html。未调用API。')
            elif args.command == "run":
                from .pipeline import configuration, live_run
                result = live_run(configuration(args.config), args.out, args.as_of, store)
                print(f'采集完成，待复核{result["pending"]}项；查看{args.out}/review.html')
            elif args.command in ("review", "publish", "decide", "plan"):
                from .pipeline import evaluate, check_evidence
                folder = Path(args.run)
                if args.command == "decide":
                    from .verify import apply_decisions
                    raw = load(folder / "run.json")
                    check_evidence(raw, folder / "evidence")
                    apply_decisions(raw, load(folder / "config.snapshot.json"), store, load(args.file))
                result = evaluate(folder, store)
                if args.command == "publish":
                    if result["demo"]:
                        raise ValueError("演示不能写入正式跨期数据")
                    if (result.get("pilot") or {}).get("no_publication"):
                        raise ValueError("本次是局部银行试点，不能作为全市场正式基准；请使用已确认范围的正式运行")
                    store.publish(result["run_id"], result["as_of"], result)
                    print("已发布数据快照；未启动Excel或发送消息")
                elif args.command == "plan":
                    from .export import make_plan
                    path = make_plan(result, load(folder / "config.snapshot.json"), load(args.mapping), args.template, args.rainbow, args.out)
                    print(f"已生成可检查计划：{path}")
                else:
                    print(f'待复核{result["pending"]}项；复核页面已刷新')
            elif args.command == "override-revoke":
                store.set_override(args.offer_key, {}, args.author, args.reason, active=False)
                print("跨期修正已撤销，历史修正记录保留")
        finally:
            store.close()
    except (ValueError, RuntimeError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"未完成：{exc}\n")
