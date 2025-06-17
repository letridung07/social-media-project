import math
from typing import Union
from .algebra import _get_linear_coeffs # For Expression.solve
from .operations import (
    Add, Subtract, Multiply, Divide, Power,
    Negate, Absolute, Log, Exp
)

# Forward declarations for type hints within Expression class methods
# These will be resolved once all classes are defined or imported.
# For now, some methods in Expression will refer to these names as strings.
# We are defining 'Variable' and 'Constant' in this file, so they don't need forward declaration for each other.
# However, Expression methods use other types like Add, Subtract, Multiply, Divide, Power, Log, Exp, Negate, Absolute.
# These will be unresolved in this file for now.

def _factorial(n):
    """
    Calculates the factorial of a non-negative integer n.
    Raises ValueError if n is negative or not an integer.
    """
    if not isinstance(n, int):
        raise TypeError("Factorial is only defined for integers.")
    # math.factorial already raises ValueError for negative integers.
    # It also handles 0! = 1 correctly.
    return math.factorial(n)

class Expression:
    def __add__(self, other):
        # Promote 'other' to Constant if it's a number
        if not isinstance(other, Expression):
            other = Constant(other)

        # Simplification: Constant(a) + Constant(b) -> Constant(a+b)
        if isinstance(self, Constant) and isinstance(other, Constant):
            return Constant(self.value + other.value)
        # Simplification: expr + Constant(0) -> expr
        if isinstance(other, Constant) and other.value == 0:
            return self
        # Simplification: Constant(0) + expr -> expr
        if isinstance(self, Constant) and self.value == 0:
            return other
        return Add(self, other)

    def __sub__(self, other):
        # Promote 'other' to Constant if it's a number
        if not isinstance(other, Expression):
            other = Constant(other)

        # Simplification: Constant(a) - Constant(b) -> Constant(a-b)
        if isinstance(self, Constant) and isinstance(other, Constant):
            return Constant(self.value - other.value)
        # Simplification: expr - Constant(0) -> expr
        if isinstance(other, Constant) and other.value == 0:
            return self

        if self == other: # Relies on __eq__
            return Constant(0)

        return Subtract(self, other)

    def __mul__(self, other):
        if not isinstance(other, Expression):
            other = Constant(other)
        if isinstance(self, Constant) and isinstance(other, Constant):
            return Constant(self.value * other.value)
        if isinstance(other, Constant) and other.value == 0: return Constant(0)
        if isinstance(self, Constant) and self.value == 0: return Constant(0)
        if isinstance(other, Constant) and other.value == 1: return self
        if isinstance(self, Constant) and self.value == 1: return other
        return Multiply(self, other)

    def __truediv__(self, other):
        if not isinstance(other, Expression):
            other = Constant(other)
        if isinstance(self, Constant) and isinstance(other, Constant):
            if other.value == 0: pass
            else: return Constant(self.value / other.value)
        if isinstance(self, Constant) and self.value == 0:
            if not (isinstance(other, Constant) and other.value == 0): return Constant(0)
        if self == other:
            if isinstance(self, Constant) and self.value == 0: pass
            else: return Constant(1)
        return Divide(self, other)

    def __pow__(self, other):
        if not isinstance(other, Expression):
            other = Constant(other)
        if isinstance(self, Constant) and isinstance(other, Constant):
            if self.value == 0 and other.value < 0: raise ValueError("Cannot raise zero to a negative power.")
            return Constant(self.value ** other.value)
        if isinstance(other, Constant) and other.value == 0: return Constant(1)
        if isinstance(other, Constant) and other.value == 1: return self
        if isinstance(self, Constant) and self.value == 0:
            if isinstance(other, Constant) and other.value > 0: return Constant(0)
        if isinstance(self, Constant) and self.value == 1: return Constant(1)
        return Power(self, other)

    def __radd__(self, other):
        if not isinstance(other, Expression): other = Constant(other)
        return other + self
    def __rsub__(self, other):
        if not isinstance(other, Expression): other = Constant(other)
        return other - self
    def __rmul__(self, other):
        if not isinstance(other, Expression): other = Constant(other)
        return other * self
    def __rtruediv__(self, other):
        if not isinstance(other, Expression): other = Constant(other)
        return other / self
    def __rpow__(self, other):
        if not isinstance(other, Expression): other = Constant(other)
        return other ** self

    def log(self): return Log(self)
    def exp(self): return Exp(self)
    def __neg__(self):
        if isinstance(self, Constant): return Constant(-self.value)
        if isinstance(self, Negate): return self.operand
        return Negate(self)
    def __abs__(self): return Absolute(self)

    def taylor_series(self, variable: 'Variable', expansion_point: Union[int, float], order: int):
        if not isinstance(variable, Variable): raise TypeError("Expansion variable must be an instance of Variable.")
        if not isinstance(expansion_point, (int, float)): raise TypeError("Expansion point must be a number (int or float).")
        if not isinstance(order, int): raise TypeError("Order must be an integer.")
        if order < 0: raise ValueError("Order must be a non-negative integer.")
        current_deriv_expr = self
        taylor_poly = Constant(0)
        expansion_point_const = Constant(expansion_point)
        for k in range(order + 1):
            if k == 0: f_k_a_val = current_deriv_expr.eval(**{variable.name: expansion_point})
            else:
                current_deriv_expr = current_deriv_expr.diff(variable)
                f_k_a_val = current_deriv_expr.eval(**{variable.name: expansion_point})
            factorial_k = _factorial(k)
            term_coeff_val = f_k_a_val / factorial_k if factorial_k != 0 else (0 if f_k_a_val == 0 else float('inf'))
            if term_coeff_val == float('inf'): raise ZeroDivisionError("Factorial resulted in zero division.")
            term_coeff = Constant(term_coeff_val)
            if k == 0: var_part = Constant(1)
            else: var_part = (variable - expansion_point_const) ** Constant(k)
            taylor_poly = taylor_poly + (term_coeff * var_part)
        return taylor_poly

    def diff(self, var: 'Variable'): raise NotImplementedError("Symbolic differentiation not implemented for this expression type.") # Added type hint for consistency
    def eval(self, **kwargs): raise NotImplementedError
    def __str__(self): raise NotImplementedError
    def __repr__(self): return self.__str__()
    def simplify(self): return self
    def integrate(self, var: 'Variable'): raise NotImplementedError("Symbolic integration not implemented for this expression type.")

    def solve(self, variable: 'Variable', target: Union['Expression', int, float, None] = None):
        if not isinstance(variable, Variable): raise TypeError("The 'variable' argument must be an instance of Variable.")
        target_expr: Expression
        if target is None: target_expr = Constant(0); expr_to_solve = self
        elif isinstance(target, (int, float)): target_expr = Constant(target); expr_to_solve = Subtract(self, target_expr)
        elif isinstance(target, Expression): target_expr = target; expr_to_solve = Subtract(self, target_expr)
        else: raise TypeError("Target must be an Expression, number, or None.")
        simplified_expr_to_solve = expr_to_solve.simplify()
        return self._solve_for_zero(simplified_expr_to_solve, variable)

    def _solve_for_zero(self, expr_to_solve: 'Expression', variable: 'Variable'):
        a, b = _get_linear_coeffs(expr_to_solve, variable)
        if a is None: raise NotImplementedError(f"Equation '{str(expr_to_solve)} = 0' is non-linear in '{str(variable)}' or not solvable by this linear method.")
        a_simplified = a.simplify(); b_simplified = b.simplify()
        if isinstance(a_simplified, Constant) and a_simplified.value == 0:
            return ["all_real_numbers"] if isinstance(b_simplified, Constant) and b_simplified.value == 0 else []
        else: return [(Negate(b_simplified) / a_simplified).simplify()]

class Constant(Expression):
    def __init__(self, value): self.value = value
    def diff(self, var: 'Variable'): return Constant(0)
    def eval(self, **kwargs): return self.value
    def __str__(self): return str(self.value)
    def __eq__(self, other): return isinstance(other, Constant) and self.value == other.value if isinstance(other, Constant) else NotImplemented
    def __hash__(self): return hash(self.value)
    def simplify(self): return self
    def integrate(self, var: 'Variable'): return Multiply(self, var)

class Variable(Expression):
    def __init__(self, name: str): self.name = name
    def diff(self, var: 'Variable'): return Constant(1) if self == var else Constant(0)
    def eval(self, **kwargs):
        if self.name not in kwargs: raise ValueError(f"Variable {self.name} not found in evaluation context")
        return kwargs[self.name]
    def __str__(self): return self.name
    def __eq__(self, other): return isinstance(other, Variable) and self.name == other.name if isinstance(other, Variable) else NotImplemented
    def __hash__(self): return hash(self.name)
    def simplify(self): return self
    def integrate(self, var: 'Variable'):
        if self == var: return Divide(Power(self, Constant(2)), Constant(2))
        else: return Multiply(self, var)

# All direct dependencies for Expression methods should now be resolved.
# _get_linear_coeffs is imported from .algebra.
# Operation classes (Add, Subtract, etc.) are imported from .operations.
