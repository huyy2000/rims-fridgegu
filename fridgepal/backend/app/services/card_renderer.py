"""库存卡片渲染：把库存表画成竖版 PNG 图片卡（公众号推送用）。

设计参考（2026-10-02 检索的冰箱/食材库存管理类产品共性做法）：
- 字段：名称 / 数量 / 状态（按剩余天数颜色分级）/ 到期与建议
- 临期置顶（剩余天数升序），耗尽沉底并给"补货"动作提示（联动购物清单的心智）
- 头部统计行：共 N 项 · 临期 M · 待补货 K——一眼先看数字再看表
竖版约 3:4，标题栏带日期与「豆豆刚记下」摘要句。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import APP_ROOT

logger = logging.getLogger(__name__)

_card_dir = APP_ROOT / "uploads" / "cards"

_W, _H = 750, 1000
_BG = "#FFF8F2"
_HEADER = "#E85513"
_ROW_ALT = "#FDEEE2"
_TEXT = "#3D2B1F"
_MUTED = "#9A8577"
_GREEN = "#3BA272"
_ORANGE = "#E8833A"
_RED = "#D64545"
_GRAY = "#B9A99C"

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "C:/Windows/Fonts/simsun.ttc",   # 宋体
]


def _font(size: int, bold: bool = False):
    candidates = ([_FONT_CANDIDATES[1]] if bold else []) + _FONT_CANDIDATES
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _days_left(row) -> int | None:
    if not row.expire_at:
        return None
    exp = row.expire_at if row.expire_at.tzinfo else row.expire_at.replace(tzinfo=timezone.utc)
    return (exp - datetime.now(timezone.utc)).days


def _exp_str(row) -> str:
    if not row.expire_at:
        return ""
    exp = row.expire_at if row.expire_at.tzinfo else row.expire_at.replace(tzinfo=timezone.utc)
    return f"{exp.astimezone():%m-%d}"


def _status_of(row) -> tuple[str, str, str]:
    """返回 (状态短文案, 颜色, 建议文案)。文案长度控制在卡宽内（≤8 字符）。"""
    qty = float(row.quantity or 0)
    if qty <= 0:
        return "补货", _RED, "该补货了"
    days = _days_left(row)
    if days is not None and days <= 3:
        label = f"{days}天" if days > 0 else "今天"
        return label, _ORANGE, f"{_exp_str(row)}前吃"
    return "新鲜", _GREEN, (f"{_exp_str(row)}到期" if row.expire_at else "状态不错")


def render_inventory_card(rows: list, summary: str = "") -> Path:
    """rows: list[Inventory]；summary: 一句话摘要（如「刚记下：牛奶×2」）。"""
    _card_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    f_title = _font(44, bold=True)
    f_date = _font(24)
    f_stat = _font(26, bold=True)
    f_summary = _font(28)
    f_head = _font(28, bold=True)
    f_cell = _font(28)
    f_footer = _font(22)

    # 标题栏
    draw.rounded_rectangle([0, 0, _W, 150], radius=0, fill=_HEADER)
    draw.text((40, 34), "冰箱菇 · 库存卡片", font=f_title, fill="white")
    now = datetime.now()
    draw.text((40, 98), now.strftime("%Y-%m-%d %H:%M"), font=f_date, fill="#FFE3D1")

    # 统计行：共 N 项 · 临期 M · 待补货 K
    def _st(r):
        return _status_of(r)[0]

    n_total = len(rows)
    n_soon = sum(1 for r in rows if float(r.quantity or 0) > 0 and _st(r) != "新鲜")
    n_out = sum(1 for r in rows if float(r.quantity or 0) <= 0)
    stats = f"共 {n_total} 项"
    if n_soon:
        stats += f" · 临期 {n_soon}"
    if n_out:
        stats += f" · 待补货 {n_out}"
    draw.text((40, 172), stats, font=f_stat, fill=_ORANGE if (n_soon or n_out) else _GREEN)

    # 摘要句
    draw.text((40, 214), summary or "豆豆刚记下", font=f_summary, fill=_TEXT)
    draw.line([40, 266, _W - 40, 266], fill="#F0DCC8", width=2)

    # 表头
    cols = [(40, "物品"), (330, "数量"), (470, "状态"), (600, "到期 · 建议")]
    y = 290
    for x, label in cols:
        draw.text((x, y), label, font=f_head, fill=_MUTED)
    y += 48

    # 排序：临期(剩余天数升序) → 新鲜(有到期日在前) → 耗尽沉底
    def _sort_key(r):
        if float(r.quantity or 0) <= 0:
            return (2, 0)
        days = _days_left(r)
        if days is not None and days <= 3:
            return (0, days)
        return (1, days if days is not None else 9999)

    ordered = sorted(rows, key=_sort_key)
    visible = ordered[:9]
    for i, r in enumerate(visible):
        status, color, advice = _status_of(r)
        if i % 2 == 1:
            draw.rounded_rectangle([24, y - 8, _W - 24, y + 44], radius=10, fill=_ROW_ALT)
        item_color = _GRAY if float(r.quantity or 0) <= 0 else _TEXT
        draw.text((40, y), r.item_name[:8], font=f_cell, fill=item_color)
        draw.text((330, y), f"{float(r.quantity or 0):g}{r.unit}", font=f_cell, fill=item_color)
        chip_w = 84
        draw.rounded_rectangle([470, y - 2, 470 + chip_w, y + 38], radius=16, fill=color)
        draw.text((470 + 16, y + 2), status, font=f_cell, fill="white")
        draw.text((600, y), advice[:8], font=f_cell, fill=_MUTED)
        y += 56

    if not visible:
        draw.text((40, y), "冰箱里空空如也，快说一句「放了两盒牛奶」吧", font=f_cell, fill=_MUTED)
        y += 56
    elif len(ordered) > 9:
        draw.text((40, y), f"还有 {len(ordered) - 9} 项 → 打开展示软件看全部", font=f_cell, fill=_MUTED)
        y += 56

    # 页脚
    draw.rounded_rectangle([0, _H - 70, _W, _H], radius=0, fill="#F6E7D8")
    draw.text((40, _H - 56), "冰箱菇 RIMS · 拍大蘑菇随手记 · 开门它主动问", font=f_footer, fill=_MUTED)

    out = _card_dir / f"card_{datetime.now():%Y%m%d_%H%M%S}_{id(rows) & 0xFFFF:04x}.png"
    img.save(out, "PNG")
    logger.info("库存卡片已生成: %s", out)
    return out
