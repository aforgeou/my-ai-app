# -*- coding: utf-8 -*-
"""智慧学伴：学情诊断、分层建议与对话式引导。

运行：
    ..\\.venv\\Scripts\\streamlit run app.py

数据完全来自本地分析结果：
    kb/kb.json
    data/analysis_individual.json
    data/analysis_class.json
    data/recommendations.json
    data/records_normalized.csv
    data/analysis_questions.csv
    data/analysis_score_points.csv
    data/data_quality.json

对话只做引导：不给答案，只给提示、证据、课标条目与教材页码。
"""
import ast
import csv
import json
import os
import re
import sys

import pandas as pd
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
KB_PATH = os.path.join(BASE, "kb", "kb.json")
sys.path.insert(0, BASE)

from advisor import build_indexes, card_for, curriculum_for, guidance_for, sections_for  # noqa: E402
from analyzer import labels_for, parse_points  # noqa: E402

st.set_page_config(page_title="智慧学伴 · 学情诊断", layout="wide")


@st.cache_data
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pct(value):
    if value is None or value == "":
        return "—"
    return f"{float(value) * 100:.1f}%"


def theme_sections(indicators):
    rows, seen = [], set()
    for ind in indicators:
        for s in sections_for(ind):
            key = (s["材料编号"], s["小节"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(s)
    return rows


def theme_curricula(kb, indicators):
    rows, seen = [], set()
    for ind in indicators:
        cur = curriculum_for(kb, ind)
        if cur["编号"] in seen:
            continue
        seen.add(cur["编号"])
        rows.append(cur)
    return rows


def indicators_of_theme(imap, theme_id):
    return [ind for ind in imap.values() if ind.get("theme_id") == theme_id]


def focus_item(student_rec, theme_id=None):
    items = student_rec["建议"]
    if theme_id:
        for item in items:
            if item["目标指标"].startswith(theme_id):
                return item
    for item in items:
        if item["层级"] in ("补充诊断", "基础巩固", "关键突破"):
            return item
    return items[0] if items else None


THEME_KEYWORDS = {
    "T01": ["代数式", "整式", "合并同类项", "去括号", "代入", "用字母表示"],
    "T02": ["方程", "方程组", "消元", "一元一次", "二元一次"],
    "T03": ["不等式", "解集", "数轴", "取值范围"],
}


def detect_theme(text):
    for theme_id, keywords in THEME_KEYWORDS.items():
        if any(k in text for k in keywords):
            return theme_id
    return None


# ---------------------------------------------------------------------------
# 本地工具型智能体：会话状态、题目选择、提示阶梯、答案解析与进度
# ---------------------------------------------------------------------------

UNITS = ("厘米", "平方厘米", "米", "平方米", "元", "人", "个", "本", "支", "岁", "cm")


def agent_state(sid):
    states = st.session_state.setdefault("agent_state", {})
    return states.setdefault(sid, {
        "current": None,
        "mastered": [],
        "attempts": 0,
        "hints": 0,
        "passed": 0,
    })


def find_item_q(student_rec, qid, kb):
    """返回建议条目与题目；题目合并知识库中的答案与评分点，仅用于本地核对。"""
    for item in student_rec["建议"]:
        for q in item["推荐材料"]["题目"]:
            if q["材料编号"] == qid:
                merged = dict(q)
                merged.update(kb["questions"].get(qid, {}))
                return item, merged
    return None, None


def choose_practice(student_rec, state, theme_id=None):
    pool = [(item, q) for item in student_rec["建议"] for q in item["推荐材料"]["题目"]]
    if theme_id:
        pool = [x for x in pool if x[0]["目标指标"].startswith(theme_id)]
    if not pool:
        return None, None
    current = state["current"]["qid"] if state["current"] else None
    mastered = set(state["mastered"])
    candidates = [x for x in pool if x[1]["材料编号"] not in mastered]
    if not candidates:
        candidates = pool
    for item, q in candidates:
        if len(candidates) == 1 or q["材料编号"] != current:
            return item, q
    return candidates[0]


def set_current(state, item, q):
    state["current"] = {
        "qid": q["材料编号"],
        "layer": item["层级"],
        "indicator": item["目标指标"],
        "hints_used": 0,
        "attempts": 0,
        "status": "待作答",
    }


def text_norm(value):
    s = str(value or "").strip().lower()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("，", ",").replace("；", ";").replace("：", ":")
    s = s.replace("×", "*").replace("÷", "/").replace("－", "-").replace("—", "-")
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = re.sub(r"\s+", "", s)
    for unit in UNITS:
        s = s.replace(unit, "")
    s = s.replace("。", "").replace("答:", "").replace("选", "")
    return s


def strip_answer_prefix(value):
    s = str(value or "").strip()
    s = re.sub(r"^(核对|提交|我算得|我算的是|我写的|我的答案是|答案是|答案|结果)[:：=]?", "", s)
    return s.strip()


def parse_assignments(s):
    return {k: float(v) for k, v in re.findall(r"(x|y|n|a|b)=(-?\d+(?:\.\d+)?)", s)}


def parse_inequality(s):
    one = re.fullmatch(r"x(<=|>=|<|>)(-?\d+(?:\.\d+)?)", s)
    if one:
        return ("one", one.group(1), float(one.group(2)))
    two = re.fullmatch(r"(-?\d+(?:\.\d+)?)(<=|>=|<|>)(x)(<=|>=|<|>)(-?\d+(?:\.\d+)?)", s)
    if two:
        return ("range", float(two.group(1)), two.group(2), float(two.group(5)), two.group(4))
    return None


def safe_value(expr, x):
    expr = expr.replace("^", "**")
    expr = re.sub(r"(\d)(x)", r"\1*x", expr)
    expr = re.sub(r"(x)(\d)", r"x*\2", expr)
    expr = re.sub(r"(\d)(\()", r"\1*(", expr)
    expr = re.sub(r"(\))(\d)", r")*\2", expr)
    tree = ast.parse(expr, mode="eval")
    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("unsupported expression")
        if isinstance(node, ast.Name) and node.id != "x":
            raise ValueError("unsupported name")
    return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {"x": x})


def answer_match(user_text, correct_text):
    """返回 True / False / None（无法可靠判断）。"""
    user = text_norm(strip_answer_prefix(user_text))
    correct = text_norm(correct_text)
    if not user:
        return None
    if user == correct:
        return True
    if ";" in correct:
        first = correct.split(";")[0]
        if first and (user == first or (len(first) >= 3 and user.startswith(first))):
            return True
    yes = {"是", "对", "正确", "可以", "能"}
    no = {"否", "不对", "错误", "不可以", "不能", "不是"}
    if correct in yes and user in yes:
        return True
    if correct in no and user in no:
        return True
    if (correct in yes and user in no) or (correct in no and user in yes):
        return False
    if re.fullmatch(r"[a-d]", correct) and re.fullmatch(r"[a-d]", user):
        return correct == user

    correct_assign = parse_assignments(correct)
    user_assign = parse_assignments(user)
    if correct_assign:
        if user_assign:
            return all(abs(correct_assign[k] - user_assign.get(k, float("inf"))) < 1e-6
                       for k in correct_assign)
        numbers = re.findall(r"-?\d+(?:\.\d+)?", user)
        if len(correct_assign) == 1 and len(numbers) == 1:
            return abs(list(correct_assign.values())[0] - float(numbers[0])) < 1e-6
        return None

    correct_ineq = parse_inequality(correct)
    user_ineq = parse_inequality(user)
    if correct_ineq and user_ineq:
        return correct_ineq == user_ineq
    if correct_ineq and not user_ineq:
        if re.search(r"[<>=]", user) or re.fullmatch(r"-?\d+(?:\.\d+)?", user):
            return False
        return None

    if "=" not in correct and "=" not in user and re.search(r"\d", correct) and re.search(r"\d", user):
        try:
            values = [safe_value(correct, x) for x in (1.5, 2, 3, 5)]
            user_values = [safe_value(user, x) for x in (1.5, 2, 3, 5)]
            return all(abs(a - b) < 1e-6 for a, b in zip(values, user_values))
        except Exception:
            pass
    try:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", correct) and re.fullmatch(r"-?\d+(?:\.\d+)?", user):
            return abs(float(correct) - float(user)) < 1e-6
    except Exception:
        pass
    return None


def score_point_self_check(q):
    return "\n".join(f"- {p['id']} {p['description']}（{p['score']}分）" for p in q["score_points"])


def practice_reply(sid, ctx, state, theme_id=None):
    item, q = choose_practice(ctx["recs"]["students"][sid], state, theme_id)
    if not q:
        return {"content": "当前没有可推荐的题目。先补一次诊断练习，我再按结果给你排题。",
                "source": "recommendations.json"}
    set_current(state, item, q)
    body = [
        f"给你一道**{item['层级']}**层的题，目标指标 **{item['目标指标']} {item['目标描述']}**。",
        "",
        f"**{q['材料编号']}**（{q['题型']}，{q['满分']}分）｜历史表现：{q['当前表现']}",
        "",
        q["题干"],
        "",
        "在下方输入框写你的最终答案，我会核对但不会显示正确答案。",
        "卡住了就点“给我提示”，一次只给一个提示。",
    ]
    if item["依据"]["教材"]:
        sec = item["依据"]["教材"][0]
        body += ["", f"需要时回看 {sec['材料编号']} 第 {sec['教材页']} 页“{sec['小节']}”。"]
    return {"content": "\n".join(body),
            "source": f"recommendations.json；{q['材料编号']}；课标 {item['依据']['课标']['编号']}"}


def hint_reply(sid, ctx, state):
    current = state["current"]
    if not current:
        return {"content": "现在没有进行中的练习。先说“来一题”，我再按你的薄弱指标出题。",
                "source": "recommendations.json"}
    item, q = find_item_q(ctx["recs"]["students"][sid], current["qid"], ctx["kb"])
    if not q:
        return {"content": "当前题目不在本次建议中，说“换一题”重新选一道。", "source": "recommendations.json"}
    hints = item["引导提示"]
    used = current["hints_used"]
    if used < len(hints):
        current["hints_used"] = used + 1
        state["hints"] += 1
        current["status"] = "提示中"
        body = [f"**提示 {used + 1}/{len(hints)}**：{hints[used]}",
                "", "先按这个提示改一步，再提交核对；我不会直接给出结果。"]
        source = f"recommendations.json；{current['qid']}"
    else:
        sec = item["依据"]["教材"][0] if item["依据"]["教材"] else None
        body = ["提示已经用完。下一步不猜答案，改为对照评分点自评：",
                "", score_point_self_check(q),
                "",
                f"回看教材 {sec['材料编号']} 第 {sec['教材页']} 页“{sec['小节']}”，把每一步写出来。" if sec else
                "回看教材对应小节，把每一步写出来。",
                "写完后再提交，我帮你看卡在哪一步。"]
        source = f"recommendations.json；kb.json；{current['qid']}"
    return {"content": "\n".join(body), "source": source}


def check_reply(sid, text, ctx, state):
    current = state["current"]
    if not current:
        return {"content": "还没有进行中的题目。先说“来一题”，再提交你的答案。",
                "source": "recommendations.json"}
    item, q = find_item_q(ctx["recs"]["students"][sid], current["qid"], ctx["kb"])
    if not q:
        return {"content": "当前题目不在建议列表中，请说“换一题”。", "source": "recommendations.json"}
    user_answer = strip_answer_prefix(text)
    if not user_answer:
        return {"content": "把最终答案写在“核对：”后面，例如“核对：x=11”。", "source": "kb.json"}
    result = answer_match(user_answer, q["answer"])
    current["attempts"] += 1
    state["attempts"] += 1
    current["status"] = "已核对"

    if result is True:
        if current["qid"] not in state["mastered"]:
            state["mastered"].append(current["qid"])
            state["passed"] += 1
        current["status"] = "已通过"
        body = [
            "**核对结果：正确。**",
            "",
            f"{current['qid']} 已加入本次已通过题目。",
            "下一步：说“来一题”继续，或说“看进度”查看完成情况。",
            "",
            "如果只是答案对、过程还不稳，建议再按评分点复述一遍步骤。",
        ]
        return {"content": "\n".join(body), "source": f"本地答案核对；{current['qid']}（不显示参考答案）"}

    if result is False:
        hints = item["引导提示"]
        used = current["hints_used"]
        if used < len(hints):
            current["hints_used"] = used + 1
            state["hints"] += 1
            body = ["**核对结果：还不对。**", "",
                    f"先别改答案，按提示检查一步：**{hints[used]}**",
                    "", "改完再提交；连续两次不对时，我会建议回看教材，而不是直接给结果。"]
        else:
            sec = item["依据"]["教材"][0] if item["依据"]["教材"] else None
            body = ["**核对结果：还不对。**", "",
                    "提示已用完，回到评分点逐项自评：", "", score_point_self_check(q), ""]
            if sec:
                body.append(f"回看 {sec['材料编号']} 第 {sec['教材页']} 页“{sec['小节']}”，把每一步写出来。")
            body.append("我不直接给答案；把过程写出来，我帮你定位卡点。")
        return {"content": "\n".join(body), "source": f"本地答案核对；{current['qid']}（不显示参考答案）"}

    body = ["**我无法可靠判断这个写法是否等价。**",
            "先按评分点自评，不急着改：", "", score_point_self_check(q), "",
            "如果你愿意，把中间步骤分步写出来（例如“第一步去括号：……”），我按步骤帮你看。"]
    return {"content": "\n".join(body), "source": f"本地答案核对；{current['qid']}（不显示参考答案）"}


def progress_reply(sid, ctx, state):
    student_rec = ctx["recs"]["students"][sid]
    total = len({q["材料编号"] for item in student_rec["建议"] for q in item["推荐材料"]["题目"]})
    mastered = set(state["mastered"])
    layers = {}
    for item in student_rec["建议"]:
        qids = [q["材料编号"] for q in item["推荐材料"]["题目"]]
        got = sum(1 for q in qids if q in mastered)
        layers.setdefault(item["层级"], [0, 0])
        layers[item["层级"]][0] += got
        layers[item["层级"]][1] += len(qids)
    body = [f"**{sid} 本次会话进度**", "",
            f"- 已通过：{len(mastered)}/{total} 道推荐题",
            f"- 尝试核对：{state['attempts']} 次",
            f"- 使用提示：{state['hints']} 次"]
    current = state["current"]
    if current:
        body.append(f"- 当前题目：{current['qid']}（{current['status']}，已用提示 {current['hints_used']} 个）")
    body += ["", "分层完成情况："]
    for layer, (got, total_q) in layers.items():
        if total_q:
            body.append(f"- {layer}：{got}/{total_q}")
    body += ["", "这是本次浏览器会话的进度，不写回赛题原始数据。"]
    return {"content": "\n".join(body), "source": "recommendations.json；会话状态"}


def complete_reply(sid, ctx, state):
    current = state["current"]
    if not current:
        return {"content": "没有进行中的题目。说“来一题”开始一道练习。", "source": "recommendations.json"}
    item, q = find_item_q(ctx["recs"]["students"][sid], current["qid"], ctx["kb"])
    if current["qid"] not in state["mastered"]:
        state["mastered"].append(current["qid"])
        state["passed"] += 1
    current["status"] = "标记完成"
    body = [f"已把 {current['qid']} 标记为完成。",
            "",
            "如果只是“看懂了”而不是独立做对，建议再说“来一题”做一道同类变式，确认能迁移。",
            "", "说“看进度”查看本次完成情况。"]
    return {"content": "\n".join(body), "source": f"会话状态；{current['qid']}"}


def build_reply(text, sid, ctx):
    """本地工具型智能体：路由意图 → 调用工具 → 返回引导式回答。"""
    kb = ctx["kb"]
    individual = ctx["individual"]
    recs = ctx["recs"]
    records = ctx["records"]
    imap = ctx["imap"]
    theme_name = ctx["theme_name"]

    student = individual[sid]
    student_rec = recs["students"][sid]
    state = agent_state(sid)

    theme_id = detect_theme(text)
    qid_match = re.search(r"Q\d{3}", text.upper())
    qid = qid_match.group(0) if qid_match else None

    # 工具 1：核对答案
    if state["current"] and re.match(r"^(核对|提交|我算得|我算的是|我写的|我的答案是|答案[:：=]|结果[:：=])",
                                      text.strip()):
        return check_reply(sid, text, ctx, state)

    # 工具 2：提示阶梯
    if state["current"] and re.search(r"提示|卡住|不会做|没思路|怎么下手|怎么算|下一步", text):
        return hint_reply(sid, ctx, state)

    # 工具 3：进度
    if re.search(r"进度|完成情况|做了多少|掌握了几", text):
        return progress_reply(sid, ctx, state)

    # 工具 4：标记完成
    if re.search(r"标记完成|这题会了|完成了这题|我掌握了", text):
        return complete_reply(sid, ctx, state)

    # 工具 5：重置本次进度
    if re.search(r"重置|重新开始|清空进度", text):
        state.clear()
        state.update({"current": None, "mastered": [], "attempts": 0, "hints": 0, "passed": 0})
        return {"content": "本次会话进度已重置，原始作答记录不受影响。说“来一题”重新开始。",
                "source": "会话状态"}

    # 工具 6：寒暄与帮助
    if re.fullmatch(r"(你好|您好|hi|hello|在吗)[!！.。?？]*", text.strip(), re.I):
        return {"content": "你好，我是你的数学学伴。可以问我：哪里薄弱、下一步学什么、来一题、给个提示、看进度。",
                "source": "本地工具型智能体"}
    if re.search(r"谢谢|感谢|辛苦了", text):
        return {"content": "不客气。继续的话，说“来一题”或“看进度”。", "source": "本地工具型智能体"}
    if re.search(r"你能做什么|你会什么|怎么用|帮助", text):
        return {"content": "我基于你的作答记录做四件事：诊断薄弱指标、给出分层计划、出题并分级提示、核对答案与记录进度。"
                          "我不直接给答案。", "source": "本地工具型智能体"}

    # 1. 索要答案：拒绝并给引导问题
    if re.search(r"答案|直接告诉|告诉我结果|正确结果|结果是什么", text):
        item = focus_item(student_rec, theme_id)
        if item:
            hints = item["引导提示"][:3]
            sec = item["依据"]["教材"][0] if item["依据"]["教材"] else None
            body = [
                "我不会直接给答案，但可以陪你走到能自己判断的那一步。",
                "",
                f"当前重点是 **{item['目标指标']} {item['目标描述']}**。",
                "先试着自己回答：",
            ]
            body += [f"- {h}" for h in hints]
            if sec:
                body += ["", f"需要回看：{sec['材料编号']} 第 {sec['教材页']} 页“{sec['小节']}”。"]
            body += ["", "把你的中间步骤发给我，我帮你定位卡在哪一步。"]
            return {"content": "\n".join(body), "source": "recommendations.json；kb.json"}
        return {"content": "我不会直接给答案。先说说你卡在哪一步，我给你对应的教材页和引导问题。",
                "source": "recommendations.json"}

    # 2. 指定题目
    if qid and qid in kb["questions"]:
        q = kb["questions"][qid]
        rows = [r for r in records
                if r["学生编号"] == sid and r["材料编号"] == qid
                and r["数据可用性"] == "已评分-可用于分析"]
        head = f"**{qid}**（{q['type']}，{q['max_score']}分，指标 {q['indicator_id']}）"
        body = [head, "", f"题干：{q['stem']}"]
        if not rows:
            body += ["", "你还没有这道题的可用记录。建议先独立完成，再按评分点自评。",
                     "注意：提交后才有数据，我不会替你做判断。"]
            return {"content": "\n".join(body),
                    "source": f"kb.json；records_normalized.csv（{sid} {qid} 无可用记录）"}
        best = max(rows, key=lambda r: int(r["得分"]))
        body += ["", f"当前最好表现：**{best['得分']}/{best['满分']}**（记录 {best['记录编号']}）", "", "评分点："]
        pts = parse_points(best["评分点得分"])
        all_labels = []
        for point in q["score_points"]:
            got = pts.get(point["id"], 0)
            labels = labels_for(point["description"])
            all_labels.extend(labels)
            mark = "已通过" if got >= point["score"] else "未通过"
            body.append(f"- {point['id']} {point['description']}：{got}/{point['score']}（{mark}）")
        actions, hints = guidance_for(all_labels or ["未通过该评分点"])
        if hints:
            body += ["", "先想一想："] + [f"- {h}" for h in hints[:3]]
        ind = imap[q["indicator_id"]]
        sec = sections_for(ind)[0]
        body += ["", f"对应教材：{sec['材料编号']} 第 {sec['教材页']} 页“{sec['小节']}”。",
                 "我能给的是思路和页码，具体结果要你自己写出来。"]
        return {"content": "\n".join(body),
                "source": f"{best['记录编号']} / {qid}；课标 {ind['curriculum_code']}；教材 {sec['材料编号']} P{sec['教材页']}"}

    # 3. 课标 / 教材
    if re.search(r"课标|教材|页码|课本|看哪", text):
        item = focus_item(student_rec, theme_id)
        ind = imap[item["目标指标"]] if item else None
        body = ["**对应课标与教材**", ""]
        source_parts = []
        if theme_id:
            inds = indicators_of_theme(imap, theme_id)
            for cur in theme_curricula(kb, inds):
                body.append(f"- 课标 {cur['编号']} {cur['标题']}（PDF {cur['文件页']} / 正文 {cur['正文页']}）")
                for entry in cur["条目"][:2]:
                    body.append(f"  - {entry}")
                source_parts.append(f"课标 {cur['编号']}")
            for sec in theme_sections(inds):
                body.append(f"- {sec['材料编号']} {sec['册别']} {sec['章节']}｜{sec['小节']}｜教材 P{sec['教材页']}（切片 PDF {sec['切片PDF页']} 页）")
                source_parts.append(f"{sec['材料编号']} P{sec['教材页']}")
            body += ["", f"建议从“{theme_name[theme_id]}”里你得分率最低的指标开始回看。"]
        elif ind:
            cur = curriculum_for(kb, ind)
            body.append(f"- 课标 {cur['编号']} {cur['标题']}（PDF {cur['文件页']} / 正文 {cur['正文页']}）")
            for entry in cur["条目"]:
                body.append(f"  - {entry}")
            for sec in sections_for(ind):
                body.append(f"- {sec['材料编号']} {sec['册别']} {sec['章节']}｜{sec['小节']}｜教材 P{sec['教材页']}（切片 PDF {sec['切片PDF页']} 页）")
            source_parts.append(f"课标 {cur['编号']}")
            source_parts += [f"{s['材料编号']} P{s['教材页']}" for s in sections_for(ind)]
        else:
            body.append("还没有足够记录定位到具体条目。先完成一次诊断练习，再回来看课标与页码。")
        return {"content": "\n".join(body), "source": "；".join(source_parts) or "kb.json"}

    # 4. 练习
    if re.search(r"练习|来一题|来道题|做题|换一题|再练|题目", text):
        return practice_reply(sid, ctx, state, theme_id)

    # 5. 计划 / 建议
    if re.search(r"计划|建议|怎么学|怎么提高|先学|怎么办", text):
        body = [f"**{sid} 的分层学习路线**（可用记录 {student['可用记录数']} 条，得分率 {pct(student['得分率'])}）", ""]
        for item in student_rec["建议"]:
            first_step = item["实施步骤"][0] if item["实施步骤"] else ""
            qids = "、".join(q["材料编号"] for q in item["推荐材料"]["题目"]) or "复述与自评"
            body.append(f"**{item['层级']}｜{item['目标指标']} {item['目标描述']}**")
            body.append(f"- 先做：{first_step}")
            body.append(f"- 材料：{qids}")
        body += ["", "按顺序做，完成一层再进下一层；记录不足的层级先补证据，不急着下结论。",
                 "想直接开始，说“来一题”。"]
        return {"content": "\n".join(body), "source": "recommendations.json；kb.json"}

    # 6. 证据 / 为什么错
    if re.search(r"证据|为什么|记录|依据", text):
        item = focus_item(student_rec, theme_id)
        if not item:
            return {"content": "还没有足够记录可以展开证据。先完成一次诊断练习。", "source": "records_normalized.csv"}
        body = [f"**{item['目标指标']} {item['目标描述']}** 的数据证据：", ""]
        for ev in item["依据"]["数据证据"]:
            body.append(f"- {ev['记录编号']}｜{ev['材料编号']}｜{ev['评分点']}｜表现：{ev['表现']}")
        if item["依据"]["失分步骤"]:
            body += ["", "对应失分步骤：" + "、".join(item["依据"]["失分步骤"])]
        cur = item["依据"]["课标"]
        body += ["", f"课标 {cur['编号']} {cur['标题']}（PDF {cur['文件页']} / 正文 {cur['正文页']}）"]
        if item["依据"]["教材"]:
            sec = item["依据"]["教材"][0]
            body += [f"教材 {sec['材料编号']} P{sec['教材页']}“{sec['小节']}”"]
        return {"content": "\n".join(body),
                "source": f"records_normalized.csv；分析结果 analysis_individual.json；课标 {cur['编号']}"}

    # 7. 薄弱点
    if re.search(r"薄弱|哪里|问题|不会|错|掌握|得分", text):
        body = [f"**{sid} 的当前画像**", "",
                f"- 可用记录：{student['可用记录数']} 条（{student['记录充分性']}）",
                f"- 总得分率：{pct(student['得分率'])}"]
        body += ["", "分主题："]
        for tid in ("T01", "T02", "T03"):
            row = student["分主题"][tid]
            flag = "可判断" if row["可否判断掌握"] else "信息不足"
            body.append(f"- {tid} {row['主题名称']}：{pct(row['得分率'])}（{row['可用记录数']} 条，{flag}）")
        if student["需关注指标"]:
            body += ["", "优先巩固："]
            for row in student["需关注指标"][:3]:
                body.append(f"- {row['指标编号']} {row['指标描述']}：{pct(row['得分率'])}（{row['可用记录数']} 条）")
        if student["主要失分步骤"]:
            body += ["", "主要失分步骤：" + "、".join(f"{x['失分标签']}（{x['次数']}次）" for x in student["主要失分步骤"][:4])]
        if student["信息不足主题"]:
            body += ["", f"{'、'.join(student['信息不足主题'])} 可用记录不足，先补诊断，不能据此判定未掌握。"]
        body += ["", "想看具体证据，可以问“我为什么错”。"]
        return {"content": "\n".join(body), "source": "analysis_individual.json；records_normalized.csv"}

    # 8. 主题概念
    if theme_id:
        inds = indicators_of_theme(imap, theme_id)
        card = card_for(kb, theme_id)
        body = [f"**{theme_name[theme_id]}**", ""]
        if card:
            body += [f"学习卡 {card['编号']}：{card['内容']}", ""]
        body.append("你的指标表现：")
        for ind in inds:
            row = student["分指标"].get(ind["indicator_id"], {})
            body.append(f"- {ind['indicator_id']} {ind['description']}：{pct(row.get('得分率'))}（{row.get('可用记录数', 0)} 条）")
        body += ["", "建议回看："]
        for cur in theme_curricula(kb, inds):
            body.append(f"- 课标 {cur['编号']} {cur['标题']}（PDF {cur['文件页']} / 正文 {cur['正文页']}）")
        for sec in theme_sections(inds)[:3]:
            body.append(f"- {sec['材料编号']} {sec['章节']}｜{sec['小节']}｜P{sec['教材页']}")
        body += ["", "先用自己的话复述这个主题的关键步骤，再做题；卡住时告诉我具体是哪一步。"]
        return {"content": "\n".join(body),
                "source": f"学习卡 {card['编号'] if card else '—'}；kb.json；analysis_individual.json"}

    # 9. 当前练习的裸答案（如“x=11”）
    if state["current"] and re.fullmatch(r"[0-9xy=<>≤≥+\-*/().,，。\s]+", text.strip()):
        return check_reply(sid, text, ctx, state)

    # 10. 默认：能力说明
    item = focus_item(student_rec)
    body = [
        "我可以基于你的作答记录做这些事：",
        "- 说“我哪里薄弱”看主题与指标表现",
        "- 说“下一步怎么学”看分层建议",
        "- 说“来一题”拿一道匹配当前层的练习",
        "- 说“给我提示”逐级提示，不直接给答案",
        "- 说“核对：x=11”检查你的答案",
        "- 说“看进度”查看本次完成情况",
        "- 说“查课标和教材页码”定位回看材料",
        "- 说“我为什么错”看具体记录与评分点证据",
        "- 也可以直接问“Q014”或“不等式”。",
        "",
        "我不会直接给出结果：只给证据、页码和引导问题。",
    ]
    if item:
        body += ["", f"你现在可以先关注 **{item['目标指标']} {item['目标描述']}**。"]
    return {"content": "\n".join(body), "source": "recommendations.json；kb.json"}


def render_student(ctx, sid):
    individual, recs = ctx["individual"], ctx["recs"]
    student = individual[sid]
    rec = recs["students"][sid]

    st.markdown(f"## {sid} · 学习画像")
    cols = st.columns(4)
    cols[0].metric("可用记录", f"{student['可用记录数']} 条")
    cols[1].metric("总得分率", pct(student["得分率"]))
    cols[2].metric("记录充分性", student["记录充分性"])
    cols[3].metric("待巩固指标", f"{len(student['需关注指标'])} 个")
    st.caption(rec["摘要"])

    tabs = st.tabs(["分层建议", "数据证据", "对话学伴"])

    with tabs[0]:
        order = ["补充诊断", "基础巩固", "关键突破", "迁移应用", "自主检验", "拓展提升"]
        items = sorted(rec["建议"], key=lambda x: order.index(x["层级"]) if x["层级"] in order else 99)
        for item in items:
            with st.expander(f"{item['层级']}｜{item['目标指标']} {item['目标描述']}",
                             expanded=item["层级"] == "基础巩固"):
                left, right = st.columns([1.05, 1])
                with left:
                    st.markdown("**数据证据**")
                    ev_rows = [{
                        "记录": e["记录编号"],
                        "题目": e["材料编号"],
                        "评分点": e["评分点"],
                        "表现": e["表现"],
                    } for e in item["依据"]["数据证据"]]
                    st.dataframe(pd.DataFrame(ev_rows), hide_index=True, width="stretch")
                    cur = item["依据"]["课标"]
                    st.markdown(f"**课标 {cur['编号']} {cur['标题']}**（PDF {cur['文件页']} / 正文 {cur['正文页']}）")
                    for entry in cur["条目"][:3]:
                        st.markdown(f"- {entry}")
                    st.markdown("**教材**")
                    for sec in item["依据"]["教材"]:
                        st.markdown(f"- {sec['材料编号']} {sec['册别']} {sec['章节']}｜{sec['小节']}｜教材 P{sec['教材页']}（切片 PDF {sec['切片PDF页']} 页）")
                with right:
                    st.markdown("**推荐题目（不含答案）**")
                    qs = item["推荐材料"]["题目"]
                    if qs:
                        for q in qs:
                            st.markdown(f"- `{q['材料编号']}` {q['题型']}（{q['满分']}分）｜当前表现：{q['当前表现']}")
                            st.markdown(f"  > {q['题干']}")
                    else:
                        st.caption("本层级以复述与自评为主，不额外布置题目。")
                    card = item["推荐材料"]["学习卡"]
                    if card:
                        st.info(f"学习卡 {card['编号']}：{card['内容']}")
                    st.markdown("**实施步骤**")
                    for i, step in enumerate(item["实施步骤"], 1):
                        st.markdown(f"{i}. {step}")
                    st.markdown("**引导提示（只提问，不给答案）**")
                    for hint in item["引导提示"]:
                        st.markdown(f"- {hint}")
                    st.caption("完成标准：" + item["完成标准"])
        st.caption(rec["使用说明"])

    with tabs[1]:
        st.markdown("**分主题表现**")
        theme_rows = [{
            "主题": tid,
            "名称": row["主题名称"],
            "可用记录": row["可用记录数"],
            "得分率": pct(row["得分率"]),
            "记录充分性": row["记录充分性"],
            "能否判断": "可判断" if row["可否判断掌握"] else "信息不足",
        } for tid, row in student["分主题"].items()]
        st.dataframe(pd.DataFrame(theme_rows), hide_index=True, width="stretch")

        st.markdown("**分指标表现**")
        ind_rows = [{
            "指标": iid,
            "描述": row["指标描述"],
            "主题": row["主题编号"],
            "可用记录": row["可用记录数"],
            "得分率": pct(row["得分率"]),
            "置信度": row["判断置信度"],
            "需关注": "是" if row["是否需关注"] else "否",
        } for iid, row in student["分指标"].items()]
        st.dataframe(pd.DataFrame(ind_rows), hide_index=True, width="stretch")

        if student["主要失分步骤"]:
            st.markdown("**主要失分步骤**")
            st.dataframe(pd.DataFrame([
                {"失分标签": x["失分标签"], "次数": x["次数"]} for x in student["主要失分步骤"]
            ]), hide_index=True, width="stretch")

        st.markdown("**证据明细（当前版本记录）**")
        for ev in student["证据"]:
            with st.expander(f"{ev['材料编号']}｜{ev['评分点编号']} {ev['评分点描述']}｜{ev['得分']}/{ev['满分']}"):
                st.markdown(f"题干：{ev['题干']}")
                st.markdown("失分标签：" + "、".join(ev["失分标签"]))
                if ev.get("学生最终作答"):
                    st.markdown(f"我的最终作答：{ev['学生最终作答']}")

    with tabs[2]:
        hist = st.session_state.setdefault("chat", {}).setdefault(sid, [])
        state = agent_state(sid)

        def ask(question):
            hist.append({"role": "user", "content": question})
            reply = build_reply(question, sid, ctx)
            hist.append({"role": "assistant", "content": reply["content"], "source": reply["source"]})

        st.caption("对话只做引导：不给答案，只给证据、课标条目、教材页码和提示问题。")

        status = st.columns(4)
        status[0].metric("会话已通过", f"{len(state['mastered'])} 题")
        status[1].metric("核对次数", state["attempts"])
        status[2].metric("提示使用", state["hints"])
        status[3].metric("当前题目", state["current"]["qid"] if state["current"] else "未开始")

        current = state["current"]
        if current:
            item, q = find_item_q(rec, current["qid"], ctx["kb"])
            if q:
                with st.container(border=True):
                    st.markdown(f"**当前练习 {current['qid']}**｜{current['layer']}｜{current['indicator']}")
                    st.markdown(q["题干"])
                    st.caption(f"状态：{current['status']}｜提示 {current['hints_used']}/{len(item['引导提示'])}"
                               f"｜已核对 {current['attempts']} 次")
                    with st.form(key=f"answer_form_{sid}", clear_on_submit=True):
                        ans = st.text_area("你的最终答案", height=80,
                                           placeholder="只写最终结果，例如 x=11")
                        submitted = st.form_submit_button("提交核对")
                    if submitted:
                        if ans.strip():
                            ask("核对：" + ans.strip())
                            st.rerun()
                        else:
                            st.warning("先写下答案，再提交核对。")
                    b = st.columns(3)
                    b[0].button("给我提示", on_click=ask, args=("给我一个提示",), width="stretch")
                    b[1].button("换一题", on_click=ask, args=("来一题练习",), width="stretch")
                    b[2].button("标记完成", on_click=ask, args=("把这题标记完成",), width="stretch")
        else:
            st.info("还没有进行中的练习。点“来一题”，我按你的薄弱指标出题。")

        quick = st.columns(6)
        quick[0].button("我的薄弱点", on_click=ask, args=("我哪里薄弱？",), width="stretch")
        quick[1].button("学习计划", on_click=ask, args=("下一步怎么学？",), width="stretch")
        quick[2].button("来一题", on_click=ask, args=("来一题练习",), width="stretch")
        quick[3].button("看进度", on_click=ask, args=("看进度",), width="stretch")
        quick[4].button("课标页码", on_click=ask, args=("课标和教材看哪几页？",), width="stretch")
        quick[5].button("为什么错", on_click=ask, args=("我为什么错？",), width="stretch")

        st.divider()
        for message in hist:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message.get("source"):
                    st.caption("依据：" + message["source"])

        text = st.chat_input("问问学伴：我哪里薄弱？来一题，或输入“核对：x=11”", key=f"chat_input_{sid}")
        if text:
            ask(text)
            st.rerun()


def render_teacher(ctx, cls):
    kb = ctx["kb"]
    class_report = ctx["class_report"]
    recs = ctx["recs"]
    quality = ctx["quality"]
    qrows = ctx["qrows"]
    prows = ctx["prows"]

    c = class_report["classes"][cls]
    plan = recs["classes"][cls]

    st.markdown(f"## {cls} · 班级学情")
    cols = st.columns(4)
    cols[0].metric("学生数", str(c["学生数"]))
    cols[1].metric("可用记录", f"{c['可用记录数']} 条")
    cols[2].metric("班级得分率", pct(c["得分率"]))
    cols[3].metric("相对薄弱指标", f"{len(c['相对薄弱指标'])} 个")
    st.caption(plan["摘要"])

    tabs = st.tabs(["班级概览", "指标对比", "题目与评分点", "分层与干预", "数据与口径"])

    with tabs[0]:
        left, right = st.columns(2)
        with left:
            st.markdown("**分主题得分率**")
            theme_df = pd.DataFrame([
                {"主题": f"{tid} {row['主题名称']}", "得分率": float(row["得分率"] or 0), "可用记录": row["可用记录数"]}
                for tid, row in c["分主题"].items()
            ]).set_index("主题")
            st.bar_chart(theme_df["得分率"], height=280)
        with right:
            st.markdown("**优先干预指标**")
            st.dataframe(pd.DataFrame([
                {"指标": x["指标编号"], "描述": x["指标描述"],
                 "得分率": pct(x["得分率"]), "可用记录": x["可用记录数"]}
                for x in plan["优先指标"]
            ]), hide_index=True, width="stretch")

        st.markdown("**共性薄弱评分点**")
        st.dataframe(pd.DataFrame([
            {"评分点": x["评分点编号"], "描述": x["评分点描述"],
             "失败数": x["失败数"], "评价数": x["评价数"], "失败率": pct(x["失败率"])}
            for x in c["共性薄弱评分点"]
        ]), hide_index=True, width="stretch")

    with tabs[1]:
        gaps = class_report["两班指标对比"]
        st.markdown("**DC01 与 DC02 指标对比**")
        st.dataframe(pd.DataFrame([
            {"指标": g["指标编号"], "描述": g["指标描述"],
             "DC01": pct(g["DC01得分率"]), "DC02": pct(g["DC02得分率"]),
             "差值(pp)": g["差值百分点"], "可比性": g["可比性"]}
            for g in gaps
        ]), hide_index=True, width="stretch")
        st.caption("差值 = DC01 − DC02（百分点）。样本不足的对比只作参考。")

        st.markdown("**本班分指标得分率**")
        st.dataframe(pd.DataFrame([
            {"指标": iid, "描述": row["指标描述"], "可用记录": row["可用记录数"],
             "得分率": pct(row["得分率"])}
            for iid, row in c["分指标"].items()
        ]), hide_index=True, width="stretch")

    with tabs[2]:
        q_df = pd.DataFrame([
            {"题目": r["材料编号"], "主题": r["主题编号"], "指标": r["指标编号"],
             "题型": r["题型"], "满分": r["满分"],
             "可用记录": int(r["可用记录数"]),
             "得分率": float(r["得分率"]) if r["得分率"] != "" else 0.0}
            for r in qrows if r["班级"] == cls and r["可用记录数"] != "0"
        ]).sort_values("得分率")
        st.markdown("**题目得分率（从低到高）**")
        st.dataframe(
            q_df.assign(得分率=q_df["得分率"].map(lambda v: f"{v * 100:.1f}%")),
            hide_index=True, width="stretch"
        )

        p_df = pd.DataFrame([
            {"评分点": r["评分点编号"], "题目": r["材料编号"], "描述": r["评分点描述"],
             "评价数": int(r["评价记录数"]), "失败数": int(r["失败数"]),
             "失败率": float(r["失败率"]) if r["失败率"] != "" else 0.0}
            for r in prows if r["班级"] == cls and int(r["评价记录数"]) >= 5
        ])
        if not p_df.empty:
            p_df = p_df.sort_values(["失败率", "失败数"], ascending=False).head(15)
            st.markdown("**失败率最高的评分点（样本≥5）**")
            st.dataframe(
                p_df.assign(失败率=p_df["失败率"].map(lambda v: f"{v * 100:.1f}%")),
                hide_index=True, width="stretch"
            )

    with tabs[3]:
        layers = plan["分层安排"]
        st.markdown("**分层名单**")
        col_a, col_b = st.columns(2)
        col_a.markdown("补诊断：" + "、".join(layers["补诊断"]))
        col_a.markdown("夯实层：" + "、".join(layers["夯实层"]))
        col_b.markdown("提升层：" + "、".join(layers["提升层"]))
        col_b.markdown("拓展层：" + "、".join(layers["拓展层"]))

        st.markdown("**共性干预**")
        for item in plan["共性干预"]:
            with st.expander(f"{item['范围']}｜{item['问题']}｜失败 {item['失败情况']}"):
                st.markdown(f"关联指标：{item['关联指标']}｜涉及题目：{item['涉及题目']}")
                st.markdown("数据依据：" + item["依据"]["数据"])
                cur = item["依据"]["课标"]
                st.markdown(f"课标 {cur['编号']} {cur['标题']}（PDF {cur['文件页']} / 正文 {cur['正文页']}）")
                for entry in cur["条目"][:3]:
                    st.markdown(f"- {entry}")
                st.markdown("教材：" + "；".join(
                    f"{s['材料编号']} P{s['教材页']}“{s['小节']}”" for s in item["依据"]["教材"][:2]
                ))
                st.markdown("**教学动作**")
                for action in item["教学动作"]:
                    st.markdown(f"- {action}")
                st.markdown("**引导问题**")
                for hint in item["引导问题"]:
                    st.markdown(f"- {hint}")
                stems = []
                for qid in item["变式练习"]:
                    q = kb["questions"].get(qid)
                    if q:
                        stems.append(f"{qid}：{q['stem']}")
                if stems:
                    st.markdown("**变式练习（不含答案）**")
                    for stem in stems:
                        st.markdown(f"- {stem}")
                st.caption("完成标准：" + item["完成标准"])

        st.markdown("**复查安排**")
        for row in plan["复查安排"]:
            st.markdown(f"- {row}")


def render_cases(ctx):
    cases = ctx["class_report"]["典型案例候选"]
    st.markdown("## 典型案例候选")
    st.caption(cases["说明"])
    cols = st.columns(2)
    groups = ["表现较好", "部分得分", "需关注", "样本偏少", "记录不足"]
    for i, name in enumerate(groups):
        with cols[i % 2]:
            st.markdown(f"**{name}**（{len(cases[name])} 人）")
            st.markdown("、".join(cases[name]) or "—")


def render_quality(ctx):
    quality = ctx["quality"]
    st.markdown("**数据体检**")
    cols = st.columns(4)
    cols[0].metric("原始记录", quality["totals"]["原始记录数"])
    cols[1].metric("作答事件", quality["totals"]["作答事件数"])
    cols[2].metric("当前版本", quality["totals"]["当前版本记录数"])
    cols[3].metric("学生", quality["totals"]["学生数"])

    st.dataframe(pd.DataFrame([
        {"数据可用性": k, "记录数": v} for k, v in quality["availability_counts"].items()
    ]), hide_index=True, width="stretch")

    st.markdown("**问题记录分布**")
    st.dataframe(pd.DataFrame([
        {"问题类型": k, "记录数": len(v)} for k, v in quality["issues"].items()
    ]), hide_index=True, width="stretch")

    with st.expander("查看问题记录样例"):
        for key, rows in quality["issues"].items():
            st.markdown(f"**{key}**（{len(rows)} 条）")
            st.dataframe(pd.DataFrame(rows).head(5), hide_index=True, width="stretch")

    st.markdown("**处理口径**")
    for rule in quality["handling_rules"]:
        st.markdown(f"- {rule}")


def main():
    kb = load_json(KB_PATH)
    individual = load_json(os.path.join(DATA_DIR, "analysis_individual.json"))["students"]
    class_report = load_json(os.path.join(DATA_DIR, "analysis_class.json"))
    recs = load_json(os.path.join(DATA_DIR, "recommendations.json"))
    quality = load_json(os.path.join(DATA_DIR, "data_quality.json"))
    records = load_csv(os.path.join(DATA_DIR, "records_normalized.csv"))
    qrows = load_csv(os.path.join(DATA_DIR, "analysis_questions.csv"))
    prows = load_csv(os.path.join(DATA_DIR, "analysis_score_points.csv"))

    question, imap, theme_of, theme_name, _ = build_indexes(kb)
    ctx = {
        "kb": kb, "individual": individual, "recs": recs, "records": records,
        "imap": imap, "theme_of": theme_of, "theme_name": theme_name,
        "class_report": class_report, "quality": quality, "qrows": qrows, "prows": prows,
    }

    st.sidebar.markdown("## 智慧学伴")
    st.sidebar.caption("学情诊断 + 分层建议 + 引导式对话")
    view = st.sidebar.radio("视角", ["学生学习", "教师分析", "案例候选", "数据体检"])
    if view == "学生学习":
        sid = st.sidebar.selectbox("选择学生", sorted(individual),
                                   format_func=lambda x: f"{x}（{individual[x]['模拟班级编号']}）")
        render_student(ctx, sid)
    elif view == "教师分析":
        cls = st.sidebar.selectbox("选择班级", ["DC01", "DC02"])
        render_teacher(ctx, cls)
    elif view == "案例候选":
        render_cases(ctx)
    else:
        render_quality(ctx)

    st.sidebar.divider()
    st.sidebar.caption("数据口径：仅“已评分-可用于分析”记录进入统计；待评分、未作答与异常记录单独标注。")
    st.sidebar.caption("生成文件：data/recommendations.json、data/recommendations_index.csv")


if __name__ == "__main__":
    main()
