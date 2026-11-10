# -*- coding: utf-8 -*-
"""学情分析层：个体诊断 + 群体（班级）分析。

输入：kb/kb.json、data/records_normalized.csv
输出：
  data/analysis_individual.json  每名学生的指标掌握、失分步骤、证据与信息充分性
  data/analysis_class.json       班级层面指标/题目表现、两班对比、共性薄弱点、典型案例候选
  data/analysis_questions.csv    题目×班级得分率
  data/analysis_score_points.csv 评分点×班级失分率

原则：
  1. 只用“已评分-可用于分析”的记录计算得分率；
  2. 可用记录不足时只描述已有表现，不下“未掌握”结论；
  3. 每条判断都能回溯到记录编号、题目和评分点。
"""
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
KB_PATH = os.path.join(BASE, "kb", "kb.json")

# 评分点描述 → 失分步骤标签（按顺序匹配，允许一个评分点命中多个标签）
ERROR_RULES = [
    (r"反向|除以负数|乘负数|不等号方向", "不等式乘除负数未变号"),
    (r"去分母", "去分母错误"),
    (r"去括号", "去括号符号错误"),
    (r"移项", "移项未变号"),
    (r"合并同类项", "合并同类项错误"),
    (r"消元", "消元步骤错误"),
    (r"交集|公共解集", "不等式组公共解集错误"),
    (r"数轴|端点", "数轴表示或端点开闭错误"),
    (r"回代|代入", "回代或代入求值错误"),
    (r"检验|核验", "缺少检验或检验错误"),
    (r"单位", "结果未写单位"),
    (r"与.*无关|倍数关系|说明理由|解释", "缺少对结果的解释"),
    (r"设未知数|等量关系|列出", "建模或列式错误"),
    (r"求出|求解", "求解过程未完成"),
    (r"答案正确", "最终结果错误"),
]

THEME_LABELS = {"T01": "代数式与整式运算", "T02": "方程与方程组", "T03": "不等式与不等式组"}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_kb():
    with open(KB_PATH, encoding="utf-8") as f:
        return json.load(f)


def usable(records):
    return [r for r in records if r["数据可用性"] == "已评分-可用于分析"]


def score_of(records):
    score = sum(int(r["得分"]) for r in records)
    total = sum(int(r["满分"]) for r in records)
    return score, total, (score / total if total else None)


def parse_points(text):
    points = {}
    for part in str(text or "").split("；"):
        if "=" in part:
            pid, value = part.split("=", 1)
            try:
                points[pid.strip()] = int(value)
            except ValueError:
                continue
    return points


def labels_for(description):
    labels = [label for pattern, label in ERROR_RULES if re.search(pattern, description)]
    return labels[:2] if labels else ["未通过该评分点"]


def confidence(n):
    if n == 0:
        return "无记录"
    if n == 1:
        return "不足"
    if n <= 3:
        return "初步"
    return "较充分"


def sufficiency(n):
    if n == 0:
        return "无记录"
    if n < 5:
        return "不足"
    if n <= 8:
        return "偏少"
    return "可分析"


def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def build_indexes(kb):
    question = kb["questions"]
    indicator_of = {qid: q["indicator_id"] for qid, q in question.items()}
    theme_of = {qid: q["theme_id"] for qid, q in question.items()}
    indicator_desc = {}
    indicator_theme = {}
    theme_name = {}
    for theme in kb["themes"]:
        theme_name[theme["theme_id"]] = theme["name"]
        for ind in theme["indicators"]:
            indicator_desc[ind["indicator_id"]] = ind["description"]
            indicator_theme[ind["indicator_id"]] = theme["theme_id"]
    return question, indicator_of, theme_of, indicator_desc, indicator_theme, theme_name


def failed_points(record, question):
    """返回该记录中得0分的评分点明细。"""
    points = parse_points(record["评分点得分"])
    out = []
    for point in question["score_points"]:
        if points.get(point["id"]) == 0:
            out.append({
                "评分点编号": point["id"],
                "评分点描述": point["description"],
                "失分标签": labels_for(point["description"]),
            })
    return out


def analyze_student(sid, records, kb, indexes):
    question, indicator_of, theme_of, indicator_desc, indicator_theme, theme_name = indexes
    student_records = [r for r in records if r["学生编号"] == sid]
    cls = student_records[0]["模拟班级编号"] if student_records else ""
    good = usable(student_records)
    score, total, rate = score_of(good)

    themes = {}
    for tid in ("T01", "T02", "T03"):
        subset = [r for r in good if theme_of.get(r["材料编号"]) == tid]
        s, t, rt = score_of(subset)
        themes[tid] = {
            "主题名称": theme_name.get(tid, tid),
            "可用记录数": len(subset),
            "得分": s,
            "满分": t,
            "得分率": None if rt is None else round(rt, 4),
            "记录充分性": sufficiency(len(subset)),
            "可否判断掌握": len(subset) >= 5,
        }

    indicators = {iid: [] for iid in indicator_desc}
    for r in good:
        indicators[indicator_of[r["材料编号"]]].append(r)
    indicator_rows = {}
    for iid, subset in indicators.items():
        s, t, rt = score_of(subset)
        indicator_rows[iid] = {
            "指标描述": indicator_desc.get(iid, ""),
            "主题编号": indicator_theme.get(iid, ""),
            "可用记录数": len(subset),
            "得分": s,
            "满分": t,
            "得分率": None if rt is None else round(rt, 4),
            "判断置信度": confidence(len(subset)),
            "是否需关注": len(subset) >= 3 and rt is not None and rt < 0.6,
        }

    error_counter = Counter()
    evidence = []
    for r in good:
        q = question[r["材料编号"]]
        for point in failed_points(r, q):
            for label in point["失分标签"]:
                error_counter[label] += 1
            evidence.append({
                "记录编号": r["记录编号"],
                "材料编号": r["材料编号"],
                "主题编号": theme_of[r["材料编号"]],
                "指标编号": indicator_of[r["材料编号"]],
                "题干": q["stem"],
                "满分": int(r["满分"]),
                "得分": int(r["得分"]),
                "评分点编号": point["评分点编号"],
                "评分点描述": point["评分点描述"],
                "失分标签": point["失分标签"],
                "学生最终作答": r["学生最终作答"],
                "解答过程": r["解答过程"],
            })

    evidence.sort(key=lambda e: (-e["满分"], e["得分"], e["材料编号"]))
    top_errors = [{"失分标签": k, "次数": v} for k, v in error_counter.most_common()]
    weak_indicators = sorted(
        [{"指标编号": iid, **row} for iid, row in indicator_rows.items()
         if row["是否需关注"]],
        key=lambda x: x["得分率"],
    )

    insufficient = [tid for tid, row in themes.items() if not row["可否判断掌握"]]
    summary_parts = [f"可用记录 {len(good)} 条，得分率 {pct(rate)}，记录充分性：{sufficiency(len(good))}。"]
    theme_text = "、".join(
        f"{tid} {pct(row['得分率'])}（{row['可用记录数']}条）" for tid, row in themes.items()
    )
    summary_parts.append(f"分主题：{theme_text}。")
    if top_errors:
        summary_parts.append("主要失分步骤：" + "、".join(
            f"{item['失分标签']}（{item['次数']}次）" for item in top_errors[:4]
        ) + "。")
    if weak_indicators:
        summary_parts.append("建议优先巩固：" + "、".join(
            f"{item['指标编号']}{item['指标描述']}（{pct(item['得分率'])}）" for item in weak_indicators[:3]
        ) + "。")
    if insufficient:
        summary_parts.append("信息不足：" + "、".join(
            f"{tid}仅{themes[tid]['可用记录数']}条可用记录，暂不能判断掌握情况" for tid in insufficient
        ) + "。")

    return {
        "学生编号": sid,
        "模拟班级编号": cls,
        "记录数": len(student_records),
        "可用记录数": len(good),
        "得分": score,
        "满分": total,
        "得分率": None if rate is None else round(rate, 4),
        "记录充分性": sufficiency(len(good)),
        "可否判断整体掌握": len(good) >= 5,
        "分主题": themes,
        "分指标": indicator_rows,
        "主要失分步骤": top_errors,
        "需关注指标": weak_indicators,
        "信息不足主题": insufficient,
        "证据": evidence[:10],
        "摘要": "".join(summary_parts),
    }


def analyze_class(cls, records, kb, indexes):
    question, indicator_of, theme_of, indicator_desc, indicator_theme, theme_name = indexes
    good = [r for r in records if r["模拟班级编号"] == cls]
    s, t, rate = score_of(good)

    themes = {}
    for tid in ("T01", "T02", "T03"):
        subset = [r for r in good if theme_of.get(r["材料编号"]) == tid]
        ss, tt, rt = score_of(subset)
        themes[tid] = {
            "主题名称": theme_name.get(tid, tid),
            "可用记录数": len(subset),
            "得分率": None if rt is None else round(rt, 4),
        }

    indicators = {iid: [] for iid in indicator_desc}
    for r in good:
        indicators[indicator_of[r["材料编号"]]].append(r)
    indicator_rows = {}
    for iid, subset in indicators.items():
        ss, tt, rt = score_of(subset)
        indicator_rows[iid] = {
            "指标描述": indicator_desc.get(iid, ""),
            "主题编号": indicator_theme.get(iid, ""),
            "可用记录数": len(subset),
            "得分": ss,
            "满分": tt,
            "得分率": None if rt is None else round(rt, 4),
        }

    error_counter = Counter()
    point_stats = defaultdict(lambda: [0, 0, ""])
    for r in good:
        q = question[r["材料编号"]]
        for point in failed_points(r, q):
            key = point["评分点编号"]
            point_stats[key][0] += 1
            point_stats[key][2] = point["评分点描述"]
            for label in point["失分标签"]:
                error_counter[label] += 1
        for point in q["score_points"]:
            point_stats[point["id"]][1] += 1
    common_weak = sorted(
        [{"评分点编号": pid, "评分点描述": desc, "失败数": fails, "评价数": total,
          "失败率": round(fails / total, 4)}
         for pid, (fails, total, desc) in point_stats.items() if fails > 0],
        key=lambda x: (-x["失败数"], -x["失败率"]),
    )

    weak_indicators = sorted(
        [{"指标编号": iid, **row} for iid, row in indicator_rows.items()
         if row["可用记录数"] >= 3 and row["得分率"] is not None and row["得分率"] < 0.5],
        key=lambda x: x["得分率"],
    )
    missing = [tid for tid in ("T01", "T02", "T03") if themes[tid]["可用记录数"] == 0]

    summary = (
        f"{cls}：可用记录 {len(good)} 条，得分率 {pct(rate)}。"
        + "分主题：" + "、".join(f"{tid} {pct(themes[tid]['得分率'])}" for tid in themes) + "。"
        + ("相对薄弱指标：" + "、".join(f"{x['指标编号']}（{pct(x['得分率'])}）" for x in weak_indicators[:4]) + "。" if weak_indicators else "")
        + ("数据缺口：" + "、".join(missing) + "无可用记录。" if missing else "")
    )

    return {
        "班级编号": cls,
        "学生数": len({r["学生编号"] for r in good}),
        "可用记录数": len(good),
        "得分": s,
        "满分": t,
        "得分率": None if rate is None else round(rate, 4),
        "分主题": themes,
        "分指标": indicator_rows,
        "相对薄弱指标": weak_indicators,
        "主要失分步骤": [{"失分标签": k, "次数": v} for k, v in error_counter.most_common()],
        "共性薄弱评分点": common_weak[:12],
        "数据缺口主题": missing,
        "摘要": summary,
    }


def build_question_and_point_tables(records, kb, indexes):
    _, indicator_of, theme_of, _, _, _ = indexes
    question = kb["questions"]
    q_rows, p_rows = [], []
    for qid in sorted(question):
        q = question[qid]
        for cls in ("DC01", "DC02", "全体"):
            subset = [r for r in usable(records) if r["材料编号"] == qid and (cls == "全体" or r["模拟班级编号"] == cls)]
            s, t, rt = score_of(subset)
            q_rows.append({
                "材料编号": qid,
                "主题编号": theme_of[qid],
                "指标编号": indicator_of[qid],
                "题型": q["type"],
                "满分": q["max_score"],
                "班级": cls,
                "可用记录数": len(subset),
                "得分": s,
                "满分合计": t,
                "得分率": "" if rt is None else round(rt, 4),
            })
        for point in q["score_points"]:
            for cls in ("DC01", "DC02", "全体"):
                subset = [r for r in usable(records) if r["材料编号"] == qid and (cls == "全体" or r["模拟班级编号"] == cls)]
                fails = 0
                rated = 0
                for r in subset:
                    pts = parse_points(r["评分点得分"])
                    if point["id"] in pts:
                        rated += 1
                        if pts[point["id"]] == 0:
                            fails += 1
                p_rows.append({
                    "材料编号": qid,
                    "主题编号": theme_of[qid],
                    "指标编号": indicator_of[qid],
                    "评分点编号": point["id"],
                    "评分点描述": point["description"],
                    "班级": cls,
                    "评价记录数": rated,
                    "失败数": fails,
                    "失败率": "" if rated == 0 else round(fails / rated, 4),
                })
    return q_rows, p_rows


def build_comparison(classes, kb, indexes):
    _, indicator_of, theme_of, indicator_desc, _, _ = indexes
    gaps = []
    for iid in sorted(set(indicator_of.values())):
        rows = {cls: classes[cls]["分指标"].get(iid) for cls in ("DC01", "DC02")}
        if not all(rows.values()):
            continue
        a, b = rows["DC01"], rows["DC02"]
        comparable = a["可用记录数"] >= 5 and b["可用记录数"] >= 5
        gaps.append({
            "指标编号": iid,
            "指标描述": indicator_desc.get(iid, ""),
            "DC01得分率": a["得分率"],
            "DC02得分率": b["得分率"],
            "差值百分点": None if a["得分率"] is None or b["得分率"] is None else round((a["得分率"] - b["得分率"]) * 100, 1),
            "两班可用记录数": {"DC01": a["可用记录数"], "DC02": b["可用记录数"]},
            "可比性": "可比" if comparable else "样本不足，仅作参考",
        })
    gaps.sort(key=lambda x: -abs(x["差值百分点"] or 0))
    return gaps


def case_candidates(individual):
    good, partial, limited, attention, sparse = [], [], [], [], []
    for sid, row in individual.items():
        missing_theme = any(v["可用记录数"] == 0 for v in row["分主题"].values())
        n = row["可用记录数"]
        if n < 5 or missing_theme:
            limited.append(sid)
        elif n < 9:
            sparse.append(sid)
        elif row["得分率"] is not None and row["得分率"] >= 0.85:
            good.append(sid)
        elif row["得分率"] is not None and 0.35 <= row["得分率"] < 0.85:
            partial.append(sid)
        else:
            attention.append(sid)
    return {
        "表现较好": sorted(good),
        "部分得分": sorted(partial),
        "记录不足": sorted(limited),
        "样本偏少": sorted(sparse),
        "需关注": sorted(attention),
        "说明": "分类仅用于挑选展示案例；记录不足不等于未掌握。",
    }


def main():
    kb = load_kb()
    indexes = build_indexes(kb)
    records = read_csv(os.path.join(DATA_DIR, "records_normalized.csv"))
    all_usable = usable(records)

    student_ids = sorted({r["学生编号"] for r in records})
    individual = {sid: analyze_student(sid, records, kb, indexes) for sid in student_ids}

    classes = {cls: analyze_class(cls, all_usable, kb, indexes) for cls in ("DC01", "DC02")}
    comparison = build_comparison(classes, kb, indexes)
    q_rows, p_rows = build_question_and_point_tables(records, kb, indexes)

    class_report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rule_version": "analysis-v1",
        "classes": classes,
        "两班指标对比": comparison,
        "典型案例候选": case_candidates(individual),
        "处理说明": [
            "得分率仅使用“已评分-可用于分析”的记录，待评分、未作答与异常记录不计入分母。",
            "指标可用记录少于3条时只给初步观察，不标为薄弱；主题可用记录少于5条时标注信息不足。",
            "共性薄弱评分点按失败数排序，失败率用于辅助判断，不替代教师判断。",
        ],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "analysis_individual.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rule_version": "analysis-v1",
            "students": individual,
        }, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, "analysis_class.json"), "w", encoding="utf-8") as f:
        json.dump(class_report, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "analysis_questions.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(q_rows[0].keys()))
        writer.writeheader()
        writer.writerows(q_rows)
    with open(os.path.join(DATA_DIR, "analysis_score_points.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(p_rows[0].keys()))
        writer.writeheader()
        writer.writerows(p_rows)

    print(f"学生分析 {len(individual)} 人 | 班级 {len(classes)} 个 | 题目×班级 {len(q_rows)} 行 | 评分点×班级 {len(p_rows)} 行")
    for cls, row in classes.items():
        print(f"- {row['摘要']}")
    print("两班差距最大的指标：")
    for gap in comparison[:5]:
        print(f"  {gap['指标编号']} {gap['指标描述']}：DC01 {pct(gap['DC01得分率'])} vs DC02 {pct(gap['DC02得分率'])}，差 {gap['差值百分点']}pp（{gap['可比性']}）")
    print("典型案例候选：", json.dumps(class_report["典型案例候选"], ensure_ascii=False))


if __name__ == "__main__":
    main()
