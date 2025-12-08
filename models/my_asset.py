from pydantic import BaseModel
from typing import List, Optional

class AssetItem(BaseModel):
    currency: str
    balance: float
    locked: float

class MyAsset(BaseModel):
    type: str  # "myAsset"
    asset_uuid: str
    assets: List[AssetItem]
    asset_timestamp: int
    timestamp: int
    stream_type: str

    class Config:
        frozen = False
