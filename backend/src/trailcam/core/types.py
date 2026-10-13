"""Domain enums shared by every layer (DESIGN §3, §8).

Stored in the database as ``text`` with ``CHECK`` constraints (see ADR 0002), so the values here
are the single source of truth for both Python and SQL.
"""

from __future__ import annotations

from enum import StrEnum


class MediaKind(StrEnum):
    VIDEO = "video"
    PHOTO = "photo"


class MediaStatus(StrEnum):
    DISCOVERED = "discovered"
    HASHED = "hashed"
    PROBED = "probed"
    TIMED = "timed"
    SAMPLED = "sampled"
    EMPTY = "empty"
    MAYBE_EMPTY = "maybe_empty"
    ANIMAL = "animal"
    ERROR = "error"


class TimeSource(StrEnum):
    """Where a media capture time came from (DESIGN §9.3), strongest first."""

    OCR = "ocr"
    CONTAINER = "container"
    FILENAME = "filename"
    EXIF = "exif"
    MTIME = "mtime"
    MANUAL = "manual"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DetectionClass(StrEnum):
    ANIMAL = "animal"
    PERSON = "person"
    VEHICLE = "vehicle"


class DeerClass(StrEnum):
    BUCK = "buck"
    DOE = "doe"
    FAWN = "fawn"
    ANTLERLESS = "antlerless"
    UNKNOWN = "unknown"


class LabelTargetType(StrEnum):
    MEDIA = "media"
    TRACK = "track"
    OBSERVATION = "observation"
    INDIVIDUAL = "individual"


class LabelTrust(StrEnum):
    """Precedence: ground_truth/human labels always beat model output (DESIGN §8)."""

    GROUND_TRUTH = "ground_truth"
    HUMAN = "human"
    MODEL = "model"


class GoldenSplit(StrEnum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


class RutPhase(StrEnum):
    PRE_RUT = "pre_rut"
    SEEKING = "seeking"
    CHASING = "chasing"
    BREEDING = "breeding"
    POST_RUT = "post_rut"
    NONE = "none"
