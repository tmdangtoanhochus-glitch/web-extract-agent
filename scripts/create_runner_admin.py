"""Bootstrap admin: người vận hành chạy local, nhập mật khẩu qua getpass."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runner.repository import Repository
from src.runner.service import Service


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/runner.db")
    parser.add_argument("--root", default="data/runner")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Mật khẩu admin Runner (tối thiểu 12 ký tự): ")
    if password != getpass.getpass("Nhập lại: "):
        raise SystemExit("Mật khẩu không khớp")
    repo = Repository(args.db)
    try:
        Service(repo, args.root).add_user(args.username, password, "admin", bootstrap=True)
        print("Đã tạo admin Runner")
    finally:
        repo.close()
