"""微信测试号服务：access_token 缓存、回调验签、客服消息推送、关注者列表。"""
import hashlib
import logging
import time
import xml.etree.ElementTree as ET

import httpx
from fastapi.responses import PlainTextResponse

from ..config import settings

logger = logging.getLogger(__name__)

API = "https://api.weixin.qq.com/cgi-bin"
_token_cache: dict[str, str] = {"token": "", "expires_at": 0.0}


class WechatError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    if not settings.wechat_appid or not settings.wechat_secret:
        raise WechatError("WECHAT_APPID / WECHAT_SECRET 未配置")
    return settings.wechat_appid, settings.wechat_secret


def get_access_token(force: bool = False) -> str:
    """获取并缓存 access_token（有效期 7200s，提前 120s 刷新）。"""
    now = time.time()
    if not force and _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]
    appid, secret = _credentials()
    r = httpx.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=10,
    )
    data = r.json()
    if "access_token" not in data:
        raise WechatError(f"获取 access_token 失败: {data}")
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 7200)) - 120
    return _token_cache["token"]


def check_signature(signature: str, timestamp: str, nonce: str) -> bool:
    """接口配置验证：sha1(sort(token, timestamp, nonce)) == signature。"""
    if not settings.wechat_token:
        return False
    raw = "".join(sorted([settings.wechat_token, timestamp, nonce]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest() == signature


def parse_message(xml_body: bytes) -> dict:
    """解析微信回调 XML 为 dict（只取常用字段）。"""
    root = ET.fromstring(xml_body)
    return {child.tag: (child.text or "") for child in root}


def reply_text_xml(to_user: str, from_user: str, content: str) -> str:
    """被动回复文本消息 XML。"""
    content = (content or "")[:600]
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


def send_text(openid: str, content: str) -> None:
    """主动推送文本（测试号支持客服消息接口）。"""
    token = get_access_token()
    r = httpx.post(
        f"{API}/message/custom/send?access_token={token}",
        json={"touser": openid, "msgtype": "text", "text": {"content": content[:600]}},
        timeout=10,
    )
    data = r.json()
    if data.get("errcode") not in (0, None):
        raise WechatError(f"推送失败: {data}")


def send_image(openid: str, media_id: str) -> None:
    """主动推送图片（media_id 需先通过素材接口上传）。"""
    token = get_access_token()
    r = httpx.post(
        f"{API}/message/custom/send?access_token={token}",
        json={"touser": openid, "msgtype": "image", "image": {"media_id": media_id}},
        timeout=10,
    )
    data = r.json()
    if data.get("errcode") not in (0, None):
        raise WechatError(f"推送图片失败: {data}")


def upload_image(path: str | bytes, filename: str = "card.png") -> str:
    """上传临时素材（客服消息用），返回 media_id。"""
    token = get_access_token()
    data = path if isinstance(path, bytes) else open(path, "rb").read()
    r = httpx.post(
        f"{API}/media/upload?access_token={token}",
        params={"type": "image"},
        files={"media": (filename, data, "image/png")},
        timeout=15,
    )
    res = r.json()
    if "media_id" not in res:
        raise WechatError(f"上传素材失败: {res}")
    return res["media_id"]


def list_followers() -> list[str]:
    """测试号关注者 openid 列表（配置绑定后，用户关注测试号即可拿到）。"""
    token = get_access_token()
    r = httpx.get(f"{API}/user/get?access_token={token}", timeout=10)
    data = r.json()
    return data.get("data", {}).get("openid", [])


def echo_response(echostr: str) -> PlainTextResponse:
    return PlainTextResponse(echostr)
