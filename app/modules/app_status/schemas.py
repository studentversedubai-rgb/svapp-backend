"""
App Status Schemas

Single-row configuration that controls app-wide lockout / alert screens.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


AppStatusMode = Literal['normal', 'maintenance', 'emergency', 'force_update', 'custom']


class AppStatus(BaseModel):
    id: Optional[str] = None
    mode: AppStatusMode = 'normal'

    min_ios_version: Optional[str] = None
    min_android_version: Optional[str] = None
    update_dismissible: bool = True
    update_store_url_ios: Optional[str] = None
    update_store_url_android: Optional[str] = None

    alert_title: Optional[str] = None
    alert_body: Optional[str] = None
    alert_icon: Optional[str] = None
    alert_accent_color: Optional[str] = None
    alert_cta_label: Optional[str] = None
    alert_cta_url: Optional[str] = None
    alert_dismissible: bool = False

    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
