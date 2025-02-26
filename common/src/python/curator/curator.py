"""Defines utilities for curating metadata."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AttributeCondition(BaseModel):
    predicate: str
    arguments: Optional[Dict[str, Any]] = None


class ComputeDefinition(BaseModel):
    compute: str
    arguments: Dict[str, Any]


class ValueDefinition(BaseModel):
    attribute: Any


class AnnotatedAttribute(BaseModel):
    attribute: str
    condition: Optional[AttributeCondition | List[AttributeCondition]] = None

    rule: ComputeDefinition | ValueDefinition


class AttributeCurator(BaseModel):
    subject: List[AnnotatedAttribute] = []
    session: List[AnnotatedAttribute] = []
    acquisition: List[AnnotatedAttribute] = []
    file: List[AnnotatedAttribute] = []
