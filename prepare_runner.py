"""User-operated preparation: preserve existing settings unless each change is approved."""
import argparse
from pathlib import Path
from runner_agent.preparation import analyze, merge, read_workbook


def prepare(template, draft, output, prompt=input):
    target = Path(output)
    if target.suffix.lower() != ".xlsx" or target.exists():
        raise ValueError("Choose a new .xlsx output path")
    template_bytes, draft_bytes = read_workbook(template), read_workbook(draft)
    _, proposals = analyze(template_bytes, draft_bytes)
    approved = []
    for proposal in proposals:
        print(f"Setting {proposal['key']}: {proposal['before']} -> {proposal['after']}")
        print("Lý do:", proposal["reason"])
        if prompt("Đồng ý đổi setting này trong bản sao? [y/N]: ").strip().lower() == "y":
            approved.append(proposal["key"])
    if not proposals:
        print("Không cần thay đổi settings; giữ nguyên cấu hình hiện tại.")
    if read_workbook(template) != template_bytes or read_workbook(draft) != draft_bytes:
        raise ValueError("Source changed during review")
    result = merge(template_bytes, draft_bytes, approved)
    with target.open("xb") as file:
        file.write(result)
    print("Đã xuất bản sao với step inactive. Testcase do người dùng tự nhập; không có dòng testcase được sinh.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        prepare(args.template, args.draft, args.output)
    except Exception as error:
        raise SystemExit(f"Preparation stopped ({type(error).__name__}); source files unchanged.") from None
