# -*- coding: utf-8 -*-
"""导出三任务正式成果包到工作区根目录。

输入（本项目 data/ 与 kb/）：
    kb/kb.json
    data/analysis_individual.json
    data/analysis_class.json
    data/recommendations.json
    data/recommendations_index.csv
    data/analysis_questions.csv
    data/analysis_score_points.csv
    data/data_quality.json
    data/records_normalized.csv
    data/coverage.csv

输出：
    ../../三任务成果包/
"""
import csv
import json
import os
import shutil
from collections import defaultdict

from analyzer import labels_for, parse_points

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
KB_PATH = os.path.join(BASE, "kb", "kb.json")
WORKSPACE = os.path.dirname(os.path.dirname(BASE))
OUT = os.path.join(WORKSPACE, "三任务成果包")

TASK1 = os.path.join(OUT, "任务1_学习内容梳理")
TASK2 = os.path.join(OUT, "任务2_学情分析")
TASK3 = os.path.join(OUT, "任务3_个性化建议")

CASES = [
    {
        "case_id": "CASE01",
        "sid": "D01",
        "type": "部分得分",
        "reason": "可用记录21条、得分率48.6%，解答题存在“部分步骤正确但结果/解释失分”，适合展示关键步骤定位与巩固建议。",
        "qids": ["Q014", "Q043", "Q018", "Q022"],
        "diagnosis": {
            "总体判断": "部分得分型：能进入解题入口，基本步骤可以起步，但结果呈现、检验与解释不稳定；不等式负数方向存在明确缺口。",
            "优势": [
                "Q025 三点评分全部通过；Q015、Q018 各得2/3，说明部分解答题的基本步骤可以独立完成。",
                "T02 主题得分率54.5%，为三个主题中最高，方程主体步骤相对稳定。",
            ],
            "关键问题": [
                "T01I1 33.3%、T03I1 33.3%，均低于35%关注线；T03 主题得分率37.5%，为三个主题最低。",
                "Q014 三个评分点全部失分，建模/列式与结果呈现同时出错；Q043 的P2/P3失分，负数乘除未反向；Q018 的P3失分，缺少对“结果与x无关”的解释。",
                "失分标签以“最终结果错误”7次、“缺少对结果的解释”3次为主，说明写到最后一步的检验与表达不足。",
            ],
            "待观察": [
                "T03I3 可用记录为0，T01I2、T02I2 各1条，暂不能判断这些指标的掌握情况。",
                "下一次同类任务重点观察：是否先写数量关系再列式、负数运算是否先变号、结果是否写单位并解释。",
            ],
        },
        "extra_observation": [
            "T03I3 目前无可用记录，建议在下一次测验或作业中补充“根据实际限制列不等式并解释取值范围”的任务，再判断掌握程度。",
            "T01I2、T02I2 仅1条记录，相关结论只作初步观察，不作为掌握度结论。",
        ],
    },
    {
        "case_id": "CASE02",
        "sid": "D29",
        "type": "表现较好",
        "reason": "可用记录23条、得分率85.7%，方法与计算较稳，失分集中在结果呈现；适合展示变式与迁移任务。",
        "qids": ["Q031", "Q049", "Q006", "Q014", "Q034", "Q026"],
        "diagnosis": {
            "总体判断": "表现较稳：方法与计算过程完整，失分集中在结果呈现与检验，属于“会做但收尾不严”。",
            "优势": [
                "T03 主题100%（6条），T01I2 100%（5条），T02I2 87.5%（4条）。",
                "Q031、Q049 三点评分全部通过；Q006、Q014、Q034 均得2/3，主体步骤正确。",
            ],
            "关键问题": [
                "Q006、Q014、Q034 的P3均未通过，失分标签集中在“结果未写单位”“缺少检验”“缺少对结果的解释”。",
                "Q026 为0/1，个别概念判断仍需回看。",
                "T01I3、T03I3 可用记录为0，T02I3 仅1条，迁移与解释类证据不足。",
            ],
            "待观察": [
                "补充解释类与开放情境任务，观察能否把“写单位、检验、解释”变成稳定习惯。",
                "不把 T01I3、T03I3 的0条记录写成未掌握，先补证据再判断。",
            ],
        },
        "extra_observation": [
            "T01I3、T03I3 各0条可用记录，建议在下一次任务中加入“说明结果含义/取值范围”的解释题。",
            "继续观察高表现是否稳定：用一题变式检验迁移，而不是重复原题。",
        ],
    },
    {
        "case_id": "CASE03",
        "sid": "D32",
        "type": "记录不足",
        "reason": "可用记录21条、T01/T02可分析，但目标主题T03的可用记录为0；适合展示“先补证据、不判未掌握”的处理方式。",
        "qids": ["Q014", "Q034", "Q009", "Q022"],
        "diagnosis": {
            "总体判断": "记录不足型（目标主题T03无记录）：T01、T02可分析且表现中等，T03暂不能判断；同类题在不同节点表现不一致，化简步骤尚未稳定。",
            "优势": [
                "Q006、Q031、Q036 均满分；Q009 在N01达到3/3，说明该次化简过程完整。",
                "T01、T02 主题均为66.7%，基础运算与方程组主体步骤较稳。",
            ],
            "关键问题": [
                "Q014、Q034 三个评分点全部失分，建模/列式是主要卡点；Q022 的P2/P3失分，求解过程不完整。",
                "Q009 在N01为3/3、N02降为1/3，同一知识点跨节点表现不一致，说明化简步骤尚未稳定。",
                "T01I1 57.1%、T02I3 57.1%，低于60%关注线；失分标签中合并同类项3次、建模2次、求解未完成2次、缺少检验2次。",
                "T03 三个指标可用记录均为0，不能判断不等式主题的掌握情况。",
            ],
            "待观察": [
                "先完成T03诊断题（Q037、Q038、Q039等），再判断掌握程度。",
                "用Q009的同类变式检验稳定性，观察能否在新题中稳定达到满分，而不是只记住原题。",
            ],
        },
        "extra_observation": [
            "T03 为0条可用记录，本案例不作“未掌握”结论，只安排补充诊断。",
            "Q009 的N01/N02两次作答结果不一致（3/3与1/3），后续需用变式题检验稳定性。",
        ],
    },
]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def write_csv(path, rows, fieldnames=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def table(headers, rows):
    def cell(value):
        return str(value).replace("|", "｜").replace("\n", "<br>")

    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(cell(x) for x in row) + " |")
    return "\n".join(lines)


def pct(value):
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def build_task1(kb):
    os.makedirs(TASK1, exist_ok=True)
    themes = kb["themes"]
    curriculum = kb["curriculum"]
    sections = {s["id"]: s for s in kb["textbook_sections"]}
    materials = kb["textbook_materials"]
    questions = kb["questions"]

    learning = {
        "meta": {
            "task": "任务1 学习内容梳理",
            "scope": kb["meta"]["scope"],
            "sources": kb["meta"]["sources"],
            "generated_at": kb["meta"]["generated_at"],
            "mapping_rules": [
                "主题与指标来自赛题指定的三个主题及课程要求。",
                "课标条目只纳入与七年级本主题直接相关的部分；乘法公式、因式分解、一元二次方程等后续学段内容不计入。",
                "教材印刷页与切片PDF页已按页核对；指标—教材小节为编辑映射，因为教材本身未标注指标。",
                "题目按题目与材料表中的主题、指标字段归属；一道题可对应一个指标。",
            ],
        },
        "themes": [],
        "curriculum": curriculum,
        "textbook_materials": materials,
        "question_count": len(questions),
    }

    overview_rows, indicator_rows, question_rows, curriculum_rows, textbook_rows = [], [], [], [], []
    section_to_indicators = defaultdict(list)
    for iid, ids in kb["mappings"]["indicator_to_sections"].items():
        for sid in ids:
            section_to_indicators[sid].append(iid)

    for theme in themes:
        inds = theme["indicators"]
        qids = theme["question_ids"]
        codes = sorted({ind["curriculum_code"] for ind in inds})
        mats = sorted({s["material_id"] for ind in inds for s in ind["textbook_sections"]})
        learning["themes"].append({
            "theme_id": theme["theme_id"],
            "name": theme["name"],
            "goal": theme["goal"],
            "curriculum_codes": codes,
            "indicators": inds,
            "question_ids": qids,
            "question_count": len(qids),
            "learning_cards": theme["learning_cards"],
        })
        overview_rows.append({
            "主题编号": theme["theme_id"],
            "主题名称": theme["name"],
            "学习目标": theme["goal"],
            "指标数": len(inds),
            "题目数": len(qids),
            "课标编号": "、".join(codes),
            "教材材料": "、".join(mats),
            "学习卡": "、".join(theme["learning_cards"]),
        })

        for ind in inds:
            cur = curriculum[ind["curriculum_code"]]
            sec_text = "；".join(
                f"{s['material_id']} P{s['pages']} {s['section']}" for s in ind["textbook_sections"]
            )
            indicator_rows.append({
                "主题编号": theme["theme_id"],
                "主题名称": theme["name"],
                "指标编号": ind["indicator_id"],
                "指标描述": ind["description"],
                "课标编号": ind["curriculum_code"],
                "课标标题": cur["title"],
                "课标文件页": cur["pdf_page"],
                "课标正文页": cur["print_page"],
                "教材页码范围": ind["textbook_pages"],
                "教材小节": sec_text,
                "题目编号": "、".join(ind["question_ids"]),
                "题目数": len(ind["question_ids"]),
                "学习卡": "、".join(ind["learning_cards"]),
            })

    for qid, q in sorted(questions.items()):
        point_text = "；".join(
            f"{p['id']} {p['description']}（{p['score']}分）" for p in q["score_points"]
        )
        question_rows.append({
            "题目编号": qid,
            "主题编号": q["theme_id"],
            "指标编号": q["indicator_id"],
            "题型": q["type"],
            "满分": q["max_score"],
            "评分点数": len(q["score_points"]),
            "评分点": point_text,
            "来源": q["source"],
            "题干": q["stem"],
        })

    for code, cur in sorted(curriculum.items()):
        inds = [ind["indicator_id"] for theme in themes for ind in theme["indicators"]
                if ind["curriculum_code"] == code]
        curriculum_rows.append({
            "课标编号": code,
            "标题": cur["title"],
            "领域": cur["domain"],
            "PDF页": cur["pdf_page"],
            "正文页": cur["print_page"],
            "关联指标": "、".join(inds),
            "条目": "；".join(f"{x['no']}{x['text']}" for x in cur["items"]),
            "选取说明": cur["selection_note"],
        })

    for sid, sec in sorted(sections.items()):
        textbook_rows.append({
            "小节编号": sid,
            "材料编号": sec["material_id"],
            "材料名称": materials[sec["material_id"]]["title"],
            "册别": sec["volume"],
            "章节": sec["chapter"],
            "小节": sec["section"],
            "教材页": sec["pages"],
            "切片PDF页": sec["pdf_pages"],
            "关联指标": "、".join(section_to_indicators.get(sid, [])),
        })

    write_json(os.path.join(TASK1, "task1_learning_content.json"), learning)
    write_csv(os.path.join(TASK1, "task1_theme_overview.csv"), overview_rows)
    write_csv(os.path.join(TASK1, "task1_indicator_map.csv"), indicator_rows)
    write_csv(os.path.join(TASK1, "task1_question_map.csv"), question_rows)
    write_csv(os.path.join(TASK1, "task1_curriculum_map.csv"), curriculum_rows)
    write_csv(os.path.join(TASK1, "task1_textbook_map.csv"), textbook_rows)

    md = f"""# 任务1 学习内容梳理

## 1 范围与目标

本任务覆盖七年级数学的三个指定主题：代数式与整式运算、方程与方程组、不等式与不等式组。梳理结果把“主题—指标—课标—教材—题目—学习卡”串成一条可追溯链路。

- 3 个主题、9 个观测指标、54 道题（其中 18 道解答题）、3 张学习卡。
- 课标依据为《义务教育数学课程标准（2022年版）》：CR01 代数式、CR02 方程与方程组、CR03 不等式与不等式组。
- 教材依据为人教版七年级上、下册切片：B05、B06、B02。

## 2 主题总览

{table(["主题", "学习目标", "指标数", "题目数", "课标", "学习卡"], [
    (r["主题编号"] + " " + r["主题名称"], r["学习目标"], r["指标数"], r["题目数"], r["课标编号"], r["学习卡"])
    for r in overview_rows])}

## 3 指标与课标、教材、题目对应

{table(["主题", "指标", "指标描述", "课标", "课标页", "教材小节", "题目数"], [
    (r["主题编号"], r["指标编号"], r["指标描述"], r["课标编号"], f"PDF {r['课标文件页']} / 正文 {r['课标正文页']}", r["教材小节"], r["题目数"])
    for r in indicator_rows])}

## 4 课标条目

{table(["课标", "标题", "PDF页", "正文页", "关联指标", "条目"], [
    (r["课标编号"], r["标题"], r["PDF页"], r["正文页"], r["关联指标"], r["条目"])
    for r in curriculum_rows])}

## 5 教材小节

{table(["小节", "材料", "册别", "章节", "小节名", "教材页", "切片PDF页", "关联指标"], [
    (r["小节编号"], r["材料编号"], r["册别"], r["章节"], r["小节"], r["教材页"], r["切片PDF页"], r["关联指标"])
    for r in textbook_rows])}

## 6 题目归属

54 道题的逐题映射见 `task1_question_map.csv`，字段包括题目编号、主题、指标、题型、满分、评分点、来源与题干。题目只呈现题干与评分点，不附答案，避免把“内容梳理”变成答案册。

## 7 映射规则与边界

- 课标条目只纳入与本主题直接相关的部分；后续学段的乘法公式、因式分解、一元二次方程等不计入。
- 教材本身未标注指标，指标—教材小节为编辑映射，已在 `task1_learning_content.json` 的 `mapping_rules` 中注明。
- 教材印刷页与切片 PDF 页逐条核对，二者同时给出，便于评审回查。
- 题目按“题目与材料”表中的主题、指标字段归属，不按主观印象重新归类。
"""
    write_text(os.path.join(TASK1, "任务1说明.md"), md)
    return {
        "themes": len(themes),
        "indicators": len(indicator_rows),
        "questions": len(question_rows),
        "curriculum": len(curriculum_rows),
        "sections": len(textbook_rows),
    }


def question_detail(kb, records, sid, qid):
    q = kb["questions"][qid]
    rows = [r for r in records if r["学生编号"] == sid and r["材料编号"] == qid]
    rows.sort(key=lambda r: (r["节点编号"], r["模拟提交时间"], int(r["修订版本"] or 0)))
    attempts = []
    for r in rows:
        scores = parse_points(r["评分点得分"])
        points = []
        for p in q["score_points"]:
            got = scores.get(p["id"])
            labels = ["未记录"] if got is None else (
                ["答案正确"] if got >= p["score"] else labels_for(p["description"])
            )
            points.append({
                "评分点编号": p["id"],
                "评分点描述": p["description"],
                "满分": p["score"],
                "得分": got,
                "失分标签": labels,
            })
        attempts.append({
            "记录编号": r["记录编号"],
            "节点编号": r["节点编号"],
            "作答事件编号": r["作答事件编号"],
            "修订版本": r["修订版本"],
            "模拟提交时间": r["模拟提交时间"],
            "评分状态": r["评分状态"],
            "得分": r["得分"],
            "满分": r["满分"],
            "学生最终作答": r["学生最终作答"],
            "解答过程": r["解答过程"],
            "评分点得分": r["评分点得分"],
            "评分点明细": points,
            "数据可用性": r["数据可用性"],
        })
    return {
        "题目编号": qid,
        "题型": q["type"],
        "满分": q["max_score"],
        "题干": q["stem"],
        "主题编号": q["theme_id"],
        "指标编号": q["indicator_id"],
        "作答次数": len(attempts),
        "作答记录": attempts,
    }


def case_record(case, kb, students, records, recommendations):
    sid = case["sid"]
    student = students[sid]
    rec = recommendations["students"][sid]
    details = [question_detail(kb, records, sid, qid) for qid in case["qids"]]
    theme_rows = [{
        "主题编号": tid,
        "主题名称": row["主题名称"],
        "可用记录数": row["可用记录数"],
        "得分率": row["得分率"],
        "记录充分性": row["记录充分性"],
        "可否判断掌握": row["可否判断掌握"],
    } for tid, row in student["分主题"].items()]
    indicator_rows = [{
        "指标编号": iid,
        "指标描述": row["指标描述"],
        "可用记录数": row["可用记录数"],
        "得分": row["得分"],
        "满分": row["满分"],
        "得分率": row["得分率"],
        "是否需关注": row["是否需关注"],
    } for iid, row in student["分指标"].items()]

    suggested = rec["建议"]
    sequence = [{
        "顺序": i + 1,
        "层级": item["层级"],
        "目标指标": item["目标指标"],
        "目标描述": item["目标描述"],
        "题目": [q["材料编号"] for q in item["推荐材料"]["题目"]],
        "教材": [f"{s['材料编号']} P{s['教材页']}" for s in item["推荐材料"]["教材"]],
        "第一步骤": item["实施步骤"][0] if item["实施步骤"] else "",
        "完成标准": item["完成标准"],
    } for i, item in enumerate(suggested)]

    return {
        "案例编号": case["case_id"],
        "学生编号": sid,
        "模拟班级编号": student["模拟班级编号"],
        "案例类型": case["type"],
        "选取理由": case["reason"],
        "数据概况": {
            "记录数": student["记录数"],
            "可用记录数": student["可用记录数"],
            "得分": student["得分"],
            "满分": student["满分"],
            "得分率": student["得分率"],
            "记录充分性": student["记录充分性"],
            "可否判断整体掌握": student["可否判断整体掌握"],
            "摘要": student["摘要"],
        },
        "分主题": theme_rows,
        "分指标": indicator_rows,
        "答题分析": details,
        "学情诊断": case["diagnosis"],
        "教学建议": {
            "建议顺序": sequence,
            "建议明细": suggested,
            "补充观察建议": case["extra_observation"],
        },
    }


def build_task2(kb, students, class_report, quality, records, qrows, prows):
    os.makedirs(TASK2, exist_ok=True)
    recommendations = load_json(os.path.join(DATA_DIR, "recommendations.json"))
    cases = [case_record(c, kb, students, records, recommendations) for c in CASES]

    write_json(os.path.join(TASK2, "task2_class_analysis.json"), class_report)
    write_json(os.path.join(TASK2, "task2_student_analysis.json"), {
        "generated_at": class_report["generated_at"],
        "rule_version": class_report["rule_version"],
        "students": students,
    })
    write_json(os.path.join(TASK2, "task2_data_quality.json"), quality)
    write_json(os.path.join(TASK2, "task2_three_cases.json"), {
        "meta": {
            "task": "任务2 学情分析——三名代表性学生案例",
            "selection": "按“部分得分、表现较好、记录不足”三类各取一名，覆盖 DC01 与 DC02。",
            "note": "案例只使用赛题模拟数据；记录不足不等于未掌握。",
        },
        "cases": cases,
    })
    write_csv(os.path.join(TASK2, "task2_questions.csv"), qrows)
    write_csv(os.path.join(TASK2, "task2_score_points.csv"), prows)
    shutil.copy2(os.path.join(DATA_DIR, "records_normalized.csv"),
                 os.path.join(TASK2, "task2_records_normalized.csv"))
    shutil.copy2(os.path.join(DATA_DIR, "coverage.csv"), os.path.join(TASK2, "task2_coverage.csv"))

    # 统计信息不足主题与低记录指标
    by_theme = defaultdict(list)
    for sid, row in students.items():
        for tid in row["信息不足主题"]:
            by_theme[tid].append(sid)
    low_indicator = defaultdict(list)
    for sid, row in students.items():
        for iid, ind in row["分指标"].items():
            if ind["可用记录数"] < 3:
                low_indicator[iid].append(sid)

    class_rows = []
    for cls, row in class_report["classes"].items():
        class_rows.append((
            cls,
            row["学生数"],
            row["可用记录数"],
            pct(row["得分率"]),
            pct(row["分主题"]["T01"]["得分率"]),
            pct(row["分主题"]["T02"]["得分率"]),
            pct(row["分主题"]["T03"]["得分率"]),
            "、".join(x["指标编号"] for x in row["相对薄弱指标"]),
        ))

    theme_rows = []
    for cls, row in class_report["classes"].items():
        for tid, t in row["分主题"].items():
            theme_rows.append((cls, tid + " " + t["主题名称"], t["可用记录数"], pct(t["得分率"])))

    gap_rows = [(
        g["指标编号"], g["指标描述"], pct(g["DC01得分率"]), pct(g["DC02得分率"]),
        g["差值百分点"], g["可比性"]
    ) for g in class_report["两班指标对比"]]

    weak_rows = []
    for cls, row in class_report["classes"].items():
        for p in row["共性薄弱评分点"][:6]:
            weak_rows.append((cls, p["评分点编号"], p["评分点描述"], p["失败数"], p["评价数"], pct(p["失败率"])))

    issue_rows = [(k, len(v)) for k, v in quality["issues"].items()]
    availability_rows = [(k, v) for k, v in quality["availability_counts"].items()]
    missing_rows = [(tid, "、".join(by_theme.get(tid, [])) or "无") for tid in ("T01", "T02", "T03")]
    low_rows = [(iid, len(v), "、".join(v)) for iid, v in sorted(low_indicator.items())]

    case_rows = [(
        c["案例编号"], c["学生编号"], c["模拟班级编号"], c["案例类型"],
        c["数据概况"]["可用记录数"], pct(c["数据概况"]["得分率"])
    ) for c in cases]

    md = f"""# 任务2 学情分析报告

## 1 数据概况与处理口径

{table(["指标", "数值"], [
    ("学生数", quality["totals"]["学生数"]),
    ("班级数", quality["totals"]["班级数"]),
    ("原始记录数", quality["totals"]["原始记录数"]),
    ("作答事件数", quality["totals"]["作答事件数"]),
    ("当前版本记录数", quality["totals"]["当前版本记录数"]),
    ("题目数", quality["totals"]["题目数"]),
    ("解答题数", quality["totals"]["解答题数"]),
])}

**数据可用性分布**

{table(["数据可用性", "记录数"], availability_rows)}

处理规则：

{chr(10).join("- " + x for x in quality["handling_rules"])}

## 2 班级层面分析

{table(["班级", "学生数", "可用记录", "得分率", "T01", "T02", "T03", "薄弱指标"], class_rows)}

**分主题**

{table(["班级", "主题", "可用记录", "得分率"], theme_rows)}

**两班指标对比（按差值绝对值排序）**

{table(["指标", "描述", "DC01", "DC02", "差值(pp)", "可比性"], gap_rows)}

**共性薄弱评分点（每班前6）**

{table(["班级", "评分点", "描述", "失败数", "评价数", "失败率"], weak_rows)}

## 3 三名代表性学生案例

{table(["案例", "学生", "班级", "类型", "可用记录", "得分率"], case_rows)}

案例的答题证据、诊断与建议见 `task2_three_cases.json` 与 `任务2三案例报告.md`。

## 4 记录不足与暂不能确定的内容

**主题级信息不足（可用记录少于5条）**

{table(["主题", "学生"], missing_rows)}

**指标级初步观察（可用记录少于3条的学生数）**

{table(["指标", "学生数", "学生"], low_rows[:10])}

对上述内容只作初步观察，不写入“未掌握”；先补证据，再判断。

## 5 异常与重复记录

{table(["问题类型", "记录数"], issue_rows)}

- 同一作答事件保留修订版本号最大的记录，其余版本保留在修订轨迹中。
- 得分超出满分、节点与题目/主题不匹配的记录标记为异常，不进入统计。
- 提交晚于节点的记录视为复核/补录，仍可使用，但单独标注。

## 6 与任务成果包的对应

- 班级分析：`task2_class_analysis.json`
- 学生分析：`task2_student_analysis.json`
- 三案例：`task2_three_cases.json`
- 题目/评分点：`task2_questions.csv`、`task2_score_points.csv`
- 标准化记录与覆盖：`task2_records_normalized.csv`、`task2_coverage.csv`
- 数据体检：`task2_data_quality.json`
"""
    write_text(os.path.join(TASK2, "任务2学情分析报告.md"), md)

    case_md = ["# 任务2 三案例报告", ""]
    for c in cases:
        case_md.append(f"## {c['案例编号']} {c['学生编号']}（{c['模拟班级编号']}）· {c['案例类型']}")
        case_md.append("")
        case_md.append(f"**选取理由**：{c['选取理由']}")
        case_md.append("")
        case_md.append("### 1 数据概况")
        case_md.append(table(["项目", "数值"], [
            ("记录数", c["数据概况"]["记录数"]),
            ("可用记录数", c["数据概况"]["可用记录数"]),
            ("得分/满分", f"{c['数据概况']['得分']}/{c['数据概况']['满分']}"),
            ("得分率", pct(c["数据概况"]["得分率"])),
            ("记录充分性", c["数据概况"]["记录充分性"]),
            ("可否判断整体掌握", "是" if c["数据概况"]["可否判断整体掌握"] else "否"),
        ]))
        case_md.append("")
        case_md.append("**分主题**")
        case_md.append(table(["主题", "可用记录", "得分率", "记录充分性", "可否判断"], [
            (r["主题编号"] + " " + r["主题名称"], r["可用记录数"], pct(r["得分率"]), r["记录充分性"],
             "是" if r["可否判断掌握"] else "否") for r in c["分主题"]
        ]))
        case_md.append("")
        case_md.append("### 2 答题分析")
        for d in c["答题分析"]:
            case_md.append(f"#### {d['题目编号']}（{d['题型']}，{d['满分']}分，{d['指标编号']}）")
            case_md.append("")
            case_md.append(f"题干：{d['题干']}")
            case_md.append("")
            rows = []
            for a in d["作答记录"]:
                rows.append((
                    a["记录编号"], a["节点编号"], a["得分"], a["满分"],
                    a["学生最终作答"], a["评分点得分"],
                    "；".join(f"{p['评分点编号']}：{p['得分']}/{p['满分']}（{'、'.join(p['失分标签'])}）"
                             for p in a["评分点明细"]),
                ))
            case_md.append(table(["记录", "节点", "得分", "满分", "实际作答", "评分点得分", "分点判定"], rows))
            case_md.append("")
            for a in d["作答记录"]:
                if a["解答过程"]:
                    text = a["解答过程"].replace("\n", "；").replace("。；", "；").replace("；；", "；")
                    case_md.append(f"- {a['记录编号']} 解答过程：{text}")
            case_md.append("")
        case_md.append("### 3 学情诊断")
        case_md.append("")
        case_md.append(f"**总体判断**：{c['学情诊断']['总体判断']}")
        case_md.append("")
        case_md.append("**优势**")
        case_md.append("")
        case_md.append("\n".join("- " + x for x in c["学情诊断"]["优势"]))
        case_md.append("")
        case_md.append("**关键问题**")
        case_md.append("")
        case_md.append("\n".join("- " + x for x in c["学情诊断"]["关键问题"]))
        case_md.append("")
        case_md.append("**待观察**")
        case_md.append("")
        case_md.append("\n".join("- " + x for x in c["学情诊断"]["待观察"]))
        case_md.append("")
        case_md.append("### 4 教学建议")
        case_md.append("")
        case_md.append(table(["顺序", "层级", "目标", "题目", "教材", "完成标准"], [
            (s["顺序"], s["层级"], f"{s['目标指标']} {s['目标描述']}", "、".join(s["题目"]),
             "；".join(s["教材"]), s["完成标准"]) for s in c["教学建议"]["建议顺序"]
        ]))
        case_md.append("")
        case_md.append("**补充观察建议**")
        case_md.append("")
        case_md.append("\n".join("- " + x for x in c["教学建议"]["补充观察建议"]))
        case_md.append("")
        case_md.append("> 提示语只引导思考，不直接给出答案；建议按“补充诊断→基础巩固→关键突破→迁移应用→自主检验”的顺序使用，可按完成情况跳过。")
        case_md.append("")
    write_text(os.path.join(TASK2, "任务2三案例报告.md"), "\n".join(case_md))

    return {"cases": len(cases), "students": len(students)}


def build_task3(recs):
    os.makedirs(TASK3, exist_ok=True)
    shutil.copy2(os.path.join(DATA_DIR, "recommendations.json"),
                 os.path.join(TASK3, "task3_recommendations.json"))
    shutil.copy2(os.path.join(DATA_DIR, "recommendations_index.csv"),
                 os.path.join(TASK3, "task3_recommendation_index.csv"))
    write_json(os.path.join(TASK3, "task3_class_plans.json"), {
        "meta": {
            "task": "任务3 个性化建议——班级教学干预",
            "rule": "按班级筛选评分点，优先100%失败项，再按失败数×失败率排序；最多5条本班干预+1条两班共性。",
        },
        "classes": recs["classes"],
    })

    cases = []
    for case in CASES:
        sid = case["sid"]
        student_rec = recs["students"][sid]
        cases.append({
            "学生编号": sid,
            "案例类型": case["type"],
            "摘要": student_rec["摘要"],
            "建议顺序": [f"{i + 1}. {item['层级']}：{item['目标指标']} {item['目标描述']}"
                        for i, item in enumerate(student_rec["建议"])],
            "建议明细": student_rec["建议"],
            "补充观察": student_rec.get("补充观察", []),
            "补充观察建议": case["extra_observation"],
            "后续调整条件": [
                "完成标准达到后再进入下一层；未达到则回到对应评分点复述与重做。",
                "若同一评分点在后续任务中失败率仍高于30%，保留该层并增加一次变式练习。",
                "若补充诊断后可用记录达到5条以上，再重新判断掌握程度。",
            ],
        })
    write_json(os.path.join(TASK3, "task3_three_cases_advice.json"), {
        "meta": {
            "task": "任务3 个性化建议——三名案例",
            "note": "建议均绑定数据证据、课标、教材页码、题目编号与学习卡；引导提示不给答案。",
        },
        "cases": cases,
    })

    class_rows = []
    for cls, plan in recs["classes"].items():
        class_rows.append({
            "班级": cls,
            "摘要": plan["摘要"].replace(f"{cls}：", "", 1),
            "优先指标": "、".join(x["指标编号"] for x in plan["优先指标"]),
            "干预数": len(plan["共性干预"]),
            "补诊断": "、".join(plan["分层安排"]["补诊断"]),
            "夯实层": "、".join(plan["分层安排"]["夯实层"]),
            "提升层": "、".join(plan["分层安排"]["提升层"]),
            "拓展层": "、".join(plan["分层安排"]["拓展层"]),
        })

    intervention_rows = []
    for cls, plan in recs["classes"].items():
        for item in plan["共性干预"]:
            intervention_rows.append((
                cls, item["范围"], item["问题"], item["失败情况"], item["关联指标"],
                "、".join(item["变式练习"]), item["完成标准"]
            ))

    case_rows = []
    obs_rows = []
    for case in cases:
        first = case["建议明细"][0] if case["建议明细"] else None
        case_rows.append((
            case["学生编号"], case["案例类型"],
            " → ".join(x.split("：")[0].replace(f"{i + 1}. ", "") for i, x in enumerate(case["建议顺序"])) if case["建议顺序"] else "—",
            f"{first['目标指标']} {first['目标描述']}" if first else "—",
            "；".join(q["材料编号"] for item in case["建议明细"] for q in item["推荐材料"]["题目"]),
        ))
        obs = case.get("补充观察", [])
        obs_rows.append((
            case["学生编号"],
            "；".join(f"{x['指标编号']}（{x['可用记录数']}条）" for x in obs) or "无",
            "先补1—2道诊断题，再判断掌握程度" if obs else "—",
        ))

    md = f"""# 任务3 个性化建议

## 1 分层规则

建议按以下顺序组织，可根据已完成情况跳过：

1. **补充诊断**：目标主题可用记录不足时，先补证据，不判“未掌握”。
2. **基础巩固**：针对薄弱指标的基本概念与规范步骤。
3. **关键突破**：针对高频失分步骤做专项修正。
4. **迁移应用**：换情境、换问法，检查能否独立迁移。
5. **自主检验 / 拓展提升**：用不同主题的题目自检；高表现者做变式与解释任务。

每条建议都给出数据证据、课标条目、教材页码、题目编号与学习卡编号；引导提示只提问，不给答案。

## 2 班级层面

{table(["班级", "摘要", "优先指标", "干预数", "补诊断", "夯实层", "提升层", "拓展层"], [
    (r["班级"], r["摘要"], r["优先指标"], r["干预数"], r["补诊断"], r["夯实层"], r["提升层"], r["拓展层"])
    for r in class_rows])}

**共性干预**

{table(["班级", "范围", "问题", "失败情况", "指标", "变式练习", "完成标准"], intervention_rows)}

## 3 三名案例建议

{table(["学生", "案例类型", "建议顺序", "首层目标", "题目"], case_rows)}

三名案例的完整建议（含实施步骤、引导提示、教材页码、完成标准）见 `task3_three_cases_advice.json`。

**补充观察（可用记录少于3条的指标）**

{table(["学生", "记录不足指标", "处理方式"], obs_rows)}

对上述指标只作初步观察，不判“未掌握”；先补诊断题或在下一次作业中保留完整过程，再判断掌握程度。

## 4 后续调整条件

- 完成标准达到后再进入下一层；未达到则回到对应评分点复述与重做。
- 同一评分点在后续任务中失败率仍高于30%时，保留该层并增加一次变式练习。
- 补充诊断后可用记录达到5条以上，再重新判断掌握程度；不足5条仍只作初步观察。
- 高表现学生的拓展任务不以重复刷题替代，优先“解释、变式、开放情境”。

## 5 与成果包的对应

- 全班建议：`task3_recommendations.json`、`task3_recommendation_index.csv`
- 班级方案：`task3_class_plans.json`
- 三名案例建议：`task3_three_cases_advice.json`
"""
    write_text(os.path.join(TASK3, "任务3建议说明.md"), md)

    return {
        "students": len(recs["students"]),
        "items": sum(len(x["建议"]) for x in recs["students"].values()),
        "classes": len(recs["classes"]),
    }


def field_rows():
    rows = []

    def add(file, field, dtype, meaning, example=""):
        rows.append({"文件": file, "字段": field, "类型": dtype, "含义": meaning, "示例": example})

    add("任务1/task1_learning_content.json", "meta", "object", "任务说明、数据来源与映射规则", "")
    add("任务1/task1_learning_content.json", "themes[].theme_id", "string", "主题编号（T01/T02/T03）", "T01")
    add("任务1/task1_learning_content.json", "themes[].name", "string", "主题名称", "代数式与整式运算")
    add("任务1/task1_learning_content.json", "themes[].goal", "string", "主题学习目标", "")
    add("任务1/task1_learning_content.json", "themes[].indicators[]", "object", "指标及其课标/教材/题目映射", "")
    add("任务1/task1_learning_content.json", "indicators[].indicator_id", "string", "指标编号", "T01I1")
    add("任务1/task1_learning_content.json", "indicators[].description", "string", "指标描述", "表示数量关系并代入求值")
    add("任务1/task1_learning_content.json", "indicators[].curriculum_code", "string", "对应课标编号", "CR01")
    add("任务1/task1_learning_content.json", "indicators[].textbook_sections[]", "array", "对应教材小节（材料、页码、PDF页）", "")
    add("任务1/task1_learning_content.json", "indicators[].question_ids[]", "array", "对应题目编号", "Q014")
    add("任务1/task1_learning_content.json", "themes[].learning_cards", "array", "对应学习卡编号", "L01")

    add("任务1/task1_theme_overview.csv", "主题编号/主题名称", "string", "主题标识与名称", "T01")
    add("任务1/task1_theme_overview.csv", "学习目标", "string", "主题目标", "")
    add("任务1/task1_theme_overview.csv", "指标数/题目数", "integer", "该主题的指标与题目数量", "3/18")
    add("任务1/task1_theme_overview.csv", "课标编号/教材材料/学习卡", "string", "对应资源编号", "CR01")

    add("任务1/task1_indicator_map.csv", "指标编号/指标描述", "string", "指标标识与描述", "T01I1")
    add("任务1/task1_indicator_map.csv", "课标编号/课标标题/课标文件页/课标正文页", "string/integer", "课标定位", "CR01/62/55")
    add("任务1/task1_indicator_map.csv", "教材页码范围/教材小节", "string", "教材印刷页与小节名称", "69—77")
    add("任务1/task1_indicator_map.csv", "题目编号/题目数", "string/integer", "该指标对应题目", "Q014")
    add("任务1/task1_indicator_map.csv", "学习卡", "string", "对应学习卡编号", "L01")

    add("任务1/task1_question_map.csv", "题目编号", "string", "题目唯一编号", "Q014")
    add("任务1/task1_question_map.csv", "主题编号/指标编号", "string", "题目归属", "T01/T01I1")
    add("任务1/task1_question_map.csv", "题型/满分/评分点数", "string/integer", "题目属性", "解答题/3/3")
    add("任务1/task1_question_map.csv", "评分点", "string", "评分点编号、描述与分值", "Q014P1 表示女生人数（1分）")
    add("任务1/task1_question_map.csv", "来源/题干", "string", "题目来源与题干（不含答案）", "赛事新编")
    add("任务1/task1_curriculum_map.csv", "课标编号/标题/领域", "string", "课标条目元数据", "CR01/代数式/数与代数")
    add("任务1/task1_curriculum_map.csv", "PDF页/正文页", "integer", "课标文件页与正文页", "62/55")
    add("任务1/task1_curriculum_map.csv", "关联指标/条目/选取说明", "string", "对应指标、条目原文与取舍说明", "")
    add("任务1/task1_textbook_map.csv", "小节编号/材料编号/材料名称", "string", "教材小节与材料标识", "B05-3.1/B05")
    add("任务1/task1_textbook_map.csv", "册别/章节/小节/教材页/切片PDF页", "string", "教材定位", "七年级上册/69—77/2—10")
    add("任务1/task1_textbook_map.csv", "关联指标", "string", "该小节关联的指标", "T01I1")

    add("任务2/task2_class_analysis.json", "classes.{班级}.学生数/可用记录数", "integer", "班级规模与有效记录", "21/420")
    add("任务2/task2_class_analysis.json", "classes.{班级}.得分率", "number", "0—1，仅用已评分可用记录", "0.5871")
    add("任务2/task2_class_analysis.json", "classes.{班级}.分主题", "object", "T01/T02/T03 的可用记录与得分率", "")
    add("任务2/task2_class_analysis.json", "classes.{班级}.分指标", "object", "9个指标的可用记录与得分率", "")
    add("任务2/task2_class_analysis.json", "classes.{班级}.相对薄弱指标", "array", "可用记录≥3且得分率<50%的指标", "")
    add("任务2/task2_class_analysis.json", "classes.{班级}.共性薄弱评分点", "array", "按失败数排序的评分点", "")
    add("任务2/task2_class_analysis.json", "两班指标对比", "array", "DC01与DC02指标差值（百分点）及可比性", "")
    add("任务2/task2_class_analysis.json", "典型案例候选", "object", "按表现分类的案例候选名单", "")

    add("任务2/task2_student_analysis.json", "students.{学生}.记录数/可用记录数", "integer", "原始记录与可用记录", "21")
    add("任务2/task2_student_analysis.json", "students.{学生}.得分/满分/得分率", "number", "个人有效记录得分与得分率", "48.6%")
    add("任务2/task2_student_analysis.json", "students.{学生}.记录充分性", "string", "无记录/不足/偏少/可分析", "可分析")
    add("任务2/task2_student_analysis.json", "students.{学生}.分主题/分指标", "object", "按主题与指标的表现", "")
    add("任务2/task2_student_analysis.json", "students.{学生}.主要失分步骤", "array", "失分标签及次数", "")
    add("任务2/task2_student_analysis.json", "students.{学生}.需关注指标", "array", "可用记录≥3且得分率<60%的指标", "")
    add("任务2/task2_student_analysis.json", "students.{学生}.信息不足主题", "array", "可用记录<5的主题，不判掌握", "T03")
    add("任务2/task2_student_analysis.json", "students.{学生}.证据", "array", "记录编号、题目、评分点、得分与失分标签", "")

    add("任务2/task2_questions.csv", "材料编号/主题编号/指标编号", "string", "题目与归属", "Q014/T01/T01I1")
    add("任务2/task2_questions.csv", "班级", "string", "DC01/DC02/全体", "DC01")
    add("任务2/task2_questions.csv", "可用记录数/得分/满分合计/得分率", "number", "该题在该班的统计", "0.586")
    add("任务2/task2_score_points.csv", "评分点编号/评分点描述", "string", "评分点标识与描述", "Q014P2")
    add("任务2/task2_score_points.csv", "评价记录数/失败数/失败率", "number", "该评分点的评分记录与失败情况", "5/5/1.0")
    add("任务2/task2_three_cases.json", "cases[].学生编号/案例类型", "string", "三名案例的标识与类型", "D01/部分得分")
    add("任务2/task2_three_cases.json", "cases[].答题分析[]", "array", "题干、作答、评分点明细与记录编号", "")
    add("任务2/task2_three_cases.json", "cases[].学情诊断", "object", "总体判断、优势、关键问题、待观察", "")
    add("任务2/task2_data_quality.json", "totals/availability_counts", "object", "数据总量与可用性分布", "787可用")
    add("任务2/task2_data_quality.json", "issues", "object", "异常、重复、节点不匹配等记录", "")
    add("任务2/task2_data_quality.json", "handling_rules", "array", "缺失、异常、重复的处理口径", "")
    add("任务2/task2_records_normalized.csv", "记录编号/学生编号/材料编号", "string", "标准化记录主键与关联", "DR0005/D01/Q014")
    add("任务2/task2_records_normalized.csv", "作答事件编号/修订版本", "string", "去重与版本控制字段", "D01-N01-Q014/1")
    add("任务2/task2_records_normalized.csv", "得分/满分/评分点得分", "string/number", "得分与分点评分", "0/3/Q014P1=0")
    add("任务2/task2_records_normalized.csv", "数据可用性/质量问题", "string", "可用性判定与问题标签", "已评分-可用于分析")
    add("任务2/task2_coverage.csv", "覆盖统计字段", "string/number", "主题、题目与班级的记录覆盖", "")

    add("任务3/task3_recommendations.json", "students.{学生}.摘要", "string", "学生建议摘要", "")
    add("任务3/task3_recommendations.json", "students.{学生}.建议[].层级", "string", "补充诊断/基础巩固/关键突破/迁移应用/自主检验/拓展提升", "基础巩固")
    add("任务3/task3_recommendations.json", "建议[].目标指标/目标描述", "string", "本条建议针对的指标", "T01I1")
    add("任务3/task3_recommendations.json", "建议[].依据.数据证据[]", "array", "记录编号、题目、评分点与表现", "")
    add("任务3/task3_recommendations.json", "建议[].依据.课标/教材", "object", "课标条目与教材页码", "CR01/B05 P69—77")
    add("任务3/task3_recommendations.json", "建议[].推荐材料.题目[]", "array", "推荐题目编号、题干、当前表现（不含答案）", "Q014")
    add("任务3/task3_recommendations.json", "建议[].实施步骤/引导提示/完成标准", "array/string", "执行步骤、只提问的提示与达成标准", "")
    add("任务3/task3_recommendations.json", "students.{学生}.补充观察[]", "array", "可用记录少于3条的指标及补证据建议", "")
    add("任务3/task3_recommendation_index.csv", "学生编号/班级/层级/目标指标", "string", "建议索引", "D01/DC01/基础巩固/T01I1")
    add("任务3/task3_recommendation_index.csv", "教材材料/题目/学习卡/完成标准", "string", "建议关联材料", "")
    add("任务3/task3_class_plans.json", "classes.{班级}.优先指标", "array", "班级相对薄弱指标", "T01I1/T03I3")
    add("任务3/task3_class_plans.json", "classes.{班级}.共性干预[]", "array", "班级共性问题、依据、教学动作与变式练习", "")
    add("任务3/task3_class_plans.json", "classes.{班级}.分层安排", "object", "补诊断/夯实层/提升层/拓展层名单", "")
    add("任务3/task3_class_plans.json", "classes.{班级}.复查安排", "array", "下一次复查重点", "")
    add("任务3/task3_three_cases_advice.json", "cases[].建议明细[]", "array", "三名案例的完整建议", "")
    add("任务3/task3_three_cases_advice.json", "cases[].后续调整条件", "array", "进入下一层或保留当前层的条件", "")

    return rows


def build_docs(recs):
    field_path = os.path.join(OUT, "字段说明.csv")
    rows = field_rows()
    write_csv(field_path, rows)

    lines = ["# 字段说明", "",
             "本成果包同时提供 JSON 与 CSV。JSON 便于保留嵌套结构，CSV 便于直接统计与复核。", "",
             table(["文件", "字段", "类型", "含义", "示例"], [
                 (r["文件"], r["字段"], r["类型"], r["含义"], r["示例"]) for r in rows
             ]), "",
             "## 通用约定", "",
             "- 得分率取值 0—1；CSV 中同时提供百分数展示字段时以 `%` 结尾。",
             "- 空值 `null` 表示无可用记录或无法计算，不等同于 0 分。",
             "- “可用记录”指 `数据可用性=已评分-可用于分析` 的记录。",
             "- 待评分、未作答、异常记录不进入得分率分母。",
             "- 题目推荐与题干不含答案；引导提示只提问。",
             ""]
    write_text(os.path.join(OUT, "字段说明.md"), "\n".join(lines))

    total_items = sum(len(x["建议"]) for x in recs["students"].values())
    readme = f"""# 三任务成果包

本成果包对应“智慧学伴 七年级数学”赛题的三项任务，包含可机读结果（JSON/CSV）、字段说明与三案例报告。

## 1 目录

- `任务1_学习内容梳理/`：3个主题、9个指标、54道题的课标/教材/题目映射。
- `任务2_学情分析/`：班级分析、40名学生分析、数据体检、三名代表性学生案例。
- `任务3_个性化建议/`：40名学生共 {total_items} 条分层建议、2个班级教学干预方案、三案例建议。
- `字段说明.csv` / `字段说明.md`：所有 JSON/CSV 字段的类型、含义与示例。
- `00_成果包清单.csv`：文件清单与字节数。

## 2 关键数据

- 学生 40 人（DC01 21 人、DC02 19 人）；原始记录 806 条，作答事件 799 条，当前版本 799 条。
- 已评分 790 条，未作答 5 条，待评分 4 条；可用记录 787 条；异常 3 条。
- DC01 得分率 58.7%，DC02 得分率 55.0%。
- 三案例：D01（DC01，部分得分）、D29（DC02，表现较好）、D32（DC02，记录不足/T03无记录）。

## 3 任务对应

| 赛题要求 | 成果包文件 |
|---|---|
| 任务1 梳理学习内容与要求，标明课标、教材、题目 | `任务1_学习内容梳理/task1_learning_content.json`、5张CSV、`任务1说明.md` |
| 任务2 分析作答、得分、步骤，说明缺失/异常/重复处理 | `任务2_学情分析/task2_class_analysis.json`、`task2_student_analysis.json`、`task2_data_quality.json`、4张CSV、`任务2学情分析报告.md` |
| 任务2 三名代表性学生案例 | `task2_three_cases.json`、`任务2三案例报告.md` |
| 任务3 具体练习、讲解、补充观察建议 | `任务3_个性化建议/task3_recommendations.json`、`task3_recommendation_index.csv`、`task3_class_plans.json`、`task3_three_cases_advice.json` |
| 字段说明 | `字段说明.csv`、`字段说明.md` |
| 可复现代码 | 项目目录：`kb_builder.py`、`data_pipeline.py`、`analyzer.py`、`advisor.py`、`app.py`、`export_results.py` |

## 4 数据来源与生成链路

```
赛题Excel/PDF
  → kb_builder.py        生成 kb/kb.json（课标、教材、题目、学习卡、映射）
  → data_pipeline.py     生成 data/records_normalized.csv、data_quality.json、coverage.csv
  → analyzer.py          生成 analysis_individual.json、analysis_class.json、两张统计CSV
  → advisor.py           生成 recommendations.json、recommendations_index.csv
  → export_results.py    生成 三任务成果包（本目录）
  → app.py               对话式展示（Streamlit）
```

重新生成：

```powershell
cd "chap01\\intelligent study company"
..\\.venv\\Scripts\\python.exe kb_builder.py
..\\.venv\\Scripts\\python.exe data_pipeline.py
..\\.venv\\Scripts\\python.exe analyzer.py
..\\.venv\\Scripts\\python.exe advisor.py
..\\.venv\\Scripts\\python.exe export_results.py
```

## 5 口径与边界

- 得分率只使用“已评分-可用于分析”的记录；待评分、未作答、异常记录不计入。
- 同一作答事件保留修订版本号最大的记录。
- 主题可用记录少于5条标注“信息不足”，不判“未掌握”；指标少于3条只作初步观察。
- 题目推荐与题干不含答案；引导提示只提问，不直接给出结果。
- 学生与作答记录均为赛题模拟数据，不含真实个人信息。
"""
    write_text(os.path.join(OUT, "README.md"), readme)

    manifest = []
    for root, _, files in os.walk(OUT):
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, OUT).replace("\\", "/")
            manifest.append({
                "相对路径": rel,
                "类型": os.path.splitext(name)[1].lstrip("."),
                "字节数": os.path.getsize(path),
            })
    write_csv(os.path.join(OUT, "00_成果包清单.csv"), manifest)


def main():
    os.makedirs(OUT, exist_ok=True)
    kb = load_json(KB_PATH)
    students = load_json(os.path.join(DATA_DIR, "analysis_individual.json"))["students"]
    class_report = load_json(os.path.join(DATA_DIR, "analysis_class.json"))
    quality = load_json(os.path.join(DATA_DIR, "data_quality.json"))
    recs = load_json(os.path.join(DATA_DIR, "recommendations.json"))
    records = load_csv(os.path.join(DATA_DIR, "records_normalized.csv"))
    qrows = load_csv(os.path.join(DATA_DIR, "analysis_questions.csv"))
    prows = load_csv(os.path.join(DATA_DIR, "analysis_score_points.csv"))

    t1 = build_task1(kb)
    t2 = build_task2(kb, students, class_report, quality, records, qrows, prows)
    t3 = build_task3(recs)
    build_docs(recs)

    print(f"输出目录：{OUT}")
    print(f"任务1：{t1}")
    print(f"任务2：{t2}")
    print(f"任务3：{t3}")


if __name__ == "__main__":
    main()
