"""Excel/CSV 题库读取与增量剪贴板写入（对应需求 3.1）。"""

import csv
import logging
import math
import os

import openpyxl

log = logging.getLogger(__name__)

_NULLISH = {"", "nan", "none", "null"}


def _clean_cell(value):
    """过滤空值与 NaN，返回 None 表示该字段缺失"""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text.lower() in _NULLISH:
        return None
    return text


def _build_item(headers, row, sheet_name: str) -> dict:
    item = {}
    template_value = ""
    for index, header in enumerate(headers):
        if not header:
            continue
        value = _clean_cell(row[index]) if index < len(row) else None
        if value is None:
            continue
        if header == "template":
            template_value = value
        else:
            item[header] = value
    if not item:
        return {}
    item["template"] = template_value or sheet_name
    return item


def load_excel_cards(xlsx_path: str) -> list:
    """使用 openpyxl 只读模式快速加载多 Sheet 题库，避免引入 pandas"""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    cards = []
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) <= 1:
                continue
            headers = [str(h).strip() if h is not None else "" for h in rows[0]]
            for row in rows[1:]:
                if not any(row):
                    continue
                item = _build_item(headers, row, sheet_name)
                if item:
                    cards.append(item)
    finally:
        wb.close()
    return cards


def load_csv_cards(csv_path: str) -> list:
    """读取单表混排 CSV：存在 template 列则逐行指定，否则以文件名作为模板 ID"""
    template_id = os.path.splitext(os.path.basename(csv_path))[0]
    cards = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fp:
        reader = csv.DictReader(fp)
        fieldnames = list(reader.fieldnames or [])
        headers = [field.strip() if field else "" for field in fieldnames]
        for raw in reader:
            row = [raw.get(field) for field in fieldnames]
            item = _build_item(headers, row, template_id)
            if item:
                cards.append(item)
    return cards


def load_cards(path: str) -> list:
    """按扩展名分发 Excel / CSV 题库加载，任何解析异常都不会中断程序"""
    if not path or not os.path.isfile(path):
        log.warning("题库文件不存在：%s", path)
        return []
    try:
        if path.lower().endswith(".csv"):
            return load_csv_cards(path)
        return load_excel_cards(path)
    except Exception:
        log.error("题库解析失败：%s", path, exc_info=True)
        return []


def append_card(xlsx_path: str, sheet_name: str, fields: dict) -> bool:
    """向指定工作表追加一行卡片；文件被 Excel 占用等异常时返回 False"""
    try:
        wb = openpyxl.load_workbook(xlsx_path)
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(sheet_name)
            ws.append(list(fields))  # 新工作表以字段名作为表头
        ws = wb[sheet_name]

        headers = []
        if ws.max_row >= 1:
            headers = [
                str(cell.value).strip() if cell.value is not None else ""
                for cell in ws[1]
            ]
        headers = [h for h in headers if h]
        if not headers:
            headers = list(fields)
            ws.append(headers)

        for key in fields:
            if key not in headers:
                headers.append(key)
                ws.cell(row=1, column=len(headers), value=key)

        ws.append([fields.get(header, "") for header in headers])
        wb.save(xlsx_path)
        wb.close()
        return True
    except PermissionError:
        log.warning("题库文件被占用，无法写入：%s", xlsx_path)
        return False
    except Exception:
        log.error("追加卡片失败：%s", xlsx_path, exc_info=True)
        return False
