from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt

class Parameters(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    seed: tuple[StrictInt, StrictInt, StrictInt] | None = None
    roi: tuple[StrictInt, StrictInt, StrictInt, StrictInt, StrictInt, StrictInt] | None = None
    iterations: int = Field(default=2, ge=0, le=10, strict=True)
    multiplier: float = Field(default=2.0, gt=0, le=10)
    radius: int = Field(default=1, ge=1, le=5, strict=True)
    opening_mm: float = Field(default=1.0, ge=0, le=5)
    # Original V2 always selects the original seed's 3D face-connected component.
    seed_component: Literal[True] = True
    device: Literal['auto', 'cpu', 'cuda'] = 'auto'

class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
    algorithm: Literal['traditional_v2', 'unet_e17']
    parameters: Parameters = Field(default_factory=Parameters)

class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
    ct: str
    gt: str | None = None
