"""设备注册/绑定/心跳（对应开发计划 §5.1）。

TODO(M2)：设备鉴权完善 —— token 校验、MAC 校验、防伪造。
TODO(M3)：配网流程、固件版本上报、OTA。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device
from ..schemas import (
    DeviceBindRequest,
    DeviceHeartbeatRequest,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
)

router = APIRouter(prefix="/device", tags=["设备"])


def _require_device(
    db: Session,
    device_id: str,
    device_token: str,
) -> Device:
    device = db.get(Device, device_id)
    if not device or device.device_token != device_token:
        raise HTTPException(status_code=401, detail="设备鉴权失败")
    return device


@router.post("/register", response_model=DeviceRegisterResponse)
def register(req: DeviceRegisterRequest, db: Session = Depends(get_db)):
    """设备首次上电注册：SN 唯一，已存在则直接返回原 token（幂等）。"""
    device = db.scalar(select(Device).where(Device.device_sn == req.device_sn))
    if device is None:
        device = Device(
            device_sn=req.device_sn,
            device_type=req.device_type,
            mac_address=req.mac_address,
            firmware_version=req.firmware_version,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
    return DeviceRegisterResponse(
        device_id=device.id, device_token=device.device_token
    )


@router.post("/bind")
def bind(req: DeviceBindRequest, db: Session = Depends(get_db)):
    """用户绑定设备（微信扫码/H5 绑定流程会调用）。"""
    device = _require_device(db, req.device_id, req.device_token)
    device.user_id = req.user_id
    db.commit()
    return {"ok": True, "device_id": device.id, "user_id": device.user_id}


@router.post("/heartbeat")
def heartbeat(req: DeviceHeartbeatRequest, db: Session = Depends(get_db)):
    """心跳：更新在线状态。"""
    device = _require_device(db, req.device_id, req.device_token)
    device.online = True
    device.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/status")
def status(req: DeviceHeartbeatRequest, db: Session = Depends(get_db)):
    """状态上报（电量/静音/门磁）。"""
    _require_device(db, req.device_id, req.device_token)
    # TODO(M3)：落库到 device_status 表，用于低电量提醒等
    return {"ok": True, "received": req.model_dump(exclude={"device_id", "device_token"})}
