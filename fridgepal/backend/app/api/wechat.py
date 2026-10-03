"""微信测试号回调与推送。

绑定流程（一次性）：
1. 启动后端 + 内网穿透，得到公网 URL（如 https://xxx.cpolar.io）；
2. 测试号页面「接口配置信息」填 URL=https://xxx/api/v1/wechat/callback、Token=fridgepal2026；
3. 点提交 → 微信 GET 本接口验签 → 原样返回 echostr → 绑定成功；
4. 用微信关注测试号、发消息即走 POST 分支，回复走同一条 AI 链路。
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..services import hotwords_service, wechat_service
from .recordings import _execute

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wechat", tags=["微信"])


@router.get("/callback")
def verify(
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
):
    """接口配置验证：验签通过原样返回 echostr。"""
    if wechat_service.check_signature(signature, timestamp, nonce):
        return PlainTextResponse(echostr)
    raise HTTPException(status_code=403, detail="验签失败")


@router.post("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """用户发给测试号的消息（文字走 AI 链路，语音提示用文字说）。"""
    body = await request.body()
    try:
        msg = wechat_service.parse_message(body)
    except Exception:
        return PlainTextResponse("success")

    msg_type = msg.get("MsgType", "")
    from_user = msg.get("FromUserName", "")
    to_user = msg.get("ToUserName", "")
    logger.info("微信消息: type=%s from=%s", msg_type, from_user[:8])

    if not from_user:
        return PlainTextResponse("success")

    # 账号绑定（单家庭 MVP）：首个发消息的微信账号自动绑到 demo，
    # 之后它在微信里的记账与展示软件（demo 账号）同库同清单。
    bound = db.scalars(select(User).where(User.wechat_openid == from_user)).first()
    if bound is not None:
        user_id = bound.id
    else:
        demo_user = db.get(User, "demo")
        if demo_user is not None and not demo_user.wechat_openid:
            demo_user.wechat_openid = from_user
            db.commit()
        user_id = "demo"

    if msg_type == "text":
        content = (msg.get("Content") or "").strip()
        try:
            reply, _actions, _intent = _execute(db, user_id, "wechat", content)
        except Exception as e:
            logger.exception("微信消息处理失败")
            reply = f"处理出错了：{e}"[:200]
        return PlainTextResponse(
            wechat_service.reply_text_xml(from_user, to_user, reply)
        )

    if msg_type == "voice":
        return PlainTextResponse(
            wechat_service.reply_text_xml(
                from_user, to_user, "语音识别还在路上，先用文字发我吧～"
            )
        )

    if msg_type == "event" and msg.get("Event") == "subscribe":
        return PlainTextResponse(
            wechat_service.reply_text_xml(
                from_user, to_user,
                "你好，我是冰箱菇🍄 拍大蘑菇随手记、开门主动问。发文字给我也能记账："
                "试试「放了两盒牛奶」「冰箱里有什么」「要买酱油」。",
            )
        )

    return PlainTextResponse("success")


@router.get("/followers")
def followers():
    """获取关注者 openid 列表（推送目标）。"""
    try:
        return {"openids": wechat_service.list_followers()}
    except wechat_service.WechatError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/push")
def push(openid: str = Query(...), text: str = Query("")):
    """主动推送一条文本消息（测试推送用）。"""
    try:
        wechat_service.send_text(openid, text or "冰箱菇测试推送 ✅")
    except wechat_service.WechatError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}
