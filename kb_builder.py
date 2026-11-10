# -*- coding: utf-8 -*-
"""构建“智慧学伴”知识库。

输入：mydata/ 下的题目与材料.xlsx、模拟学情数据索引.xlsx
输出：kb/kb.json（主题-指标-课标-教材-题目-学习卡 的结构化索引）

所有结论均有出处：课标条目给出文件页/正文页，教材条目给出切片编号与印刷页范围。
"""
import json
import os
import re
import sys
from datetime import datetime

import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "mydata")
OUT_DIR = os.path.join(BASE, "kb")

# 课标条目（摘自《义务教育数学课程标准（2022年版）》“四、课程内容”）
# CR01 见 PDF 第62页 / 正文第55页；CR02、CR03 见 PDF 第63页 / 正文第56页。
CURRICULUM = {
    "CR01": {
        "code": "CR01",
        "title": "代数式",
        "domain": "数与代数",
        "pdf_page": 62,
        "print_page": 55,
        "items": [
            {"no": "①", "text": "借助现实情境了解代数式，进一步理解用字母表示数的意义。"},
            {"no": "②", "text": "能分析具体问题中的简单数量关系，并用代数式表示；能根据特定的问题查阅资料，找到所需的公式。"},
            {"no": "③", "text": "会把具体数代入代数式进行计算。"},
            {"no": "⑤", "text": "理解整式的概念，掌握合并同类项和去括号的法则；能进行简单的整式加减运算。"},
        ],
        "selection_note": "①—⑤为七年级代数式与整式加减的直接依据；⑥乘法公式、⑦因式分解属后续学段，不计入本主题范围。",
    },
    "CR02": {
        "code": "CR02",
        "title": "方程与方程组",
        "domain": "数与代数",
        "pdf_page": 63,
        "print_page": 56,
        "items": [
            {"no": "①", "text": "能根据现实情境理解方程的意义，能针对具体问题列出方程；理解方程解的意义，经历估计方程解的过程。"},
            {"no": "②", "text": "掌握等式的基本性质；能解一元一次方程和可化为一元一次方程的分式方程。"},
            {"no": "③", "text": "掌握消元法，能解二元一次方程组。"},
            {"no": "⑧", "text": "能根据具体问题的实际意义，检验方程解的合理性。"},
        ],
        "selection_note": "①—③、⑧为七年级方程与方程组的直接依据；④三元一次方程组为选学，⑤—⑦为一元二次方程，不计入本主题范围。",
    },
    "CR03": {
        "code": "CR03",
        "title": "不等式与不等式组",
        "domain": "数与代数",
        "pdf_page": 63,
        "print_page": 56,
        "items": [
            {"no": "①", "text": "结合具体问题，了解不等式的意义，探索不等式的基本性质。"},
            {"no": "②", "text": "能解数字系数的一元一次不等式，并能在数轴上表示出解集；会用数轴确定两个一元一次不等式组成的不等式组的解集。"},
            {"no": "③", "text": "能根据具体问题中的数量关系，列出一元一次不等式，解决简单的问题。"},
        ],
        "selection_note": "三条均为七年级不等式与不等式组的直接依据。",
    },
}

# 教材切片：编号、册别、章、印刷页范围、PDF 页范围（已逐页核对切片页码与字段说明一致）
TEXTBOOK_SECTIONS = [
    {"id": "B05-3.1", "material_id": "B05", "volume": "七年级上册", "chapter": "第三章 代数式",
     "section": "3.1 列代数式表示数量关系", "pages": "69—77", "pdf_pages": "2—10"},
    {"id": "B05-3.2", "material_id": "B05", "volume": "七年级上册", "chapter": "第三章 代数式",
     "section": "3.2 代数式的值", "pages": "79—85", "pdf_pages": "12—18"},
    {"id": "B05-4.1", "material_id": "B05", "volume": "七年级上册", "chapter": "第四章 整式的加减",
     "section": "4.1 整式", "pages": "89—94", "pdf_pages": "22—27"},
    {"id": "B05-4.2", "material_id": "B05", "volume": "七年级上册", "chapter": "第四章 整式的加减",
     "section": "4.2 整式的加法与减法（合并同类项、去括号）", "pages": "95—101", "pdf_pages": "28—34"},
    {"id": "B06-5.1", "material_id": "B06", "volume": "七年级上册", "chapter": "第五章 一元一次方程",
     "section": "5.1 方程", "pages": "111—119", "pdf_pages": "2—10"},
    {"id": "B06-5.2", "material_id": "B06", "volume": "七年级上册", "chapter": "第五章 一元一次方程",
     "section": "5.2 解一元一次方程（合并同类项、移项、去括号、去分母）", "pages": "120—131", "pdf_pages": "11—22"},
    {"id": "B06-5.3", "material_id": "B06", "volume": "七年级上册", "chapter": "第五章 一元一次方程",
     "section": "5.3 实际问题与一元一次方程", "pages": "133—142", "pdf_pages": "24—33"},
    {"id": "B06-10.1", "material_id": "B06", "volume": "七年级下册", "chapter": "第十章 二元一次方程组",
     "section": "10.1 二元一次方程组的概念", "pages": "88—90", "pdf_pages": "41—43"},
    {"id": "B06-10.2", "material_id": "B06", "volume": "七年级下册", "chapter": "第十章 二元一次方程组",
     "section": "10.2 消元——解二元一次方程组（代入法、加减法）", "pages": "91—99", "pdf_pages": "44—52"},
    {"id": "B06-10.3", "material_id": "B06", "volume": "七年级下册", "chapter": "第十章 二元一次方程组",
     "section": "10.3 实际问题与二元一次方程组", "pages": "101—105", "pdf_pages": "54—58"},
    {"id": "B02-11.1", "material_id": "B02", "volume": "七年级下册", "chapter": "第十一章 不等式与不等式组",
     "section": "11.1 不等式（性质与解集）", "pages": "121—130", "pdf_pages": "2—11"},
    {"id": "B02-11.2", "material_id": "B02", "volume": "七年级下册", "chapter": "第十一章 不等式与不等式组",
     "section": "11.2 一元一次不等式", "pages": "131—137", "pdf_pages": "12—18"},
    {"id": "B02-11.3", "material_id": "B02", "volume": "七年级下册", "chapter": "第十一章 不等式与不等式组",
     "section": "11.3 一元一次不等式组", "pages": "138—141", "pdf_pages": "19—22"},
]

# 指标 → 教材小节（编辑映射，用于“学习内容梳理”和“建议出处”）
INDICATOR_SECTIONS = {
    "T01I1": ["B05-3.1", "B05-3.2"],
    "T01I2": ["B05-4.1", "B05-4.2"],
    "T01I3": ["B05-3.1", "B05-3.2", "B05-4.2"],
    "T02I1": ["B06-5.1", "B06-5.2"],
    "T02I2": ["B06-10.1", "B06-10.2"],
    "T02I3": ["B06-5.3", "B06-10.3"],
    "T03I1": ["B02-11.1", "B02-11.2"],
    "T03I2": ["B02-11.3"],
    "T03I3": ["B02-11.2", "B02-11.3"],
}

TEXTBOOK_TITLES = {
    "B01": "七年级下册 第八章 实数",
    "B02": "七年级下册 第十一章 不等式与不等式组",
    "B03": "七年级下册 第十二章 数据的收集、整理与描述",
    "B04": "七年级上册 第六章 几何图形初步",
    "B05": "七年级上册 第三章 代数式；第四章 整式的加减",
    "B06": "七年级上册 第五章 一元一次方程；七年级下册 第十章 二元一次方程组",
    "B07": "七年级上册 第二章 有理数的运算",
    "B08": "七年级下册 第七章 相交线与平行线",
}


def read_rows(filename, sheet=None):
    path = os.path.join(DATA_DIR, filename)
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], row)) for row in rows[1:] if row and row[0] is not None]


def parse_score_points(text):
    points = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(Q\d+P\d)\s+(.*?)\s*(\d+)分$", line)
        if m:
            points.append({"id": m.group(1), "description": m.group(2).strip(), "score": int(m.group(3))})
    return points


def build():
    q_rows = read_rows("题目与材料.xlsx")
    req_rows = read_rows("模拟学情数据索引.xlsx", "课程要求")

    questions, cards, textbooks = {}, {}, {}
    for row in q_rows:
        mid = str(row["材料编号"]).strip()
        mtype = str(row.get("材料类型") or "").strip()
        if mtype == "题目":
            questions[mid] = {
                "material_id": mid,
                "theme_id": str(row["主题编号"]).strip(),
                "type": str(row.get("题型") or "").strip(),
                "stem": str(row.get("题干或内容") or "").strip(),
                "options": [o.strip() for o in str(row.get("选项") or "").splitlines() if o.strip()],
                "answer": str(row.get("参考答案") or "").strip(),
                "analysis": str(row.get("参考解析") or "").strip(),
                "max_score": int(row["满分"]),
                "score_points": parse_score_points(row.get("评分点")),
                "indicator_id": str(row.get("指标编号") or "").strip(),
                "source": str(row.get("来源或资料文件") or "").strip(),
            }
        elif mtype == "学习卡":
            cards[mid] = {
                "material_id": mid,
                "theme_id": str(row["主题编号"]).strip(),
                "content": str(row.get("题干或内容") or "").strip(),
                "indicator_ids": [x.strip() for x in str(row.get("指标编号") or "").split("、") if x.strip()],
                "source": str(row.get("来源或资料文件") or "").strip(),
            }
        elif mtype == "教材":
            textbooks[mid] = {
                "material_id": mid,
                "title": str(row.get("题干或内容") or "").strip(),
                "source": str(row.get("来源或资料文件") or "").strip(),
            }

    # 主题与指标来自官方“课程要求”表
    themes = {}
    for row in req_rows:
        tid = str(row["主题编号"]).strip()
        theme = themes.setdefault(tid, {
            "theme_id": tid,
            "name": str(row["主题"]).strip(),
            "goal": str(row["主题目标"]).strip(),
            "indicators": [],
        })
        iid = str(row["指标编号"]).strip()
        if iid and iid not in [i["indicator_id"] for i in theme["indicators"]]:
            theme["indicators"].append({
                "indicator_id": iid,
                "description": str(row["观察指标"]).strip(),
                "curriculum_code": str(row["课标整理编号"]).strip(),
                "curriculum_pages": str(row["课标文件页／正文页"]).strip(),
                "textbook_pages": str(row["教材正文页"]).strip(),
                "textbook_sections": [],
                "question_ids": [],
                "learning_cards": [],
            })

    # 教材小节挂到指标
    section_by_id = {s["id"]: s for s in TEXTBOOK_SECTIONS}
    for theme in themes.values():
        for ind in theme["indicators"]:
            ind["textbook_sections"] = [section_by_id[sid] for sid in INDICATOR_SECTIONS.get(ind["indicator_id"], [])]
            ind["question_ids"] = sorted(q for q, v in questions.items() if v["indicator_id"] == ind["indicator_id"])

    # 题目、学习卡挂到主题
    for tid, theme in themes.items():
        theme["question_ids"] = sorted(q for q, v in questions.items() if v["theme_id"] == tid)
        theme["learning_cards"] = sorted(c for c, v in cards.items() if v["theme_id"] == tid)
        for ind in theme["indicators"]:
            ind["learning_cards"] = theme["learning_cards"]

    kb = {
        "meta": {
            "name": "智慧学伴知识库",
            "version": "1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scope": "七年级数学：代数式与整式运算、方程与方程组、不等式与不等式组",
            "sources": {
                "课程要求": "mydata/模拟学情数据索引.xlsx#课程要求",
                "题目与材料": "mydata/题目与材料.xlsx",
                "课程标准": "mydata/课程标准_2022.pdf",
                "教材切片": "mydata/B01—B08_相关资料切片.pdf",
            },
            "notes": [
                "教材印刷页与切片 PDF 页的对应关系已按页核对，与字段说明的教材正文页一致。",
                "教材条目本身未标注主题和指标，本库中的指标—教材映射为编辑映射，需在方案文档中说明规则。",
                "课标条目为相关条目摘录，未纳入后续学段内容（乘法公式、因式分解、一元二次方程等）。",
            ],
        },
        "curriculum": CURRICULUM,
        "themes": [themes[k] for k in sorted(themes)],
        "textbook_sections": TEXTBOOK_SECTIONS,
        "textbook_materials": textbooks,
        "questions": questions,
        "learning_cards": cards,
        "mappings": {
            "indicator_to_sections": INDICATOR_SECTIONS,
            "indicator_to_questions": {
                ind["indicator_id"]: ind["question_ids"]
                for theme in themes.values() for ind in theme["indicators"]
            },
        },
    }

    errors = validate(kb)
    if errors:
        for e in errors:
            print("[校验失败]", e, file=sys.stderr)
        raise SystemExit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "kb.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    return kb, out_path


def validate(kb):
    errors = []
    if len(kb["questions"]) != 54:
        errors.append(f"题目数量应为54，实际{len(kb['questions'])}")
    if len(kb["learning_cards"]) != 3:
        errors.append(f"学习卡数量应为3，实际{len(kb['learning_cards'])}")
    if len(kb["textbook_materials"]) != 8:
        errors.append(f"教材切片应为8，实际{len(kb['textbook_materials'])}")
    if len(kb["themes"]) != 3:
        errors.append(f"主题应为3，实际{len(kb['themes'])}")

    all_indicators = [i["indicator_id"] for t in kb["themes"] for i in t["indicators"]]
    if len(all_indicators) != 9:
        errors.append(f"观察指标应为9，实际{len(all_indicators)}")
    for iid in all_indicators:
        if iid not in INDICATOR_SECTIONS:
            errors.append(f"{iid} 缺少教材映射")
        if not kb["mappings"]["indicator_to_questions"].get(iid):
            errors.append(f"{iid} 没有对应题目")

    for qid, q in kb["questions"].items():
        if q["indicator_id"] not in all_indicators:
            errors.append(f"{qid} 的指标 {q['indicator_id']} 不在课程要求中")
        if q["max_score"] not in (1, 3):
            errors.append(f"{qid} 满分异常：{q['max_score']}")
        if q["max_score"] == 3:
            pts = q["score_points"]
            if len(pts) != 3 or sum(p["score"] for p in pts) != 3:
                errors.append(f"{qid} 评分点应为3个共3分，实际{len(pts)}个")
    return errors


def main():
    kb, path = build()
    print(f"知识库已写入：{path}")
    print(f"主题 {len(kb['themes'])} 个 | 指标 {len(kb['mappings']['indicator_to_questions'])} 个 | "
          f"题目 {len(kb['questions'])} 道 | 学习卡 {len(kb['learning_cards'])} 张 | "
          f"教材切片 {len(kb['textbook_materials'])} 份 | 教材小节 {len(kb['textbook_sections'])} 个")
    for theme in kb["themes"]:
        print(f"- {theme['theme_id']} {theme['name']}：题目 {len(theme['question_ids'])} 道，"
              f"指标 {len(theme['indicators'])} 个，学习卡 {','.join(theme['learning_cards'])}")
        for ind in theme["indicators"]:
            print(f"    {ind['indicator_id']} {ind['description']} | 题 {len(ind['question_ids'])} 道 | "
                  f"教材 {', '.join(s['material_id'] + ' ' + s['pages'] for s in ind['textbook_sections'])}")


if __name__ == "__main__":
    main()
