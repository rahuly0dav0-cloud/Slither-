"""Turn a parsed SAS program into an ordered execution plan of conversion units.

SAS runs top-to-bottom, so units preserve step order. Each unit is routed to the
Data Engineering or Modelling agent based on the step's category.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.parser.sas_parser import SasProgram, SasStep


@dataclass
class ConversionUnit:
    program: str
    step: SasStep
    agent: str  # "data_engineering" | "modelling"

    @property
    def outputs(self) -> list[str]:
        return self.step.outputs


@dataclass
class ExecutionPlan:
    program: str
    units: list[ConversionUnit]

    def __iter__(self):
        return iter(self.units)

    def __len__(self) -> int:
        return len(self.units)

    @property
    def modelling_units(self) -> list[ConversionUnit]:
        return [u for u in self.units if u.agent == "modelling"]

    @property
    def data_engineering_units(self) -> list[ConversionUnit]:
        return [u for u in self.units if u.agent == "data_engineering"]


def build_plan(program: SasProgram) -> ExecutionPlan:
    units = [ConversionUnit(program.name, step, step.category) for step in program.steps]
    return ExecutionPlan(program=program.name, units=units)
