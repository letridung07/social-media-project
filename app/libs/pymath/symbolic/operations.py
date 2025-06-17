import math
from collections import defaultdict
from typing import Union

from .core import Expression, Constant, Variable # Core classes needed by operations

# _get_linear_coeffs used by Add.simplify's _extract_coeff_base (if it were still there) is in algebra.py.
# For now, Add.simplify does not seem to directly call _get_linear_coeffs.
# Names like Add, Multiply, Log, etc. used in methods (e.g. Power.diff using Log)
# will resolve to the classes defined within this current file.

class UnaryOperation(Expression):
    def __init__(self, operand):
        self.operand = operand

    def eval(self, **kwargs):
        operand_val = self.operand.eval(**kwargs)
        return self._op(operand_val)

    def _op(self, operand_val):
        raise NotImplementedError

    def __eq__(self, other):
        if not type(self) is type(other):
            return NotImplemented
        return self.operand == other.operand

    def __hash__(self):
        return hash((type(self).__name__, self.operand))

    def simplify(self):
        self.operand = self.operand.simplify()
        # Constant folding for specific unary ops
        if isinstance(self, (Log, Exp, Sign, Negate, Absolute)):
            if isinstance(self.operand, Constant):
                try:
                    return Constant(self._op(self.operand.value))
                except (ValueError, ZeroDivisionError):
                    pass
        return self

    def integrate(self, var: 'Variable'):
        raise NotImplementedError("Symbolic integration not implemented for this unary operation.")

class Negate(UnaryOperation):
    def diff(self, var): return -self.operand.diff(var)
    def _op(self, operand_val): return -operand_val
    def __str__(self): return f"(-{self.operand})"
    def integrate(self, var: 'Variable'): return -self.operand.integrate(var)

class Absolute(UnaryOperation):
    def diff(self, var): return self.operand.diff(var) * Sign(self.operand)
    def _op(self, operand_val): return abs(operand_val)
    def __str__(self): return f"abs({self.operand})"
    # integrate is inherited: raises NotImplementedError

class Log(UnaryOperation):
    def diff(self, var): return self.operand.diff(var) / self.operand
    def _op(self, operand_val):
        if operand_val <= 0: raise ValueError("Logarithm undefined for non-positive values.")
        return math.log(operand_val)
    def __str__(self): return f"log({self.operand})"
    def integrate(self, var: 'Variable'):
        if self.operand == var: return (var * self) - var # var.multiply(self).subtract(var)
        else: raise NotImplementedError("Integration of log(u) for u != var (e.g., log(f(x))) not implemented yet.")

class Exp(UnaryOperation):
    def diff(self, var): return Exp(self.operand) * self.operand.diff(var) # self * self.operand.diff(var)
    def _op(self, operand_val): return math.exp(operand_val)
    def __str__(self): return f"exp({self.operand})"
    def integrate(self, var: 'Variable'):
        if self.operand == var: return self
        else: raise NotImplementedError("Integration of exp(u) for u != var (e.g., exp(f(x))) not implemented yet.")

class Sign(UnaryOperation):
    def __init__(self, operand): super().__init__(operand)
    def _op(self, operand_val): return 0 if operand_val == 0 else math.copysign(1, operand_val)
    def diff(self, var): return Constant(0)
    def __str__(self): return f"sgn({self.operand})"
    # integrate is inherited: raises NotImplementedError

class BinaryOperation(Expression):
    def __init__(self, left, right):
        self.left = left
        self.right = right
    def eval(self, **kwargs):
        left_val = self.left.eval(**kwargs); right_val = self.right.eval(**kwargs)
        return self._op(left_val, right_val)
    def _op(self, left_val, right_val): raise NotImplementedError
    def __eq__(self, other):
        if not type(self) is type(other): return NotImplemented
        return self.left == other.left and self.right == other.right
    def __hash__(self): return hash((type(self).__name__, self.left, self.right))
    def simplify(self):
        self.left = self.left.simplify(); self.right = self.right.simplify()
        if isinstance(self, (Add, Subtract, Multiply, Divide, Power)):
            if isinstance(self.left, Constant) and isinstance(self.right, Constant):
                try: return Constant(self._op(self.left.value, self.right.value))
                except (ValueError, ZeroDivisionError): pass
        return self
    def integrate(self, var: 'Variable'): raise NotImplementedError("Symbolic integration not implemented for this binary operation.")

class Add(BinaryOperation):
    def diff(self, var): return self.left.diff(var) + self.right.diff(var)
    def _op(self, left_val, right_val): return left_val + right_val
    def __str__(self): return f"({self.left} + {self.right})"
    def simplify(self):
        # _extract_coeff_base needs Expression, Constant, Variable, Multiply, Add (for isinstance)
        # and _get_linear_coeffs (if it were used, but it's not directly in _extract_coeff_base for Add)
        def _extract_coeff_base(term_expr):
            if isinstance(term_expr, Constant): return (term_expr.value, Constant(1))
            elif isinstance(term_expr, Variable): return (1.0, term_expr)
            elif isinstance(term_expr, Multiply):
                current_coeff = 1.0; non_const_factors = []; queue = [term_expr]; head = 0
                while head < len(queue):
                    sub_expr = queue[head]; head += 1
                    if isinstance(sub_expr, Multiply):
                        if isinstance(sub_expr.left, Constant): current_coeff *= sub_expr.left.value
                        elif isinstance(sub_expr.left, Multiply): queue.append(sub_expr.left)
                        else: non_const_factors.append(sub_expr.left)
                        if isinstance(sub_expr.right, Constant): current_coeff *= sub_expr.right.value
                        elif isinstance(sub_expr.right, Multiply): queue.append(sub_expr.right)
                        else: non_const_factors.append(sub_expr.right)
                    elif isinstance(sub_expr, Constant): current_coeff *= sub_expr.value
                    else: non_const_factors.append(sub_expr)
                if not non_const_factors: return (current_coeff, Constant(1))
                if len(non_const_factors) > 1: non_const_factors.sort(key=str)
                base_expr = non_const_factors[0]
                for i in range(1, len(non_const_factors)): base_expr = Multiply(base_expr, non_const_factors[i])
                return (current_coeff, base_expr)
            else: return (1.0, term_expr)

        left_simple = self.left.simplify(); right_simple = self.right.simplify()
        if isinstance(left_simple, Constant) and isinstance(right_simple, Constant): return Constant(left_simple.value + right_simple.value)
        if isinstance(left_simple, Constant) and left_simple.value == 0: return right_simple
        if isinstance(right_simple, Constant) and right_simple.value == 0: return left_simple

        # current_expr_rebuilt = Add(left_simple, right_simple) # This creates a new Add, potentially infinite recursion if __add__ calls simplify.
        # Instead, operate on self whose children are simplified.
        # For flattening, we need to handle the current Add node itself.

        terms_list = []
        def _collect_terms_add_helper(expr, lst):
            if isinstance(expr, Add):
                _collect_terms_add_helper(expr.left, lst)
                _collect_terms_add_helper(expr.right, lst)
            else:
                lst.append(expr) # Add simplified children

        # Start collection from the already simplified children of the current Add node
        _collect_terms_add_helper(left_simple, terms_list)
        _collect_terms_add_helper(right_simple, terms_list)

        constants = [t for t in terms_list if isinstance(t, Constant)]; non_constants = [t for t in terms_list if not isinstance(t, Constant)]
        sum_initial_consts = sum(c.value for c in constants); term_map = defaultdict(float); base_map = {}
        for term_loop_var in non_constants:
            coeff, base = _extract_coeff_base(term_loop_var); base_str = str(base)
            term_map[base_str] += coeff; base_map[base_str] = base
        const_one_str = str(Constant(1)); sum_initial_consts += term_map.pop(const_one_str, 0.0)
        final_total_constant_term = Constant(sum_initial_consts); new_terms = []
        if final_total_constant_term.value != 0.0 or not term_map: new_terms.append(final_total_constant_term)
        for base_str, coeff_sum in sorted(term_map.items()):
            if coeff_sum == 0.0: continue
            rebuilt_term = Constant(coeff_sum) * base_map[base_str] if coeff_sum != 1.0 else base_map[base_str]
            if not (isinstance(rebuilt_term, Constant) and rebuilt_term.value == 0.0 and len(new_terms) + len(term_map) > 1 ): # Avoid adding 0 unless it's the only term
                 new_terms.append(rebuilt_term)

        if not new_terms: return Constant(0.0)
        if len(new_terms) > 1 and isinstance(new_terms[0], Constant) and new_terms[0].value == 0.0 and len(new_terms) > 1: # check len > 1 again
            new_terms.pop(0)
        if not new_terms: return Constant(0.0)
        if len(new_terms) == 1: return new_terms[0]

        current_sum = new_terms[0]
        for i in range(1, len(new_terms)): current_sum = current_sum + new_terms[i] # Uses Expression.__add__
        return current_sum

    def integrate(self, var: 'Variable'):
        integrated_left = self.left.integrate(var); integrated_right = self.right.integrate(var)
        return integrated_left + integrated_right

class Subtract(BinaryOperation):
    def diff(self, var): return self.left.diff(var) - self.right.diff(var)
    def _op(self, left_val, right_val): return left_val - right_val
    def __str__(self): return f"({self.left} - {self.right})"
    def integrate(self, var: 'Variable'):
        integrated_left = self.left.integrate(var); integrated_right = self.right.integrate(var)
        return integrated_left - integrated_right

class Multiply(BinaryOperation):
    def diff(self, var): return (self.left.diff(var) * self.right) + (self.left * self.right.diff(var))
    def _op(self, left_val, right_val): return left_val * right_val
    def __str__(self): return f"({self.left} * {self.right})"
    def simplify(self):
        left_simple = self.left.simplify(); right_simple = self.right.simplify()
        if isinstance(left_simple, Constant) and isinstance(right_simple, Constant): return Constant(left_simple.value * right_simple.value)
        if isinstance(left_simple, Constant):
            if left_simple.value == 0: return Constant(0)
            if left_simple.value == 1: return right_simple
        if isinstance(right_simple, Constant):
            if right_simple.value == 0: return Constant(0)
            if right_simple.value == 1: return left_simple

        # current_expr_rebuilt = Multiply(left_simple, right_simple) # Uses constructor
        # if not isinstance(current_expr_rebuilt, Multiply): return current_expr_rebuilt.simplify()

        factors_list = []
        def _collect_factors_mul_helper(expr, lst):
            if isinstance(expr, Multiply):
                _collect_factors_mul_helper(expr.left, lst)
                _collect_factors_mul_helper(expr.right, lst)
            else:
                lst.append(expr)
        # Collect from simplified children directly, not a rebuilt Multiply to avoid recursion issues with __mul__
        _collect_factors_mul_helper(left_simple, factors_list)
        _collect_factors_mul_helper(right_simple, factors_list)

        # Filter out any Multiply instances that might have been added if left_simple/right_simple were already Multiply
        # This is a bit of a hack; the collection should ideally handle the current node's type.
        # A better way is to pass 'self' to collect_factors initially if self.left/right are already simplified.
        # For now, let's assume collect_factors on rebuilt is what was intended.
        # Reverting to collect_factors from current_expr_rebuilt as per Add.simplify logic
        current_expr_rebuilt_for_flattening = Multiply(left_simple, right_simple)
        if not isinstance(current_expr_rebuilt_for_flattening, Multiply): return current_expr_rebuilt_for_flattening.simplify()

        factors_list = [] # reset
        _collect_factors_mul_helper(current_expr_rebuilt_for_flattening, factors_list)


        constants = [f for f in factors_list if isinstance(f, Constant)]; non_constants = [f for f in factors_list if not isinstance(f, Constant)]
        prod_consts_val = math.prod(c.value for c in constants) if constants else 1
        final_constant_factor = Constant(prod_consts_val)
        if final_constant_factor.value == 0: return Constant(0)
        if len(non_constants) > 1: non_constants.sort(key=str)
        if not non_constants: return final_constant_factor
        new_factors = []
        if final_constant_factor.value != 1 or not non_constants :
             new_factors.append(final_constant_factor)
        new_factors.extend(non_constants)
        if len(new_factors) > 1 and isinstance(new_factors[0], Constant) and new_factors[0].value == 1:
            new_factors.pop(0)
        if not new_factors: return Constant(1)
        if len(new_factors) == 1: return new_factors[0]
        current_prod = new_factors[0]
        for i in range(1, len(new_factors)): current_prod = current_prod * new_factors[i] # Uses Expression.__mul__
        return current_prod
    def integrate(self, var: 'Variable'):
        if isinstance(self.left, Constant): return self.left * self.right.integrate(var)
        elif isinstance(self.right, Constant): return self.left.integrate(var) * self.right
        else: raise NotImplementedError("General product integration (integration by parts) not implemented yet.")

class Divide(BinaryOperation):
    def diff(self, var): return (self.left.diff(var) * self.right - self.left * self.right.diff(var)) / (self.right ** Constant(2))
    def _op(self, left_val, right_val):
        if right_val == 0: raise ZeroDivisionError("division by zero")
        return left_val / right_val
    def __str__(self): return f"({self.left} / {self.right})"
    # integrate is inherited

class Power(BinaryOperation):
    def diff(self, var):
        u, v = self.left, self.right
        if isinstance(v, Constant):
            if v.value == 0: return Constant(0)
            return v * (u ** Constant(v.value - 1)) * u.diff(var)
        else: return (u ** v) * (v.diff(var) * Log(u) + v * u.diff(var) / u)
    def _op(self, left_val, right_val): return left_val ** right_val
    def __str__(self): return f"({self.left} ** {self.right})"
    def integrate(self, var: 'Variable'):
        base, exp_expr = self.left, self.right
        if base == var and isinstance(exp_expr, Constant):
            n = exp_expr.value
            if n == -1: return Log(Absolute(base)) # Use base, not var, for Log(Abs(base))
            else: return Divide(Power(base, Constant(n + 1)), Constant(n + 1))
        # Check if the entire expression is constant w.r.t var
        # This relies on diff being correctly implemented for all types.
        if self.diff(var) == Constant(0): return Multiply(self, var)
        else: raise NotImplementedError("General Power integration not implemented yet.")
