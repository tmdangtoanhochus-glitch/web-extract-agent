"""Validate workbook trước execution; chỉ cho credential reference qua account."""
import io
import re
import zipfile
from openpyxl import load_workbook


def validate_workbook(content):
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Workbook too large")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
            raise ValueError("Workbook expanded size too large")
        if any("externallinks" in n.lower() or "vbaproject" in n.lower() for n in archive.namelist()):
            raise ValueError("External links/macros not accepted")
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    try:
        if not {"settings", "steps", "testcases"}.issubset(wb.sheetnames):
            raise ValueError("Missing sheets")
        for sheet in wb:
            rows = sheet.iter_rows()
            headers = [str(c.value or "").lower() for c in next(rows, ())]
            if not headers:
                raise ValueError("Empty sheet")
            for row in rows:
                record = {h: str(c.value or "") for h, c in zip(headers, row)}
                if sheet.title == "settings" and re.search(r"password|username|token|otp|cookie|secret", record.get("key", ""), re.I):
                    raise ValueError("Credentials not permitted in settings sheet")
                if sheet.title == "steps" and re.search(r"password|username|token|otp|cookie|secret", record.get("step", ""), re.I):
                    if record.get("value_source", "").lower() not in ("account", "testcase"):
                        raise ValueError("Sensitive step must use a local reference")
                for header, cell in zip(headers, row):
                    if cell.data_type == "f":
                        raise ValueError("Formulas not accepted")
                    if cell.value and re.search(r"password|username|token|otp|cookie|secret", header):
                        if not re.fullmatch(r"\$\{[A-Z0-9_]+\}", str(cell.value)):
                            raise ValueError("Credential must be a placeholder")
    finally:
        wb.close()
