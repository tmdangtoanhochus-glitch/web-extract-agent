import sys
sys.path.insert(0, "D:\\Kien\\hackathon\\web_extract_project_v2")
from src.runner.repository import Repository
from src.runner.service import Service

repo = Repository("data/runner.db")
try:
    Service(repo, "data/runner").add_user("runneradmin", "Runner@123456", "admin", bootstrap=True)
    print("Da tao admin Runner")
finally:
    repo.close()
