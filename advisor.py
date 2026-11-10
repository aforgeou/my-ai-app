# -*- coding: utf-8 -*-
"""分层建议层：把诊断结果转成可执行、可追溯的学习与教学建议。

输入：kb/kb.json、data/analysis_individual.json、data/analysis_class.json、
      data/records_normalized.csv、data/analysis_score_points.csv
输出：
  data/recommendations.json        学生分层建议 + 班级教学干预方案
  data/recommendations_index.csv   建议索引（学生/层级/目标指标/材料）

约束：
  1. 每条建议给出数据证据、课标条目、教材页码、题目编号与学习卡编号；
  2. 提示语只引导思考，不给答案；
  3. 记录不足时先补证据，不把“缺记录”写成“未掌握”。
"""
import csv
import json
import os
from datetime import datetime

from analyzer import labels_for

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
KB_PATH = os.path.join(BASE, "kb", "kb.json")

ERROR_GUIDANCE = {
    "不等式乘除负数未变号": {
        "教学动作": "用具体数字先验证“2<3，两边同乘-1”的大小变化，再回到代数步骤，固定“先变号、再计算”的书写顺序。",
        "引导提示": ["两边同乘或同除以一个负数时，不等号方向要不要变？", "先用2和3试一试，你发现了什么？"],
    },
    "去括号符号错误": {
        "教学动作": "圈出括号前的符号，逐项写出“括号内每一项乘这个符号”的中间过程，再用代值检验。",
        "引导提示": ["括号前是负号时，括号里每一项的符号分别怎么变？", "能不能把去括号这一步单独写出来再合并？"],
    },
    "移项未变号": {
        "教学动作": "在等号两侧画箭头，规定“移项必须变号”，每步只移动一项并口头说明依据。",
        "引导提示": ["移项的依据是等式性质几？移过去以后符号变了吗？", "这一项一定要移吗？有没有更省步骤的做法？"],
    },
    "合并同类项错误": {
        "教学动作": "先用不同标记圈出同类项，再只合并系数；完成后代入一个特值检查化简前后是否相等。",
        "引导提示": ["哪些项所含字母和指数完全相同？", "合并时改变的是系数还是字母部分？"],
    },
    "去分母错误": {
        "教学动作": "先写最小公倍数，再给方程每一项（包括常数项）乘同一个数，分子是多项式时补括号。",
        "引导提示": ["分母的最小公倍数是多少？", "不含分母的常数项也要乘吗？分子要不要加括号？"],
    },
    "消元步骤错误": {
        "教学动作": "先比较两个方程中同一未知数的系数，优先选择加减消元；消元后立即回代求另一个未知数。",
        "引导提示": ["两个方程里哪个未知数的系数容易配成相反数？", "相加或相减后，消去的是哪一个未知数？"],
    },
    "不等式组公共解集错误": {
        "教学动作": "两个不等式分别解，画在同一条数轴上，只取重叠部分，逐项检查端点开闭。",
        "引导提示": ["两个解集在数轴上哪一段是重叠的？", "端点处是实心还是空心？为什么？"],
    },
    "数轴表示或端点开闭错误": {
        "教学动作": "先判断“含等号用实心、不含等号用空心”，再确定方向；用区间内一个测试点回验。",
        "引导提示": ["这个端点包不包括在解集里？", "取一个解集内的数代回去，成立吗？"],
    },
    "回代或代入求值错误": {
        "教学动作": "负数代入必须加括号，分“代换”和“计算”两行书写；代入后先化简再算。",
        "引导提示": ["把负数代进去时，加括号了吗？", "先算乘方还是先算乘法？"],
    },
    "缺少检验或检验错误": {
        "教学动作": "把解代回原方程或不等式，分别计算左右两边；应用题还要检查是否符合实际意义。",
        "引导提示": ["把解代回原式，左右两边相等吗？", "这个答案在题目情境里合理吗？"],
    },
    "结果未写单位": {
        "教学动作": "在答案后补单位，并在草稿上圈出题目要求的单位；作答前先看问的是什么量。",
        "引导提示": ["题目最后问的是数量还是数量关系？单位是什么？", "你的答案和题目要求的量对应吗？"],
    },
    "缺少对结果的解释": {
        "教学动作": "用一句话回答“这个结果说明什么”，引用题中的条件或限制，不重复计算过程。",
        "引导提示": ["化简结果里还有x吗？这说明什么？", "这个范围对题目中的人数或数量意味着什么？"],
    },
    "建模或列式错误": {
        "教学动作": "先画数量关系表或线段图，标出已知、未知和等量关系，再设未知数列式。",
        "引导提示": ["题目中哪两个量是相等的？", "你设的未知数表示什么？它和另一个量有什么关系？"],
    },
    "求解过程未完成": {
        "教学动作": "把“下一步做什么”写出来，按步骤分点完成，不跳步；每完成一步做一次符号检查。",
        "引导提示": ["现在到了哪一步？下一步该合并、移项还是去分母？", "这一步做完，方程变成什么样子？"],
    },
    "最终结果错误": {
        "教学动作": "回到最后一步验算，并用估算或代入判断结果是否合理；把易错符号单独标出。",
        "引导提示": ["把结果代回原题，成立吗？", "结果的数量级和题目情境吻合吗？"],
    },
    "未通过该评分点": {
        "教学动作": "对照评分点逐项自评：会做、会写、会检验；缺哪一步就补哪一步。",
        "引导提示": ["这个评分点要求你写出哪几步？", "你觉得自己卡在哪一步？"],
    },
}

LAYER_NAMES = {
    "diagnose": "补充诊断",
    "basic": "基础巩固",
    "key": "关键突破",
    "transfer": "迁移应用",
    "check": "自主检验",
    "enrich": "拓展提升",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rate_text(value):
    return "暂无可用数据" if value is None else f"{value * 100:.1f}%"


def build_indexes(kb):
    question = kb["questions"]
    indicator = {}
    theme_of_indicator = {}
    theme_name = {}
    for theme in kb["themes"]:
        theme_name[theme["theme_id"]] = theme["name"]
        for ind in theme["indicators"]:
            ind["theme_id"] = theme["theme_id"]
            indicator[ind["indicator_id"]] = ind
            theme_of_indicator[ind["indicator_id"]] = theme["theme_id"]
    cards = kb["learning_cards"]
    return question, indicator, theme_of_indicator, theme_name, cards


def records_for(records, sid):
    return [r for r in records if r["学生编号"] == sid]


def usable_records(records, sid, qid=None):
    rows = [r for r in records if r["学生编号"] == sid and r["数据可用性"] == "已评分-可用于分析"]
    if qid:
        rows = [r for r in rows if r["材料编号"] == qid]
    return rows


def best_performance(records, sid, qid):
    rows = usable_records(records, sid, qid)
    if not rows:
        return None, "无可用记录"
    best = max(rows, key=lambda r: int(r["得分"]))
    score, total = int(best["得分"]), int(best["满分"])
    if score == total:
        return best, "已掌握"
    return best, f"得分 {score}/{total}"


def pick_questions(kb, records, sid, indicator_id, limit=2, prefer="basic", exclude=None):
    question = kb["questions"]
    exclude = set(exclude or [])
    qids = [q for q in kb["mappings"]["indicator_to_questions"].get(indicator_id, []) if q not in exclude]
    ranked = []
    for qid in qids:
        q = question[qid]
        rec, status = best_performance(records, sid, qid)
        if status == "无可用记录":
            rank = 2
        elif rec and int(rec["得分"]) == 0:
            rank = 0
        elif status == "已掌握":
            rank = 3
        else:
            rank = 1
        type_pref = 0 if (prefer == "basic" and q["max_score"] == 1) else 0 if (prefer == "transfer" and q["max_score"] == 3) else 1
        ranked.append((rank, type_pref, qid, {
            "材料编号": qid,
            "题型": q["type"],
            "满分": q["max_score"],
            "题干": q["stem"],
            "当前表现": status,
            "来源": q["source"],
        }))
    ranked.sort(key=lambda x: (x[0], x[1], x[2]))
    return [item[3] for item in ranked[:limit]]


def evidence_for(student, indicator_id, limit=3):
    return [e for e in student["证据"] if e["指标编号"] == indicator_id][:limit]


def curriculum_for(kb, indicator):
    code = indicator["curriculum_code"]
    entry = kb["curriculum"].get(code, {})
    return {
        "编号": code,
        "标题": entry.get("title", ""),
        "文件页": entry.get("pdf_page"),
        "正文页": entry.get("print_page"),
        "条目": [item["text"] for item in entry.get("items", [])],
    }


def sections_for(indicator):
    return [{
        "材料编号": s["material_id"],
        "册别": s["volume"],
        "章节": s["chapter"],
        "小节": s["section"],
        "教材页": s["pages"],
        "切片PDF页": s["pdf_pages"],
    } for s in indicator["textbook_sections"]]


SECTION_HINTS = {
    "不等式乘除负数未变号": ["一元一次不等式"],
    "不等式组公共解集错误": ["一元一次不等式组"],
    "数轴表示或端点开闭错误": ["一元一次不等式"],
    "移项未变号": ["解一元一次方程"],
    "去分母错误": ["解一元一次方程"],
    "去括号符号错误": ["整式的加法与减法"],
    "合并同类项错误": ["整式的加法与减法"],
    "消元步骤错误": ["消元"],
    "建模或列式错误": ["实际问题"],
    "缺少对结果的解释": ["整式的加法与减法", "一元一次不等式", "实际问题"],
    "回代或代入求值错误": ["消元", "代数式的值"],
    "缺少检验或检验错误": ["实际问题", "一元一次方程"],
    "求解过程未完成": ["解一元一次方程", "一元一次不等式"],
}


def order_sections(indicator, labels):
    """按失分步骤把最相关的小节排到前面。"""
    sections = sections_for(indicator)
    targets = []
    for label in labels:
        targets.extend(SECTION_HINTS.get(label, []))
    if not targets:
        return sections
    return sorted(sections, key=lambda s: 0 if any(t in s["小节"] for t in targets) else 1)


def card_for(kb, theme_id):
    cards = kb["learning_cards"]
    for cid, card in cards.items():
        if card["theme_id"] == theme_id:
            return {"编号": cid, "内容": card["content"], "来源": card["source"]}
    return None


def guidance_for(labels):
    actions, hints = [], []
    for label in labels:
        g = ERROR_GUIDANCE.get(label)
        if g:
            if g["教学动作"] not in actions:
                actions.append(g["教学动作"])
            for h in g["引导提示"]:
                if h not in hints:
                    hints.append(h)
    return actions, hints


def base_item(layer, student, indicator, kb, records, question_limit=2, prefer="basic", labels=None,
              extra_steps=None, exclude=None):
    sid = student["学生编号"]
    labels = labels or []
    if not labels:
        labels = [x["失分标签"] for x in student["主要失分步骤"][:2]]
    evidence = evidence_for(student, indicator["indicator_id"], limit=3)
    if not evidence:
        qids = set(kb["mappings"]["indicator_to_questions"].get(indicator["indicator_id"], []))
        rows = [r for r in records if r["学生编号"] == sid
                and r["材料编号"] in qids and r["数据可用性"] == "已评分-可用于分析"]
        rows.sort(key=lambda r: int(r["得分"]) / int(r["满分"]) if int(r["满分"]) else 1)
        evidence = [{
            "记录编号": r["记录编号"],
            "材料编号": r["材料编号"],
            "评分点编号": "—",
            "评分点描述": "本题整体表现",
            "得分": int(r["得分"]),
            "满分": int(r["满分"]),
            "失分标签": ["本题未达满分" if int(r["得分"]) < int(r["满分"]) else "已达满分"],
        } for r in rows[:2]]
    if not evidence:
        evidence = [{
            "记录编号": "—", "材料编号": "—", "评分点编号": "—",
            "评分点描述": "暂无可用记录", "得分": 0, "满分": 0,
            "失分标签": ["本次用于补充检验证据"],
            "表现": "暂无可用记录，本次用于补充检验",
        }]
    actions, hints = guidance_for(labels)
    questions = pick_questions(kb, records, sid, indicator["indicator_id"], limit=question_limit,
                               prefer=prefer, exclude=exclude)
    if not questions and exclude:
        questions = pick_questions(kb, records, sid, indicator["indicator_id"], limit=question_limit, prefer=prefer)
    curriculum = curriculum_for(kb, indicator)
    sections = order_sections(indicator, labels)
    card = card_for(kb, thematic_theme(indicator))
    steps = []
    if actions:
        steps.extend(actions)
    if sections:
        steps.append(f"回看 {sections[0]['材料编号']} 第 {sections[0]['教材页']} 页“{sections[0]['小节']}”，对照自己的失分步骤做一次复述。")
    if questions:
        steps.append("完成推荐题目，先独立作答，再按评分点自评；只查教材，不直接看答案。")
    if extra_steps:
        steps.extend(extra_steps)
    return {
        "层级": LAYER_NAMES[layer],
        "目标指标": indicator["indicator_id"],
        "目标描述": indicator["description"],
        "依据": {
            "数据证据": [{
                "记录编号": e["记录编号"],
                "材料编号": e["材料编号"],
                "评分点": f"{e['评分点编号']} {e['评分点描述']}",
                "表现": e.get("表现") or f"{e['得分']}/{e['满分']}，{','.join(e['失分标签'])}",
            } for e in evidence],
            "课标": curriculum,
            "教材": sections,
            "失分步骤": labels,
            "观察指标": indicator["description"],
        },
        "推荐材料": {
            "教材": sections,
            "题目": questions,
            "学习卡": card,
        },
        "实施步骤": steps,
        "引导提示": hints[:3],
        "完成标准": f"推荐题目中至少{min(2, len(questions))}题达到满分，并能用自己的话说清关键步骤的依据；若仍卡在同一评分点，回到教材例题重做一遍。",
    }


def thematic_theme(indicator):
    return indicator["theme_id"]


def build_for_student(student, kb, records, indicator_map, theme_of_indicator, theme_name):
    sid = student["学生编号"]
    items = []
    used = set()
    missing = student["信息不足主题"]
    weak = student["需关注指标"]
    errors = [x["失分标签"] for x in student["主要失分步骤"][:3]]

    def add(layer, ind, **kwargs):
        item = base_item(layer, student, ind, kb, records, exclude=used, **kwargs)
        used.update(q["材料编号"] for q in item["推荐材料"]["题目"])
        items.append(item)

    for tid in missing:
        ind = next(i for i in indicator_map.values() if theme_of_indicator.get(i["indicator_id"]) == tid)
        qs = pick_questions(kb, records, sid, ind["indicator_id"], limit=3, prefer="basic", exclude=used)
        used.update(q["材料编号"] for q in qs)
        items.append({
            "层级": LAYER_NAMES["diagnose"],
            "目标指标": ind["indicator_id"],
            "目标描述": ind["description"],
            "依据": {
                "数据证据": [{"记录编号": "—", "材料编号": "—", "评分点": "—",
                              "表现": f"{tid}可用记录不足，暂不能判断掌握情况"}],
                "课标": curriculum_for(kb, ind),
                "教材": sections_for(ind),
                "失分步骤": [],
                "观察指标": ind["description"],
            },
            "推荐材料": {"教材": sections_for(ind), "题目": qs, "学习卡": card_for(kb, tid)},
            "实施步骤": [
                f"先用 {len(qs)} 道题补充{tid}的学习证据，覆盖概念、基本运算和简单应用。",
                "作答后按评分点自评，把“会做但写不全”和“不会做”分开记录。",
                "补齐证据后再回看本建议，不急于给掌握程度下结论。",
            ],
            "引导提示": ["这道题考的是哪个概念？", "你能写出第一步依据吗？"],
            "完成标准": f"完成{len(qs)}道诊断题并留下过程；若正确率达到60%以上，再进入基础巩固。",
        })

    if weak:
        target = weak[0]
        ind = indicator_map[target["指标编号"]]
        flat_labels = []
        for e in evidence_for(student, target["指标编号"], limit=2):
            flat_labels.extend(e["失分标签"])
        add("basic", ind, question_limit=2, prefer="basic", labels=flat_labels)
        if errors:
            add("key", ind, question_limit=1, prefer="transfer", labels=errors)
        add("transfer", ind, question_limit=1, prefer="transfer", labels=errors,
            extra_steps=["用自己的话解释为什么这样做，并写出完整过程。"])
        if len(weak) >= 2:
            ind2 = indicator_map[weak[1]["指标编号"]]
            labels2 = []
            for e in evidence_for(student, weak[1]["指标编号"], limit=2):
                labels2.extend(e["失分标签"])
            add("key", ind2, question_limit=1, prefer="transfer", labels=labels2)
    elif student["可否判断整体掌握"]:
        target = sorted(student["分指标"].items(),
                        key=lambda kv: (kv[1]["得分率"] if kv[1]["得分率"] is not None else 1.1))[0][0]
        ind = indicator_map[target]
        add("enrich", ind, question_limit=2, prefer="transfer", labels=errors,
            extra_steps=["尝试改变题目中的一个条件，编一道同类型题并解答。"])
        check_ind = next((iid for iid in indicator_map
                          if iid != target and pick_questions(kb, records, sid, iid, limit=1,
                                                              prefer="basic", exclude=used)), None)
        if check_ind:
            add("check", indicator_map[check_ind], question_limit=1, prefer="basic", labels=errors)
    elif not missing:
        add("diagnose", indicator_map["T01I1"], question_limit=3, prefer="basic", labels=errors)

    # 自主检验：从不同主题中各取一题，避免只练薄弱点
    if items and not any(i["层级"] == LAYER_NAMES["check"] for i in items):
        other = next((i for i in indicator_map.values()
                      if theme_of_indicator.get(i["indicator_id"]) != theme_of_indicator.get(items[0]["目标指标"])
                      and pick_questions(kb, records, sid, i["indicator_id"], limit=1,
                                         prefer="basic", exclude=used)), None)
        if other:
            add("check", other, question_limit=1, prefer="basic", labels=errors)

    summary = (
        f"{sid}：可用记录 {student['可用记录数']} 条，得分率 {rate_text(student['得分率'])}。"
        + (f"优先巩固 {'、'.join(x['指标编号'] for x in weak[:2])}。" if weak else "")
        + (f"{'、'.join(missing)}记录不足，先补充诊断证据。" if missing else "")
    )
    observation = [{
        "指标编号": iid,
        "指标描述": row["指标描述"],
        "可用记录数": row["可用记录数"],
        "观察建议": "补充1—2道该指标的诊断题，或在下一次作业中保留完整过程，再判断掌握程度。",
    } for iid, row in student["分指标"].items() if row["可用记录数"] < 3]
    if observation and not missing:
        summary += f"{len(observation)}个指标可用记录不足3条，先补观察证据，不判未掌握。"
    return {
        "学生编号": sid,
        "模拟班级编号": student["模拟班级编号"],
        "记录充分性": student["记录充分性"],
        "得分率": student["得分率"],
        "摘要": summary,
        "建议": items,
        "补充观察": observation,
        "使用说明": "建议按“补充诊断→基础巩固→关键突破→迁移应用→自主检验”的顺序使用；已完成并可自评的层级可跳过。",
    }


def class_layers(individual, cls):
    base, mid, high, diagnose = [], [], [], []
    for sid, row in individual.items():
        if row["模拟班级编号"] != cls:
            continue
        missing_theme = any(v["可用记录数"] == 0 for v in row["分主题"].values())
        if row["可用记录数"] < 5 or missing_theme:
            diagnose.append(sid)
        elif row["得分率"] is not None and row["得分率"] < 0.35:
            base.append(sid)
        elif row["得分率"] is not None and row["得分率"] < 0.75:
            mid.append(sid)
        else:
            high.append(sid)
    return {"补诊断": sorted(diagnose), "夯实层": sorted(base), "提升层": sorted(mid), "拓展层": sorted(high)}


def build_class_plan(cls, class_row, kb, individual, point_rows, question_rows, indicator_map, theme_of_indicator):
    question = kb["questions"]
    points = [r for r in point_rows if r["班级"] == cls and r["失败率"] and int(r["评价记录数"]) >= 5
              and "答案正确" not in r["评分点描述"]]
    points.sort(key=lambda r: (0 if float(r["失败率"]) >= 1.0 else 1,
                               -(int(r["失败数"]) * float(r["失败率"]))))

    def make(row, scope):
        qid = row["材料编号"]
        q = question[qid]
        ind = indicator_map[q["indicator_id"]]
        labels = labels_for(row["评分点描述"])
        actions, hints = guidance_for(labels or ["未通过该评分点"])
        practice = [p for p in kb["mappings"]["indicator_to_questions"][ind["indicator_id"]]
                    if p != qid and question[p]["max_score"] == 3][:2] or [qid]
        return {
            "范围": scope,
            "问题": f"{row['评分点编号']} {row['评分点描述']}",
            "失败情况": f"{row['失败数']}/{row['评价记录数']}（{float(row['失败率']) * 100:.1f}%）",
            "涉及题目": qid,
            "关联指标": ind["indicator_id"],
            "依据": {
                "数据": f"{scope}该评分点失败率 {float(row['失败率']) * 100:.1f}%，样本 {row['评价记录数']} 条。",
                "课标": curriculum_for(kb, ind),
                "教材": order_sections(ind, labels),
            },
            "教学动作": actions,
            "引导问题": hints,
            "变式练习": practice,
            "完成标准": "同类评分点在后续练习中失败率降到30%以下；学生能说明每一步的依据。",
        }

    interventions = []
    seen_questions = set()
    for row in points:
        if len(interventions) >= 5:
            break
        if row["材料编号"] in seen_questions:
            continue
        seen_questions.add(row["材料编号"])
        interventions.append(make(row, f"{cls}本班"))

    common = [r for r in point_rows
              if r["班级"] == "全体" and r["失败率"] and float(r["失败率"]) >= 1.0
              and int(r["评价记录数"]) >= 5 and "答案正确" not in r["评分点描述"]
              and r["材料编号"] not in seen_questions]
    if common:
        interventions.append(make(common[0], "两班共性"))

    priority_indicators = [
        {
            "指标编号": x["指标编号"],
            "指标描述": x["指标描述"],
            "得分率": x["得分率"],
            "可用记录数": x["可用记录数"],
        } for x in class_row["相对薄弱指标"][:3]
    ]
    layers = class_layers(individual, cls)
    summary = (
        class_row["摘要"]
        + "分层安排："
        + f"补诊断{len(layers['补诊断'])}人、夯实层{len(layers['夯实层'])}人、提升层{len(layers['提升层'])}人、拓展层{len(layers['拓展层'])}人。"
    )
    return {
        "班级编号": cls,
        "摘要": summary,
        "优先指标": priority_indicators,
        "共性干预": interventions,
        "分层安排": layers,
        "复查安排": [
            "下一次测验沿用同一指标口径，重点复查本次失败率最高的3个评分点。",
            "对补诊断学生先补足可用记录，再纳入掌握度统计。",
            "对拓展层学生增加“解释与变式”任务，不以重复刷题替代。",
        ],
    }


def main():
    kb = load_json(KB_PATH)
    individual = load_json(os.path.join(DATA_DIR, "analysis_individual.json"))["students"]
    class_report = load_json(os.path.join(DATA_DIR, "analysis_class.json"))
    records = read_csv(os.path.join(DATA_DIR, "records_normalized.csv"))
    point_rows = read_csv(os.path.join(DATA_DIR, "analysis_score_points.csv"))
    question_rows = read_csv(os.path.join(DATA_DIR, "analysis_questions.csv"))

    question, indicator_map, theme_of_indicator, theme_name, cards = build_indexes(kb)

    student_recs = {}
    for sid, row in individual.items():
        student_recs[sid] = build_for_student(row, kb, records, indicator_map, theme_of_indicator, theme_name)

    class_recs = {}
    for cls, row in class_report["classes"].items():
        class_recs[cls] = build_class_plan(cls, row, kb, individual, point_rows, question_rows,
                                          indicator_map, theme_of_indicator)

    # 校验：每条建议的材料都能回溯到知识库
    errors = []
    for sid, rec in student_recs.items():
        if not rec["建议"]:
            errors.append(f"{sid} 没有建议")
        for item in rec["建议"]:
            for q in item["推荐材料"]["题目"]:
                if q["材料编号"] not in kb["questions"]:
                    errors.append(f"{sid} 引用了不存在的题目 {q['材料编号']}")
            for s in item["推荐材料"]["教材"]:
                if s["材料编号"] not in kb["textbook_materials"]:
                    errors.append(f"{sid} 引用了不存在的教材 {s['材料编号']}")
            if item["推荐材料"]["学习卡"] and item["推荐材料"]["学习卡"]["编号"] not in kb["learning_cards"]:
                errors.append(f"{sid} 引用了不存在的学习卡")
            if item["目标指标"] not in indicator_map:
                errors.append(f"{sid} 目标指标不存在 {item['目标指标']}")
    if errors:
        for e in errors[:20]:
            print("[校验失败]", e)
        raise SystemExit(1)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rule_version": "advisor-v1",
        "students": student_recs,
        "classes": class_recs,
        "通用规则": [
            "建议顺序为补充诊断→基础巩固→关键突破→迁移应用→自主检验，可按已完成情况跳过。",
            "每条建议均绑定数据证据、课标条目、教材页码、题目编号与学习卡编号。",
            "引导提示只提问不给答案；完成标准以评分点达成情况为准。",
            "记录不足时只安排补证据任务，不对掌握程度作结论。",
        ],
    }
    with open(os.path.join(DATA_DIR, "recommendations.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    index_rows = []
    for sid, rec in student_recs.items():
        for item in rec["建议"]:
            index_rows.append({
                "学生编号": sid,
                "模拟班级编号": rec["模拟班级编号"],
                "层级": item["层级"],
                "目标指标": item["目标指标"],
                "教材材料": "；".join(f"{s['材料编号']}P{s['教材页']}" for s in item["推荐材料"]["教材"]),
                "题目": "；".join(q["材料编号"] for q in item["推荐材料"]["题目"]),
                "学习卡": item["推荐材料"]["学习卡"]["编号"] if item["推荐材料"]["学习卡"] else "",
                "完成标准": item["完成标准"],
            })
    with open(os.path.join(DATA_DIR, "recommendations_index.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()))
        writer.writeheader()
        writer.writerows(index_rows)

    print(f"学生建议 {len(student_recs)} 人，共 {len(index_rows)} 条；班级方案 {len(class_recs)} 个")
    for cls, plan in class_recs.items():
        print(f"- {plan['摘要']}")
        for item in plan["共性干预"][:2]:
            print(f"    {item['问题']}：{item['失败情况']}；教材 {item['依据']['教材'][0]['材料编号']} P{item['依据']['教材'][0]['教材页']}")
    print("输出：data/recommendations.json, data/recommendations_index.csv")


if __name__ == "__main__":
    main()
