"""Bootstrap admin: người vận hành chạy trên máy có kết nối tới database Runner
thật (SQLite local HOẶC Postgres từ xa), nhập mật khẩu qua getpass. Chỉ chạy
được khi database CHƯA có user nào (xem `add_user(..., bootstrap=True)`) — sau
đó quản lý user qua UI/API (`POST /runner/users`), không chạy lại script này.

Deploy lên GreenNode (hoặc backend Postgres bất kỳ): KHÔNG cần exec vào
container đang chạy — chạy script này ngay trên máy bạn, trỏ `--postgres-dsn`
thẳng tới cùng Postgres mà biến môi trường `RUNNER_DATABASE_URL` của API đang
dùng (máy bạn phải kết nối mạng tới được server đó). Xem
docs/RUNNER_SETUP.md mục "Tạo admin khi deploy (Postgres)" để biết chi tiết."""
import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runner.repository import Repository
from src.runner.service import Service


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/runner.db", help="Đường dẫn SQLite local — bỏ qua nếu dùng --postgres-dsn")
    parser.add_argument(
        "--postgres-dsn", default=None,
        help="Connection string Postgres (vd. postgresql://user:pass@host:5432/runnerdb) — "
             "dùng khi API deploy đã set RUNNER_DATABASE_URL trỏ Postgres này. Ưu tiên hơn --db nếu có.",
    )
    parser.add_argument("--root", default="data/runner")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Mật khẩu admin Runner (tối thiểu 12 ký tự): ")
    if password != getpass.getpass("Nhập lại: "):
        raise SystemExit("Mật khẩu không khớp")
    repo = Repository(args.db, postgres_dsn=args.postgres_dsn)
    try:
        Service(repo, args.root).add_user(args.username, password, "admin", bootstrap=True)
        # Che mật khẩu trong DSN trước khi in ra terminal/log.
        target = re.sub(r"(://[^:/@]+:)[^@]*@", r"********@", args.postgres_dsn) if args.postgres_dsn else args.db
        print(f"Đã tạo admin Runner trên {target}")
    finally:
        repo.close()
