"""Local training API: explicit start intent, bounded engineering runs."""
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class LiveTrainingEvent(BaseModel):
    """v2 envelope; adapter fields extend the common historical event vocabulary."""
    model_config=ConfigDict(extra='allow',allow_inf_nan=False)
    schema_version: Literal[2]=2
    run_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    sequence: int = Field(ge=1,strict=True)
    event_id: str
    timestamp: AwareDatetime
    event_type: Literal['status','log','batch','metric','checkpoint','epoch_start','epoch_end','validation_end','resumed','terminal']
    epoch: int = Field(ge=0,strict=True)
    step: int | None = Field(default=None,ge=0,strict=True)

    @model_validator(mode='after')
    def identity(self):
        if self.event_id!=f'{self.run_id}:{self.sequence}':raise ValueError('Event identity mismatch')
        return self


class TrainingConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    adapter: Literal['monai-resunet-v1'] = 'monai-resunet-v1'
    dataset: Literal['course', 'registered'] = 'course'
    train_ids: list[str] = Field(default_factory=list, max_length=100)
    val_ids: list[str] = Field(default_factory=list, max_length=100)
    patient_ids: dict[str,str] = Field(default_factory=dict, max_length=100)
    epochs: int = Field(default=50, ge=1, le=60, strict=True)
    batch_size: int = Field(default=4, ge=1, le=4, strict=True)
    learning_rate: float = Field(default=.001, gt=0, le=.01)
    seed: int = Field(default=42, ge=0, le=2**31-1, strict=True)
    patience: int = Field(default=10, ge=1, le=60, strict=True)
    min_delta: float = Field(default=.0001, ge=0, le=1)
    amp: bool = True
    device: Literal['cpu', 'cuda'] = 'cuda'
    checkpoint_policy: Literal['last_best', 'every_epoch'] = 'last_best'
    preview_every: int = Field(default=1, ge=1, le=60, strict=True)
    engineering_smoke: bool = False
    max_train_batches: int | None = Field(default=None, ge=1, le=8, strict=True)

    @model_validator(mode='after')
    def bounds(self):
        if self.amp and self.device != 'cuda':
            raise ValueError('AMP requires CUDA / AMP需要CUDA')
        if self.engineering_smoke:
            if self.epochs > 3 or self.max_train_batches is None:
                raise ValueError('Engineering smoke: at most 3 epochs and 1–8 batches / 工程短训练最多3轮、每轮1–8批')
        elif self.max_train_batches is not None:
            raise ValueError('Batch cap requires engineering smoke / 批次上限仅限工程短训练')
        return self


class StartTraining(BaseModel):
    model_config = ConfigDict(extra='forbid')
    config: TrainingConfig
    preflight_id: str
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    confirm: Literal['START REAL TRAINING']
    resume_run_id: str | None = None
    checkpoint: Literal['last.pt', 'best.pt'] = 'last.pt'


class ResumePreflight(BaseModel):
    config: TrainingConfig
    resume_run_id: str | None = None
    checkpoint: Literal['last.pt', 'best.pt'] = 'last.pt'
