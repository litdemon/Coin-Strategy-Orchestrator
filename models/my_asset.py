from pydantic import BaseModel, Field 
from typing import List, Optional
from uuid import uuid4
import time

class AssetItem(BaseModel):
    currency: str
    balance: float
    locked: float

class MyAsset(BaseModel):
    type: str = "myAsset"
    asset_uuid: str = Field(default_factory=lambda: str(uuid4()))
    assets: List[AssetItem]
    asset_timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    stream_type: str = "REALTIME"

    class Config:
        frozen = False
