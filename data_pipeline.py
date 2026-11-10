# -*- coding: utf-8 -*-
"""作答数据管道：规范化、去重取版、质量检查、覆盖度统计。

输入：mydata/作答记录.xlsx、模拟学生.xlsx、测验节点.xlsx、题目与材料.xlsx
输出：
  data/records_normalized.csv  当前版本记录 + 可用性标记 + 质量问题
  data/data_quality.json       数据体检报告（含修订轨迹与异常明细）
  data/coverage.csv            学生×主题的作答覆盖与得分情况

原则：异常记录只标记、不删除；缺失/待评分不推断为未掌握。
"""
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime

import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "mydata")
OUT_DIR = os.path.join(BASE, "data")

ERROR_FLAGS = {
    "得分超出满分范围", "已评分但得分缺失", "评分状态与作答内容不一致",
    "节点与题目不匹配", "节点与主题不匹配", "记录满分与题目满分不一致",
    "提交早于测验节点",
}


def read_rows(filename, sheet=None):
    wb = openpyxl.load_workbook(os.path.join(DATA_DIR, filename), data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], row)) for row in rows[1:] if row and row[0] is not None]


def to_iso(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value or "")


def to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip().replace("/", "-")
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_records(records, students, nodes, questions):
    stu_class = {str(r["学生编号"]): str(r["模拟班级编号"]) for r in students}
    node_themes = {str(r["节点编号"]): [x.strip() for x in str(r["已教及测量主题"]).split("、") if x.strip()]
                   for r in nodes}
    node_questions = {str(r["节点编号"]): {x.strip() for x in str(r["可用题目编号"]).split("、") if x.strip()}
                      for r in nodes}
    node_dates = {str(r["节点编号"]): to_date(r["模拟测验日期"]) for r in nodes}
    q_max = {qid: int(q["满分"]) for qid, q in questions.items()}

    groups = defaultdict(list)
    for row in records:
        groups[str(row["作答事件编号"])].append(row)

    current, revisions = [], []
    for event_id, rows in groups.items():
        ordered = sorted(rows, key=lambda r: (int(r["修订版本"]), to_iso(r["模拟提交时间"])))
        current.append(ordered[-1])
        if len(ordered) > 1:
            revisions.append({
                "作答事件编号": event_id,
                "学生编号": str(ordered[-1]["学生编号"]),
                "材料编号": str(ordered[-1]["材料编号"]),
                "版本数": len(ordered),
                "版本轨迹": [{
                    "修订版本": int(r["修订版本"]),
                    "记录编号": str(r["记录编号"]),
                    "评分状态": str(r["评分状态"]),
                    "得分": r["得分"],
                    "学生最终作答": r["学生最终作答"],
                    "评分点得分": r["评分点得分"],
                } for r in ordered],
            })

    issues = defaultdict(list)
    normalized = []
    for row in current:
        rid = str(row["记录编号"])
        sid = str(row["学生编号"])
        qid = str(row["材料编号"])
        node = str(row["节点编号"])
        status = str(row["评分状态"])
        score = row["得分"]
        max_score = int(row["满分"])
        answer = row["学生最终作答"]
        point_score = row["评分点得分"]
        submit = to_iso(row["模拟提交时间"])
        flags = []

        if status == "已评分" and score is None:
            flags.append("已评分但得分缺失")
        if score is not None:
            if int(score) < 0 or int(score) > max_score:
                flags.append("得分超出满分范围")
            if status != "已评分":
                flags.append("评分状态与作答内容不一致")
        if status == "未作答" and (answer not in (None, "") or score is not None or point_score not in (None, "")):
            flags.append("评分状态与作答内容不一致")
        if status == "待评分" and (score is not None or point_score not in (None, "")):
            flags.append("评分状态与作答内容不一致")
        if qid not in node_questions.get(node, set()):
            flags.append("节点与题目不匹配")
        if str(row["主题编号"]) not in node_themes.get(node, []):
            flags.append("节点与主题不匹配")
        if qid in q_max and max_score != q_max[qid]:
            flags.append("记录满分与题目满分不一致")
        node_date = node_dates.get(node)
        submit_date = to_date(submit)
        if submit_date and node_date:
            if submit_date > node_date:
                flags.append("提交晚于测验节点（复核/补录）")
            elif submit_date < node_date:
                flags.append("提交早于测验节点")

        has_error = any(f in ERROR_FLAGS for f in flags)
        usable = status == "已评分" and score is not None and not has_error
        if status == "待评分":
            availability = "待评分-信息不足"
        elif status == "未作答":
            availability = "未作答-信息不足"
        elif has_error:
            availability = "异常-需复核"
        else:
            availability = "已评分-可用于分析"

        normalized.append({
            "记录编号": rid,
            "学生编号": sid,
            "模拟班级编号": stu_class.get(sid, ""),
            "材料编号": qid,
            "主题编号": str(row["主题编号"]),
            "节点编号": node,
            "作答事件编号": str(row["作答事件编号"]),
            "修订版本": int(row["修订版本"]),
            "模拟提交时间": submit,
            "评分状态": status,
            "得分": "" if score is None else int(score),
            "满分": max_score,
            "学生最终作答": "" if answer is None else str(answer),
            "解答过程": "" if row["解答过程"] is None else str(row["解答过程"]),
            "评分点得分": "" if point_score is None else str(point_score),
            "数据可用性": availability,
            "质量问题": "；".join(flags),
        })

        for flag in flags:
            issues[flag].append({
                "记录编号": rid,
                "学生编号": sid,
                "材料编号": qid,
                "节点编号": node,
                "评分状态": status,
                "得分": score,
                "满分": max_score,
            })

    return normalized, revisions, issues


def build_coverage(normalized, students):
    rows = []
    for stu in students:
        sid = str(stu["学生编号"])
        cls = str(stu["模拟班级编号"])
        for theme in ("ALL", "T01", "T02", "T03"):
            subset = [r for r in normalized if r["学生编号"] == sid and (theme == "ALL" or r["主题编号"] == theme)]
            graded = [r for r in subset if r["评分状态"] == "已评分" and r["数据可用性"] == "已评分-可用于分析"]
            abnormal = [r for r in subset if r["数据可用性"] == "异常-需复核"]
            score = sum(int(r["得分"]) for r in graded)
            total = sum(int(r["满分"]) for r in graded)
            if not subset:
                sufficiency = "无记录"
            elif len(graded) < 5:
                sufficiency = "不足（可用记录<5）"
            elif len(graded) <= 8:
                sufficiency = "偏少（可用记录5—8）"
            else:
                sufficiency = "可分析（可用记录≥9）"
            rows.append({
                "学生编号": sid,
                "模拟班级编号": cls,
                "主题编号": theme,
                "记录数": len(subset),
                "已可用记录数": len(graded),
                "待评分记录数": sum(1 for r in subset if r["评分状态"] == "待评分"),
                "未作答记录数": sum(1 for r in subset if r["评分状态"] == "未作答"),
                "异常记录数": len(abnormal),
                "得分": score,
                "满分": total,
                "得分率": "" if total == 0 else round(score / total, 4),
                "记录充分性": sufficiency,
            })
    return rows


def main():
    questions = {str(r["材料编号"]): r for r in read_rows("题目与材料.xlsx")
                 if str(r["材料类型"]) == "题目"}
    students = read_rows("模拟学生.xlsx")
    nodes = read_rows("测验节点.xlsx")
    records = read_rows("作答记录.xlsx")

    normalized, revisions, issues = normalize_records(records, students, nodes, questions)
    coverage = build_coverage(normalized, students)

    status_counts = Counter(r["评分状态"] for r in normalized)
    availability_counts = Counter(r["数据可用性"] for r in normalized)
    class_counts = defaultdict(Counter)
    class_score = defaultdict(lambda: [0, 0])
    for r in normalized:
        cls = r["模拟班级编号"]
        class_counts[cls][r["评分状态"]] += 1
        if r["数据可用性"] == "已评分-可用于分析":
            class_score[cls][0] += int(r["得分"])
            class_score[cls][1] += int(r["满分"])

    missing_theme = []
    for stu in students:
        sid = str(stu["学生编号"])
        for theme in ("T01", "T02", "T03"):
            graded = [r for r in normalized if r["学生编号"] == sid and r["主题编号"] == theme
                      and r["数据可用性"] == "已评分-可用于分析"]
            if not graded:
                missing_theme.append({"学生编号": sid, "模拟班级编号": str(stu["模拟班级编号"]), "主题编号": theme})

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "totals": {
            "学生数": len(students),
            "班级数": len({str(s["模拟班级编号"]) for s in students}),
            "原始记录数": len(records),
            "作答事件数": len({str(r["作答事件编号"]) for r in records}),
            "当前版本记录数": len(normalized),
            "题目数": len(questions),
            "解答题数": sum(1 for q in questions.values() if int(q["满分"]) == 3),
        },
        "status_counts": dict(status_counts),
        "availability_counts": dict(availability_counts),
        "class_summary": {
            cls: {
                "学生数": sum(1 for s in students if str(s["模拟班级编号"]) == cls),
                "记录数": sum(class_counts[cls].values()),
                "状态": dict(class_counts[cls]),
                "可用记录得分率": round(class_score[cls][0] / class_score[cls][1], 4) if class_score[cls][1] else None,
            } for cls in sorted(class_counts)
        },
        "revisions": {
            "多版本事件数": len(revisions),
            "明细": revisions,
        },
        "issues": {flag: items for flag, items in issues.items()},
        "coverage_gaps": {
            "无可用记录的学生×主题": missing_theme,
            "说明": "仅表示缺少可分析记录，不能据此判定未掌握。",
        },
        "handling_rules": [
            "同一作答事件保留修订版本号最大的记录；其余版本保留在修订轨迹中，用于观察改分/重交。",
            "待评分、未作答、异常记录均不进入得分率计算，单独标注为信息不足或需复核。",
            "得分超出满分、状态与内容矛盾、节点与题目/主题不匹配的记录标记为异常，不参与统计。",
            "提交日期晚于测验节点的记录视为复核/补录，仍可参与当前统计，但单独标注；提交早于节点的记录视为异常。",
        ],
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "data_quality.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    fields = list(normalized[0].keys())
    with open(os.path.join(OUT_DIR, "records_normalized.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(normalized)

    cov_fields = list(coverage[0].keys())
    with open(os.path.join(OUT_DIR, "coverage.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cov_fields)
        writer.writeheader()
        writer.writerows(coverage)

    print(f"原始记录 {len(records)} 条 → 作答事件 {len({str(r['作答事件编号']) for r in records})} 个 → 当前版本 {len(normalized)} 条")
    print("评分状态：", dict(status_counts))
    print("数据可用性：", dict(availability_counts))
    print(f"多版本事件 {len(revisions)} 个；异常问题 {sum(len(v) for v in issues.values())} 处")
    for flag, items in issues.items():
        print(f"  - {flag}: {len(items)} 条")
    print("无可用记录的学生×主题：", len(missing_theme), "项")
    print("输出：data/data_quality.json, data/records_normalized.csv, data/coverage.csv")


if __name__ == "__main__":
    main()
