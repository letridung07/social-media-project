from typing import Union, Tuple

# Assuming core.py contains Expression, Constant, Variable
# Assuming operations.py contains Add, Subtract, Negate, Multiply, Power
from .core import Expression, Constant, Variable
from .operations import Add, Subtract, Negate, Multiply, Power

def _get_linear_coeffs(expr: Expression, var: Variable) -> Tuple[Union[Expression, None], Union[Expression, None]]:
    """
    Represents expr as a*var + b.
    Returns (a, b) where 'a' is the coefficient of 'var' and 'b' is the constant part.
    'a' and 'b' are Expressions. 'a' should be constant w.r.t 'var'.
    If expr is not linear in 'var' in this form, returns (None, None).
    Assumes expr is simplified before calling.
    """
    if not isinstance(var, Variable):
        raise TypeError("Solving variable 'var' must be an instance of Variable.")

    # Base cases:
    if isinstance(expr, Constant):
        return (Constant(0), expr)

    if isinstance(expr, Variable):
        if expr == var:
            return (Constant(1), Constant(0))
        else:
            return (Constant(0), expr)

    # Recursive cases for operations:
    if isinstance(expr, Add):
        # Ensure operands are expressions before recursive call
        left_expr = expr.left
        right_expr = expr.right

        a_left, b_left = _get_linear_coeffs(left_expr, var)
        a_right, b_right = _get_linear_coeffs(right_expr, var)

        if a_left is None or a_right is None: return (None, None)

        # Ensure results of additions are simplified
        # The '+' and '-' ops on Expression objects should handle Constant promotion and basic simplification
        a_sum = (a_left + a_right)
        b_sum = (b_left + b_right)
        return (a_sum.simplify(), b_sum.simplify())

    if isinstance(expr, Subtract):
        left_expr = expr.left
        right_expr = expr.right

        a_left, b_left = _get_linear_coeffs(left_expr, var)
        a_right, b_right = _get_linear_coeffs(right_expr, var)

        if a_left is None or a_right is None: return (None, None)

        a_diff = (a_left - a_right)
        b_diff = (b_left - b_right)
        return (a_diff.simplify(), b_diff.simplify())

    if isinstance(expr, Negate):
        operand_expr = expr.operand
        a_operand, b_operand = _get_linear_coeffs(operand_expr, var)

        if a_operand is None: return (None, None)

        # Ensure results of negations are simplified
        neg_a_operand = (-a_operand)
        neg_b_operand = (-b_operand)
        return (neg_a_operand.simplify(), neg_b_operand.simplify())

    if isinstance(expr, Multiply):
        # Check if operands are expressions
        left_expr = expr.left
        right_expr = expr.right

        # Determine if left and right parts are constant with respect to var
        # diff(var) should return Constant(0) if it's constant w.r.t var
        # Need to handle potential string results from diff if not simplified,
        # or ensure diff always returns an Expression. Assuming diff returns Expression.
        is_left_const_wrt_var = (left_expr.diff(var) == Constant(0))
        is_right_const_wrt_var = (right_expr.diff(var) == Constant(0))

        if is_left_const_wrt_var and is_right_const_wrt_var:
            # If both are constant w.r.t var, then expr is constant w.r.t var
            return (Constant(0), expr.simplify())

        elif is_left_const_wrt_var:
            # expr = K * f(var)
            # Coeffs for f(var) = a_f*var + b_f
            a_right, b_right = _get_linear_coeffs(right_expr, var)
            if a_right is None: return (None, None)

            # Coefficient 'a_right' must itself be constant w.r.t. var for K*(a_f*var + b_f) to be linear.
            # e.g. if f(var) = (y*var)*var + c  => a_f = y*var (not const).
            # This check ensures a_right is like a Constant or expression of other variables.
            if not (a_right.diff(var) == Constant(0)): return (None, None)

            # Result: (K*a_f, K*b_f)
            term_a = (left_expr * a_right)
            term_b = (left_expr * b_right)
            return (term_a.simplify(), term_b.simplify())

        elif is_right_const_wrt_var:
            # expr = f(var) * K
            a_left, b_left = _get_linear_coeffs(left_expr, var)
            if a_left is None: return (None, None)

            # Coefficient 'a_left' must itself be constant w.r.t. var.
            if not (a_left.diff(var) == Constant(0)): return (None, None)

            # Result: (a_f*K, b_f*K)
            term_a = (a_left * right_expr)
            term_b = (b_left * right_expr)
            return (term_a.simplify(), term_b.simplify())

        else:
            # Both left and right depend on 'var' in a non-constant way (e.g. var * var)
            return (None, None)

    # Specific check for var^1 and var^0, as general Power.diff(var) might be complex
    # and we need to recognize these simple linear/constant forms.
    if isinstance(expr, Power):
        # Ensure exponent is Constant for these checks
        if expr.left == var and isinstance(expr.right, Constant):
            if expr.right.value == 1: # var^1
                return (Constant(1), Constant(0))
            if expr.right.value == 0: # var^0 = 1
                return (Constant(0), Constant(1))

    # If the expression itself is constant w.r.t. var (e.g. f(y), Constant, Log(c))
    # This should come after specific linear forms (like var^1) are handled.
    # This relies on diff(var) correctly returning Constant(0) for such expressions.
    if expr.diff(var) == Constant(0):
        return (Constant(0), expr) # expr is the 'b' term, 'a' is 0.

    # Default for any other expression type that contains 'var' and is not caught above: non-linear.
    return (None, None)
