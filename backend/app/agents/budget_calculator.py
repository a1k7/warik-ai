from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class BudgetItem:
    category: str
    amount: float
    is_fixed: bool

@dataclass
class SavingsPlan:
    income: float
    fixed_expenses: list[BudgetItem] = field(default_factory=list)
    variable_expenses: list[BudgetItem] = field(default_factory=list)
    total_expenses: float = 0.0
    savings: float = 0.0
    emergency_fund: float = 0.0
    discretionary: float = 0.0
    warnings: list[str] = field(default_factory=list)

def calculate_savings_plan(
    monthly_income: float,
    rent: float = 0.0,
    food: float = 0.0,
    travel: float = 0.0,
    target_savings_percent: float = 20.0,
) -> SavingsPlan:
    if monthly_income <= 0:
        raise ValueError("Monthly income must be positive")

    plan = SavingsPlan(income=monthly_income)

    if rent > 0:
        plan.fixed_expenses.append(BudgetItem("Rent", rent, is_fixed=True))

    if food > 0:
        essential_food = min(food, monthly_income * 0.20)
        plan.fixed_expenses.append(BudgetItem("Food (essential)", essential_food, is_fixed=True))
        if food > essential_food:
            plan.variable_expenses.append(BudgetItem("Food (dining out)", food - essential_food, is_fixed=False))

    if travel > 0:
        plan.variable_expenses.append(BudgetItem("Travel", travel, is_fixed=False))

    total_fixed = sum(i.amount for i in plan.fixed_expenses)
    total_variable = sum(i.amount for i in plan.variable_expenses)
    plan.total_expenses = total_fixed + total_variable

    if plan.total_expenses > monthly_income:
        plan.warnings.append(
            f"Your expenses (₹{plan.total_expenses:,.0f}) exceed your income (₹{monthly_income:,.0f}) by ₹{plan.total_expenses - monthly_income:,.0f}."
        )
        return plan

    remaining = monthly_income - plan.total_expenses
    target_savings = monthly_income * (target_savings_percent / 100.0)
    target_emergency = monthly_income * 0.05

    if remaining >= target_savings + target_emergency:
        plan.savings = target_savings
        plan.emergency_fund = target_emergency
        plan.discretionary = remaining - target_savings - target_emergency
    elif remaining >= target_emergency:
        plan.emergency_fund = target_emergency
        plan.savings = remaining - target_emergency
        plan.discretionary = 0
        if plan.savings < target_savings * 0.5:
            plan.warnings.append("Your savings are below the recommended 20%. Consider reducing discretionary spending.")
    else:
        plan.savings = remaining * 0.5
        plan.emergency_fund = remaining * 0.5
        plan.discretionary = 0
        plan.warnings.append("Your expenses leave very little room for savings. Focus on increasing income or reducing fixed costs.")

    return plan

def format_savings_plan_markdown(plan: SavingsPlan) -> str:
    lines = [
        "## Your Monthly Savings Plan",
        f"**Income:** ₹{plan.income:,.0f}",
        "",
        "### Fixed Expenses",
    ]
    for i in plan.fixed_expenses:
        lines.append(f"- **{i.category}:** ₹{i.amount:,.0f}")

    if plan.variable_expenses:
        lines.append("\n### Variable Expenses")
        for i in plan.variable_expenses:
            lines.append(f"- **{i.category}:** ₹{i.amount:,.0f}")

    total_allocated = plan.total_expenses + plan.savings + plan.emergency_fund + plan.discretionary
    lines.extend([
        "",
        f"**Total Expenses:** ₹{plan.total_expenses:,.0f}",
        "",
        "### Remaining Allocation",
        f"- **Savings:** ₹{plan.savings:,.0f}",
        f"- **Emergency Fund:** ₹{plan.emergency_fund:,.0f}",
        f"- **Discretionary:** ₹{plan.discretionary:,.0f}",
        "",
        f"**Total Accounted For:** ₹{total_allocated:,.0f}",
    ])
    if plan.warnings:
        lines.append("\n### ⚠️ Warnings")
        for w in plan.warnings:
            lines.append(f"- {w}")
    return "\n".join(lines)
