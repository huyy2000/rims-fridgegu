"""LLM 网关。

LLM_MODE=deepseek —— DeepSeek Function Call 式解析（JSON 输出 + 严格校验，
失败自动回落 mock 规则解析，保证链路永不断）。
LLM_MODE=mock    —— 本地规则解析（无需任何 API Key）。

parse_text() 是唯一入口，返回结构一致：
  {"intent": ..., "items": [...], "raw": ...}
"""
import json
import re

import httpx

from ..config import settings

# ---------- 物品字典（v1 精简版，W0 会补成 200+ 条） ----------
# name -> (中文分类, 默认保质天数)
_ITEM_KNOWLEDGE: dict[str, tuple[str, int]] = {
    # 乳制品/蛋类
    "牛奶": ("dairy", 7), "酸奶": ("dairy", 21), "鸡蛋": ("dairy", 30),
    "鸭蛋": ("dairy", 30), "鹌鹑蛋": ("dairy", 20),
    # 肉类/水产
    "五花肉": ("meat", 3), "猪肉": ("meat", 3), "牛肉": ("meat", 3),
    "羊肉": ("meat", 3), "鸡肉": ("meat", 3), "排骨": ("meat", 3),
    "鱼": ("meat", 2), "虾": ("meat", 2), "螃蟹": ("meat", 2),
    "豆腐": ("vegetable", 2), "豆干": ("vegetable", 5), "豆皮": ("vegetable", 5),
    # 蔬菜
    "西红柿": ("vegetable", 5), "番茄": ("vegetable", 5), "黄瓜": ("vegetable", 5),
    "青菜": ("vegetable", 3), "生菜": ("vegetable", 3), "菠菜": ("vegetable", 3),
    "白菜": ("vegetable", 5), "西兰花": ("vegetable", 5), "胡萝卜": ("vegetable", 14),
    "土豆": ("vegetable", 14), "洋葱": ("vegetable", 14), "大蒜": ("vegetable", 14),
    "葱": ("vegetable", 3), "姜": ("vegetable", 14), "辣椒": ("vegetable", 10),
    # 水果
    "苹果": ("fruit", 14), "香蕉": ("fruit", 5), "橙子": ("fruit", 10),
    "梨": ("fruit", 10), "葡萄": ("fruit", 5), "西瓜": ("fruit", 7),
    "草莓": ("fruit", 3), "桃子": ("fruit", 5),
    # 调味
    "酱油": ("condiment", 365), "盐": ("condiment", 365), "糖": ("condiment", 365),
    "醋": ("condiment", 365), "料酒": ("condiment", 365), "蚝油": ("condiment", 180),
    "食用油": ("condiment", 365), "油": ("condiment", 365),
    # 饮品
    "可乐": ("drink", 180), "雪碧": ("drink", 180), "啤酒": ("drink", 180),
    "矿泉水": ("drink", 365), "水": ("drink", 365), "果汁": ("drink", 14),
    # 主食
    "面条": ("grain", 180), "挂面": ("grain", 180), "大米": ("grain", 365),
    "米": ("grain", 365), "水饺": ("grain", 180), "饺子": ("grain", 180),
    "馒头": ("grain", 5),
    # 冷饮
    "雪糕": ("dairy", 180), "冰淇淋": ("dairy", 180), "冰棍": ("dairy", 180),
}

_UNIT_PATTERN = re.compile(
    r"(盒|袋|瓶|个|根|块|斤|克|毫升|ml|g|kg|把|包|桶|听|只|颗|串|头|片|罐|扎)"
)
_NUM_PATTERN = re.compile(r"(\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)")
_FULL_ITEM = re.compile(
    r"(?P<num>\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)?\s*"
    r"(?P<unit>盒|袋|瓶|个|根|块|斤|克|毫升|ml|g|kg|把|包|桶|听|只|颗|串|头|片|罐|扎)?\s*"
    r"(?P<name>[\u4e00-\u9fa5]{1,8})$"
)

_CN_NUM = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "半": 0.5,
}

# 意图关键词：按优先级从前往后匹配
_INTENT_RULES = [
    ("query", re.compile(r"(还有|剩|有没有|有什么|多少个|几个|快过期|临期|哪些|啥|多少)")),
    ("shopping", re.compile(r"(购物清单|要买|帮我买|再买|买点|买些|该买|采购|^买(?![了]))")),
    ("consume", re.compile(r"(喝完了|喝掉|用完了|用掉|吃完了|吃完|吃掉了|吃掉|用光了|消灭|拿出了|拿出|拿走|取出来|取出|取了)")),
    ("remove", re.compile(r"(扔了|扔掉|丢了|丢掉|过期了|坏了|清掉|清理了|清了|倒掉)")),
    ("add", re.compile(r"(买了|放了|加了|放入|放进|存了|买了点|补了|进了)")),
]

_START_JUNK = re.compile(r"^(买了|买了点|放了|加了|放入|放进|存了|补了|进了|又|放|买)")

_TRAILING_QTY = re.compile(
    r"^(?P<head>.*?)(?P<num>\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*"
    r"(?P<unit>盒|袋|瓶|个|根|块|斤|克|毫升|ml|g|kg|把|包|桶|听|只|颗|串|头|片|罐|扎)\s*$"
)
_UNIT_SET = frozenset("盒袋瓶个根块斤克毫升把包桶听只颗串头片罐扎")


def category_of(name: str) -> tuple[str, int]:
    """返回 (英文分类, 默认保质天数)；未知物品归「其他/7 天」。"""
    return _ITEM_KNOWLEDGE.get(name, ("other", 7))


# ---------- 位置常识库（D-12）：用户没说位置时，按品类/物品常识自动归类 ----------
# 品类默认位置
_CATEGORY_LOCATION = {
    "dairy": "冷藏",       # 乳蛋
    "vegetable": "冷藏",   # 蔬菜豆腐
    "fruit": "冷藏",       # 水果
    "drink": "冷藏",       # 饮品
    "meat": "冷冻",        # 肉类水产（买回多数冻存；当天吃用户会说"放冷藏"）
    "grain": "冷冻",       # 主食多为速冻（水饺/馒头）
    "condiment": "调味",   # 调味品（冰箱门格/调味区）
    "other": "冷藏",
}
# 物品级覆盖（品类默认不合适时单独指明）
_ITEM_LOCATION = {
    "雪糕": "冷冻", "冰淇淋": "冷冻", "冰棍": "冷冻", "冰激凌": "冷冻",
    "大米": "常温", "米": "常温", "挂面": "常温",
    "面条": "冷藏",  # 鲜面条
    "豆腐": "冷藏", "豆干": "冷藏",  # 品类是 vegetable，但不当蔬菜堆冷冻
}
# LLM 可输出的位置白名单
VALID_LOCATIONS = ("冷藏", "冷冻", "调味", "常温")


def default_location(name: str) -> str:
    """用户没说位置时的常识推断：物品级覆盖 > 品类默认。"""
    if name in _ITEM_LOCATION:
        return _ITEM_LOCATION[name]
    return _CATEGORY_LOCATION.get(category_of(name)[0], "冷藏")


def _to_number(raw: str) -> float:
    if raw in _CN_NUM:
        return float(_CN_NUM[raw])
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _parse_add_segment(seg: str) -> dict | None:
    """解析单个片段，返回 {name, quantity, unit} 或 None。

    支持两类句式：
      - "两盒牛奶"     → 牛奶 2 盒
      - "一袋鸡蛋30个" → 鸡蛋 30 个（尾部数量优先于前面的袋数）
    """
    m = _TRAILING_QTY.match(seg)
    if m and m.group("head"):
        hm = _FULL_ITEM.match(m.group("head"))
        if hm and hm.group("name"):
            return {
                "name": hm.group("name"),
                "quantity": _to_number(m.group("num")),
                "unit": m.group("unit"),
            }
    m = _FULL_ITEM.match(seg)
    if m and m.group("name"):
        return {
            "name": m.group("name"),
            "quantity": _to_number(m.group("num")) if m.group("num") else 1.0,
            "unit": m.group("unit") or "个",
        }
    return None


def _extract_items_add(text: str) -> list[dict]:
    """解析「放了两盒牛奶、一袋鸡蛋」这类录入句式。"""
    text = re.sub(r"(大概|大约|差不多|左右)", "", text)
    items: list[dict] = []
    for seg in re.split(r"[、，,。;；\s]+", text):
        seg = _START_JUNK.sub("", seg.strip())
        if not seg:
            continue
        parsed = _parse_add_segment(seg)
        if parsed:
            items.append(parsed)
        else:
            # 兜底：把结尾的中文词当物品名（排除纯单位词，如单独的"个"）
            tail = re.search(r"([\u4e00-\u9fa5]{1,8})$", seg)
            if tail and tail.group(1) not in _UNIT_SET:
                name = tail.group(1)
                head = seg[: tail.start()]
                num = _NUM_PATTERN.search(head)
                items.append({
                    "name": name,
                    "quantity": _to_number(num.group(1)) if num else 1.0,
                    "unit": "个",
                })
    return items


def _extract_items_consume(text: str) -> list[dict]:
    """解析「牛奶喝完了」「用了2个鸡蛋」这类扣减句式。"""
    pat = re.compile(
        r"(?P<name>[\u4e00-\u9fa5]{1,6})"
        r"(?:喝完了|喝掉|喝光|用完了|用完|用掉|用光了|吃完了|吃完|吃掉了|吃掉|扔了|扔掉|丢了|丢掉|过期了|坏了|清掉了|清掉|倒掉了|拿出了|拿出|拿走了|拿走|取出来了|取出|取了)"
        r"(?P<rest>.*)$"
    )
    items: list[dict] = []
    for seg in re.split(r"[、，,。;；\s]+", text):
        m = pat.search(seg)
        if m and m.group("name"):
            name = m.group("name")
            rest = m.group("rest").strip()
            qty = None  # None = 全部吃完/用完（如"牛奶喝完了"）
            unit = "个"
            rm = re.search(r"(\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*(盒|袋|瓶|个|根|块|斤|把|包|桶|听|只|颗|串)", rest)
            if rm:
                qty = _to_number(rm.group(1))
                unit = rm.group(2)
            items.append({"name": name, "quantity": qty, "unit": unit})
    return items


def _extract_shopping_items(text: str) -> list[dict]:
    """解析「买酱油和纸巾」「加一瓶可乐到清单」这类购物清单句式。"""
    text = re.sub(r"(购物清单|清单|要买|帮我买|再买|买点|买些|该买|采购|加.*?到.*?清单)", "", text)
    text = text.replace("和", "、").replace("跟", "、").replace("以及", "、")
    items: list[dict] = []
    for seg in re.split(r"[、，,。;；\s]+", text):
        seg = seg.strip()
        if not seg:
            continue
        m = _FULL_ITEM.match(seg)
        if m and m.group("name"):
            items.append({
                "name": m.group("name"),
                "quantity": m.group("num") or "1",
                "unit": m.group("unit") or "",
            })
        elif seg and re.fullmatch(r"[\u4e00-\u9fa5]{1,8}", seg):
            items.append({"name": seg, "quantity": "1", "unit": ""})
    return items


_VALID_INTENTS = {
    "upsert_inventory", "consume_inventory", "remove_inventory",
    "query_inventory", "create_shopping_list", "chat",
}

_LLM_SYSTEM_PROMPT = """你是「冰箱菇」，一个只负责冰箱库存记账的助手。

职责边界（铁律）：
- 你只做一件事：从用户的话里提取冰箱库存相关的事实（放入 / 消耗 / 扔掉 / 查询 / 要买）。
- 用户经常口语化、东拉西扯、夹带寒暄——你只挑库存事实，其余内容（天气、心情、
  新闻、请求帮忙做别的任何事）一律当没听见，不要回答它。
- 绝不编造：用户没明确提到的物品不许入库；数量含糊（"一些""几瓶"）时 quantity=1，
  unit 填原词（如"些"）；宁可少记，不错记。
- 一次性说多个物品就拆成多个 items；"喝完了/吃完了"不带数量 = quantity 填 null（整体消耗）。
- 与库存无关 → intent=chat，items 留空，不要试图回答它的内容。

输出 JSON：
{"intent": "upsert_inventory|consume_inventory|remove_inventory|query_inventory|create_shopping_list|chat",
 "items": [{"name": "物品名", "quantity": 数字或null, "unit": "单位或null", "location": "冷藏|冷冻|调味|常温或null"}]}

规则补充：
- location 只有在用户**明说**了位置时才填（"放冷冻了""塞急冻""放门上调味架"→冷冻/调味），
  没说就填 null，位置由常识库自动推断，你不用猜。

示例：
用户："今天累死了，不过早上买了两盒牛奶放冰箱了，鸡蛋大概30个，对了明天好像要下雨"
输出：{"intent":"upsert_inventory","items":[{"name":"牛奶","quantity":2,"unit":"盒"},{"name":"鸡蛋","quantity":30,"unit":"个"}]}
用户："外面下雨了明天记得带伞"
输出：{"intent":"chat","items":[]}
用户："我妈来住两天，冰箱塞满了，两盒牛奶一打啤酒还有半棵白菜"
输出：{"intent":"upsert_inventory","items":[{"name":"牛奶","quantity":2,"unit":"盒"},{"name":"啤酒","quantity":1,"unit":"打"},{"name":"白菜","quantity":0.5,"unit":"棵"}]}
用户："牛奶好像喝完了，蛋糕也不新鲜了扔了吧"
输出：{"intent":"consume_inventory","items":[{"name":"牛奶","quantity":null,"unit":"盒"},{"name":"蛋糕","quantity":null,"unit":"个"}]}
用户："拿出一个橘子"
输出：{"intent":"consume_inventory","items":[{"name":"橘子","quantity":1,"unit":"个"}]}
用户："五花肉和雪糕放冷冻了，草莓洗好放冷藏"
输出：{"intent":"upsert_inventory","items":[{"name":"五花肉","quantity":1,"unit":"盒","location":"冷冻"},{"name":"雪糕","quantity":1,"unit":"盒","location":"冷冻"},{"name":"草莓","quantity":1,"unit":"盒","location":"冷藏"}]}
只输出 JSON，不要输出任何其他文字。"""


def parse_text(text: str) -> dict:
    """统一入口：文字 → 结构化意图。deepseek 失败自动回落 mock。"""
    if settings.llm_mode == "deepseek" and settings.deepseek_api_key:
        try:
            return _parse_with_llm(text)
        except Exception:
            pass
    return _parse_with_mock(text)


def _parse_with_llm(text: str) -> dict:
    """DeepSeek 解析 + 严格校验；任何结构不符都抛异常 → 上层回落 mock。"""
    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 500,
    }
    r = httpx.post(
        f"{settings.deepseek_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        json=body,
        timeout=15,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    plan = _validate_llm_plan(data, text)
    return plan


def _validate_llm_plan(data: dict, raw: str) -> dict:
    intent = data.get("intent")
    if intent not in _VALID_INTENTS:
        raise ValueError(f"bad intent: {intent}")
    plan: dict = {"intent": intent, "raw": raw}
    items = data.get("items") or []
    if items and intent in (
        "upsert_inventory", "consume_inventory",
        "remove_inventory", "create_shopping_list",
    ):
        cleaned = []
        for it in items:
            name = str(it.get("name", "")).strip()
            if not name:
                continue
            qty = it.get("quantity")
            if qty is not None:
                try:
                    qty = float(qty)
                except (TypeError, ValueError):
                    qty = 1.0
            location = str(it.get("location") or "").strip()
            if location not in VALID_LOCATIONS:
                location = None  # 没说/乱说 -> 交常识库
            cleaned.append({
                "name": name,
                "quantity": qty,
                "unit": str(it.get("unit") or "个"),
                "location": location,
            })
        if not cleaned and intent != "query_inventory":
            raise ValueError("no valid items")
        plan["items"] = cleaned
    return plan


def _parse_with_mock(text: str) -> dict:
    for intent, pattern in _INTENT_RULES:
        if pattern.search(text):
            if intent == "query":
                return {"intent": "query_inventory", "raw": text}
            if intent == "shopping":
                items = _extract_shopping_items(text)
                if items:
                    return {"intent": "create_shopping_list", "items": items, "raw": text}
                continue  # 匹配到但没解析出物品，继续走其他规则
            if intent in ("add", "consume", "remove"):
                extractor = _extract_items_add if intent == "add" else _extract_items_consume
                items = extractor(text)
                if items:
                    return {
                        "intent": {
                            "add": "upsert_inventory",
                            "consume": "consume_inventory",
                            "remove": "remove_inventory",
                        }[intent],
                        "items": items,
                        "raw": text,
                    }
    return {"intent": "chat", "raw": text}
