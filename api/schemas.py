"""Request / response models for the prediction API (validated with Pydantic)."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StudentFeatures(BaseModel):
    """One student's mid-semester snapshot. Every field except `previous_semester_score`
    is optional: a missing value is imputed with the training median (the same
    justified-imputation rule used in Part 1) and the matching `*_data_available`
    flag is set to 0 automatically."""

    model_config = ConfigDict(extra="forbid")

    student_id: Optional[str] = Field(None, examples=["STU100123"])

    # multi-source features (Part 1 mart)
    previous_semester_score: float = Field(..., ge=0, le=20, description="Latest score G2 (0-20)")
    avg_internal_marks: Optional[float] = Field(None, ge=0, le=20)
    attendance_pct: Optional[float] = Field(None, ge=0, le=100)
    assignment_completion_rate: Optional[float] = Field(None, ge=0, le=1)
    lms_engagement_score: Optional[float] = Field(None, ge=0, le=100)

    # academic-record features
    studytime: Optional[int] = Field(None, ge=1, le=4)
    failures: Optional[int] = Field(None, ge=0, le=4)
    absences: Optional[int] = Field(None, ge=0, le=100)
    goout: Optional[int] = Field(None, ge=1, le=5)
    Dalc: Optional[int] = Field(None, ge=1, le=5)
    Walc: Optional[int] = Field(None, ge=1, le=5)
    freetime: Optional[int] = Field(None, ge=1, le=5)
    health: Optional[int] = Field(None, ge=1, le=5)
    famrel: Optional[int] = Field(None, ge=1, le=5)
    Medu: Optional[int] = Field(None, ge=0, le=4)
    Fedu: Optional[int] = Field(None, ge=0, le=4)
    age: Optional[int] = Field(None, ge=14, le=30)
    traveltime: Optional[int] = Field(None, ge=1, le=4)

    internet: Optional[int] = Field(None, ge=0, le=1)
    higher: Optional[int] = Field(None, ge=0, le=1)
    schoolsup: Optional[int] = Field(None, ge=0, le=1)
    famsup: Optional[int] = Field(None, ge=0, le=1)
    paid: Optional[int] = Field(None, ge=0, le=1)
    activities: Optional[int] = Field(None, ge=0, le=1)
    romantic: Optional[int] = Field(None, ge=0, le=1)
    is_male: Optional[int] = Field(None, ge=0, le=1)
    is_math: Optional[int] = Field(None, ge=0, le=1)


class Factor(BaseModel):
    feature: str
    label: str
    impact: float = Field(..., description="Change in risk probability vs. a typical student (+ raises risk)")


class Prediction(BaseModel):
    student_id: Optional[str]
    at_risk_probability: float
    at_risk: bool
    risk_band: str
    threshold: float
    top_factors: List[Factor]
    model_version: Optional[str]


class BatchRequest(BaseModel):
    students: List[StudentFeatures] = Field(..., min_length=1, max_length=500)


class BatchResponse(BaseModel):
    count: int
    predictions: List[Prediction]
