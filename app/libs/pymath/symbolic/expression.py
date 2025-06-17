import math
from collections import defaultdict

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

        # Simplification: expr - expr -> Constant(0)
        # This relies on __eq__ being implemented for operands.
        if self == other:
            return Constant(0)

        return Subtract(self, other)

    def __mul__(self, other):
        # Promote 'other' to Constant if it's a number
        if not isinstance(other, Expression):
            other = Constant(other)

        # Simplification: Constant(a) * Constant(b) -> Constant(a*b)
        if isinstance(self, Constant) and isinstance(other, Constant):
            return Constant(self.value * other.value)
        # Simplification: expr * Constant(0) -> Constant(0)
        if isinstance(other, Constant) and other.value == 0:
            return Constant(0)
        # Simplification: Constant(0) * expr -> Constant(0)
        if isinstance(self, Constant) and self.value == 0:
            return Constant(0)
        # Simplification: expr * Constant(1) -> expr
        if isinstance(other, Constant) and other.value == 1:
            return self
        # Simplification: Constant(1) * expr -> expr
        if isinstance(self, Constant) and self.value == 1:
            return other
        return Multiply(self, other)

    def __truediv__(self, other):
        # Promote 'other' to Constant if it's a number
        if not isinstance(other, Expression):
            other = Constant(other)

        # Simplification: Constant(a) / Constant(b) -> Constant(a/b)
        if isinstance(self, Constant) and isinstance(other, Constant):
            if other.value == 0:
                # This case will be caught by BinaryOperation.eval -> _op for Divide
                # Or we can raise it here. For now, let _op handle it during evaluation.
                pass # Fall through to Divide(self, other)
            else:
                return Constant(self.value / other.value)
        # Simplification: Constant(0) / expr -> Constant(0) (if other is not 0)
        if isinstance(self, Constant) and self.value == 0:
            # We need to ensure 'other' is not Constant(0).
            # If 'other' is Constant(0), Division by zero will be handled by Divide._op
            if not (isinstance(other, Constant) and other.value == 0):
                 return Constant(0)

        # Simplification: expr / expr -> Constant(1), carefully handling 0/0
        if self == other:
            # Check if 'self' (and therefore 'other') is Constant(0)
            if isinstance(self, Constant) and self.value == 0:
                # Let Divide(Constant(0), Constant(0)) handle this case.
                # This will typically lead to a ZeroDivisionError upon evaluation.
                pass
            else:
                # For any other expr / expr where expr is not Constant(0), result is 1.
                return Constant(1)

        return Divide(self, other)

    def __pow__(self, other):
        # Promote 'other' to Constant if it's a number
        if not isinstance(other, Expression):
            other = Constant(other)

        # Simplification: Constant(a) ** Constant(b) -> Constant(a**b)
        if isinstance(self, Constant) and isinstance(other, Constant):
            # Add checks for math domain errors e.g. (-1)**0.5
            if self.value == 0 and other.value < 0: # 0**-ve is an error
                raise ValueError("Cannot raise zero to a negative power.")
            # Python's ** handles 0**0 = 1, and 0**positive = 0 correctly.
            return Constant(self.value ** other.value)
        # Simplification: expr ** Constant(0) -> Constant(1)
        if isinstance(other, Constant) and other.value == 0:
            return Constant(1)
        # Simplification: expr ** Constant(1) -> expr
        if isinstance(other, Constant) and other.value == 1:
            return self
        # Simplification: Constant(0) ** expr -> Constant(0)
        # (assuming expr is positive, for now only if other is a positive Constant)
        if isinstance(self, Constant) and self.value == 0:
            if isinstance(other, Constant) and other.value > 0:
                return Constant(0)
            # If 'other' is not a constant or is not positive, don't simplify yet.
            # More complex check like other.eval() > 0 is too much for __pow__
        # Simplification: Constant(1) ** expr -> Constant(1)
        if isinstance(self, Constant) and self.value == 1:
            return Constant(1)
        return Power(self, other)

    # Reflected operations for cases like int + Expression
    def __radd__(self, other):
        # other + self
        if not isinstance(other, Expression):
            other = Constant(other)
        return other + self # Calls other.__add__(self), which will use Expression.__add__ if other is Constant

    def __rsub__(self, other):
        # other - self
        if not isinstance(other, Expression):
            other = Constant(other)
        return other - self

    def __rmul__(self, other):
        # other * self
        if not isinstance(other, Expression):
            other = Constant(other)
        return other * self

    def __rtruediv__(self, other):
        # other / self
        if not isinstance(other, Expression):
            other = Constant(other)
        return other / self

    def __rpow__(self, other):
        # other ** self
        if not isinstance(other, Expression):
            other = Constant(other)
        return other ** self

    def log(self):
        """Returns the natural logarithm of this expression."""
        return Log(self)

    def exp(self):
        """Returns the exponential of this expression (e^self)."""
        return Exp(self)

    def __neg__(self):
        # Simplification: -Constant(a) -> Constant(-a)
        if isinstance(self, Constant):
            return Constant(-self.value)
        # Simplification: -(-expr) -> expr
        if isinstance(self, Negate):
            return self.operand
        return Negate(self)

    def __abs__(self):
        return Absolute(self)

    def taylor_series(self, variable, expansion_point, order):
        """
        Computes the Taylor series expansion of this expression.

        Args:
            variable (Variable): The variable of the expansion.
            expansion_point (float or int): The point 'a' around which to expand.
            order (int): The order of the Taylor polynomial (non-negative integer).

        Returns:
            Expression: The Taylor polynomial as an Expression object.

        Raises:
            TypeError: If input types are incorrect.
            ValueError: If order is negative.
        """
        if not isinstance(variable, Variable):
            raise TypeError("Expansion variable must be an instance of Variable.")
        if not isinstance(expansion_point, (int, float)):
            raise TypeError("Expansion point must be a number (int or float).")
        if not isinstance(order, int):
            raise TypeError("Order must be an integer.")
        if order < 0:
            raise ValueError("Order must be a non-negative integer.")

        current_deriv_expr = self
        taylor_poly = Constant(0)

        expansion_point_const = Constant(expansion_point)

        for k in range(order + 1):
            # Calculate f_k_a_val (k-th derivative evaluated at expansion_point)
            if k == 0:
                f_k_a_val = current_deriv_expr.eval(**{variable.name: expansion_point})
            else:
                current_deriv_expr = current_deriv_expr.diff(variable)
                f_k_a_val = current_deriv_expr.eval(**{variable.name: expansion_point})

            # Calculate factorial_k
            try:
                factorial_k = _factorial(k)
            except ValueError as e: # Should not happen for non-negative k
                raise ValueError(f"Error calculating factorial for k={k}: {e}")

            if factorial_k == 0: # Should ideally not happen for k>=0
                # This case might occur if _factorial had an issue, though unlikely for k>=0
                # Or if f_k_a_val is 0, then this term is 0 anyway.
                # If f_k_a_val is non-zero and factorial_k is zero, it's an issue.
                # For k>=0, factorial_k is always >=1.
                # For safety, if we want to handle it:
                if f_k_a_val != 0:
                     raise ZeroDivisionError(f"Factorial of {k} is zero, leading to division by zero.")
                term_coeff_val = 0 # if f_k_a_val is also 0
            else:
                term_coeff_val = f_k_a_val / factorial_k

            term_coeff = Constant(term_coeff_val)

            # Calculate var_part = (variable - expansion_point)**k
            if k == 0:
                var_part = Constant(1)  # (x-a)^0 = 1
            else:
                # (variable - Constant(expansion_point))
                term_base = variable - expansion_point_const
                var_part = term_base ** Constant(k)

            current_term = term_coeff * var_part
            taylor_poly = taylor_poly + current_term

        return taylor_poly

    def diff(self, var):
        raise NotImplementedError

    def eval(self, **kwargs):
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError

    def __repr__(self):
        return self.__str__()

    def simplify(self):
        """
        Recursively simplifies the expression.
        Default implementation returns self.
        """
        return self

    def integrate(self, var: 'Variable'):
        """Symbolically integrates the expression with respect to 'var'."""
        raise NotImplementedError("Symbolic integration not implemented for this expression type.")


class Constant(Expression):
    def __init__(self, value):
        self.value = value

    def diff(self, var):
        return Constant(0)

    def eval(self, **kwargs):
        return self.value

    def __str__(self):
        return str(self.value)

    def __eq__(self, other):
        if not isinstance(other, Constant):
            return NotImplemented
        return self.value == other.value

    def __hash__(self):
        return hash(self.value)

    def simplify(self):
        """Simplifies a constant, which is just itself."""
        return self

    def integrate(self, var: 'Variable'):
        """
        Integrates a constant c with respect to var, returning c*var.
        Example: integrate(Constant(5), Variable('x')) -> Multiply(Constant(5), Variable('x'))
        """
        # __mul__ will handle Constant(0)*var -> Constant(0) and Constant(1)*var -> var
        return Multiply(self, var)


class Variable(Expression):
    def __init__(self, name):
        self.name = name

    def diff(self, var):
        if self.name == var.name:
            return Constant(1)
        return Constant(0)

    def eval(self, **kwargs):
        if self.name not in kwargs:
            raise ValueError(f"Variable {self.name} not found in evaluation context")
        return kwargs[self.name]

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Variable):
            return NotImplemented
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def simplify(self):
        """Simplifies a variable, which is just itself."""
        return self

    def integrate(self, var: 'Variable'):
        """
        Integrates a variable.
        If integrating 'x' w.r.t 'x', returns x^2/2.
        If integrating 'y' w.r.t 'x', returns y*x.
        """
        if self == var:
            # Integral of x dx is x^2 / 2
            return Divide(Power(self, Constant(2)), Constant(2))
        else:
            # Integral of y dx (where y is a variable different from x) is y*x
            return Multiply(self, var)


class Variable(Expression): # This class definition seems duplicated in the prompt, will only modify the first one.
    def __init__(self, name):
        self.name = name

    def diff(self, var):
        if self.name == var.name:
            return Constant(1)
        return Constant(0)

    def eval(self, **kwargs):
        if self.name not in kwargs:
            raise ValueError(f"Variable {self.name} not found in evaluation context")
        return kwargs[self.name]

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Variable):
            return NotImplemented
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def simplify(self):
        """Simplifies a variable, which is just itself."""
        return self


class BinaryOperation(Expression):
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def eval(self, **kwargs):
        left_val = self.left.eval(**kwargs)
        right_val = self.right.eval(**kwargs)
        return self._op(left_val, right_val)

    def _op(self, left_val, right_val):
        raise NotImplementedError

    def __eq__(self, other):
        if not type(self) is type(other): # Ensures it's the exact same class, e.g. Add == Add
            return NotImplemented
        # Relies on operand __eq__ being defined for recursive comparison.
        return self.left == other.left and self.right == other.right

    def __hash__(self):
        return hash((type(self).__name__, self.left, self.right))

    def simplify(self):
        """
        Simplifies a binary operation by simplifying operands and then potentially itself.
        """
        self.left = self.left.simplify()
        self.right = self.right.simplify()

        # Constant folding: if both operands are constants, evaluate the operation.
        # Specific binary operation classes (Add, Multiply, etc.) are expected to
        # have more advanced simplification rules in their __init__ or dedicated simplify.
        # This is a general fallback for BinaryOperation.
        if isinstance(self, (Add, Subtract, Multiply, Divide, Power)):
            if isinstance(self.left, Constant) and isinstance(self.right, Constant):
                try:
                    # self._op is defined in concrete classes like Add, Multiply etc.
                    return Constant(self._op(self.left.value, self.right.value))
                except (ValueError, ZeroDivisionError):
                    # If evaluation fails (e.g., log of negative, division by zero),
                    # the expression cannot be simplified to a single constant here.
                    pass # Return self as is
        return self

    def integrate(self, var: 'Variable'):
        """Base implementation for integrating binary operations."""
        raise NotImplementedError("Symbolic integration not implemented for this binary operation.")


class Add(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) + self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val + right_val

    def __str__(self):
        return f"({self.left} + {self.right})"

    def simplify(self):

        def _extract_coeff_base(term):
            if isinstance(term, Constant):
                return (term.value, Constant(1)) # Base for a pure constant is 1
            elif isinstance(term, Variable):
                return (1.0, term) # Return float for coefficient consistency
            elif isinstance(term, Multiply):
                current_coeff = 1.0
                non_const_factors = []
                queue = [term]
                head = 0
                while head < len(queue):
                    sub_expr = queue[head]
                    head += 1
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
            else:
                return (1.0, term) # Return float for coefficient consistency

        # First, simplify operands
        left_simple = self.left.simplify()
        right_simple = self.right.simplify()

        # Initial constant folding (already in __add__ but good to have in simplify too)
        if isinstance(left_simple, Constant) and isinstance(right_simple, Constant):
            return Constant(left_simple.value + right_simple.value)
        if isinstance(left_simple, Constant) and left_simple.value == 0:
            return right_simple
        if isinstance(right_simple, Constant) and right_simple.value == 0:
            return left_simple

        # For Add, we use the simplified operands to reconstruct if no further specific Add rules apply here
        # The __add__ method itself handles some simplifications.
        # If we always returned Add(left_simple, right_simple), we might bypass those.
        # However, the goal here is to flatten and collect.

        current_expr_rebuilt = Add(left_simple, right_simple)
        if not isinstance(current_expr_rebuilt, Add): # If __add__ simplified it to not be an Add anymore
            return current_expr_rebuilt.simplify() # Simplify further if possible (e.g. x + (-x) became 0)

        # Flattening: Collect all terms from nested Add operations
        terms = []
        # Helper to collect terms from an expression
        def collect_terms(expr, term_list):
            if isinstance(expr, Add):
                # Ensure we are collecting from already simplified operands if possible
                # This means the collect_terms will operate on the structure *after* initial simplification
                collect_terms(expr.left, term_list) # expr.left here is from current_expr_rebuilt
                collect_terms(expr.right, term_list)
            else:
                term_list.append(expr)

        # We collect from the potentially reconstructed Add(left_simple, right_simple)
        # to ensure we're working with the structure after initial __add__ simplifications.
        collect_terms(current_expr_rebuilt, terms)

        # Separate constants and non-constants
        constants = [term for term in terms if isinstance(term, Constant)]
        non_constants = [term for term in terms if not isinstance(term, Constant)]

        # Sum constants from initial flattening
        sum_of_initial_constants_val = sum(c.value for c in constants)
        # 'non_constants' is the list of terms that were not Constant after initial pass

        # --- Collect like terms ---
        term_map = defaultdict(float)
        base_objects_map = {}

        for term in non_constants:
            coeff_val, base_expr = _extract_coeff_base(term)
            base_expr_str = str(base_expr)
            term_map[base_expr_str] += coeff_val
            if base_expr_str not in base_objects_map:
                 base_objects_map[base_expr_str] = base_expr

        const_one_str = str(Constant(1))
        if const_one_str in term_map:
            sum_of_initial_constants_val += term_map[const_one_str]
            del term_map[const_one_str]

        final_total_constant_term = Constant(sum_of_initial_constants_val)

        new_terms = []
        if final_total_constant_term.value != 0.0 or not term_map:
            new_terms.append(final_total_constant_term)

        # Sort term_map items by base_expr_str for canonical order of non-constant terms
        sorted_term_map_items = sorted(term_map.items(), key=lambda item: item[0])

        for base_expr_str, summed_coeff_val in sorted_term_map_items:
            if summed_coeff_val == 0.0:
                continue
            base_expr = base_objects_map[base_expr_str]
            if summed_coeff_val == 1.0:
                new_terms.append(base_expr)
            else:
                new_terms.append(Constant(summed_coeff_val) * base_expr)

        # Final cleanup and reconstruction
        if not new_terms: return Constant(0.0)

        # Remove Constant(0.0) if it's not the only term.
        # This can happen if final_total_constant_term was 0.0 but other terms existed.
        if len(new_terms) > 1 and isinstance(new_terms[0], Constant) and new_terms[0].value == 0.0:
            new_terms.pop(0)

        if not new_terms: return Constant(0.0) # Should not happen if logic is correct
        if len(new_terms) == 1: return new_terms[0]

        current_sum = new_terms[0]
        for i in range(1, len(new_terms)):
            current_sum = current_sum + new_terms[i]

        return current_sum


class Subtract(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) - self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val - right_val

    def __str__(self):
        return f"({self.left} - {self.right})"

    def integrate(self, var: 'Variable'):
        """Integrates a subtraction: Integral(f-g)dx = Integral(f)dx - Integral(g)dx."""
        integrated_left = self.left.integrate(var)
        integrated_right = self.right.integrate(var)
        # The __sub__ operator (Expression.__sub__) will handle potential simplifications.
        return integrated_left - integrated_right


class Multiply(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) * self.right + self.left * self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val * right_val

    def __str__(self):
        return f"({self.left} * {self.right})"

    def simplify(self):
        # First, simplify operands
        left_simple = self.left.simplify()
        right_simple = self.right.simplify()

        # Initial constant folding & zero/one product (already in __mul__ but good for self-containment)
        if isinstance(left_simple, Constant) and isinstance(right_simple, Constant):
            return Constant(left_simple.value * right_simple.value)
        # Check for multiplication by 0 or 1 (handled by __mul__, but explicit here for clarity in simplify logic)
        if isinstance(left_simple, Constant):
            if left_simple.value == 0: return Constant(0)
            if left_simple.value == 1: return right_simple # Already simplified
        if isinstance(right_simple, Constant):
            if right_simple.value == 0: return Constant(0)
            if right_simple.value == 1: return left_simple # Already simplified

        # Reconstruct with simplified operands to leverage __mul__ simplifications
        current_expr_rebuilt = Multiply(left_simple, right_simple)
        if not isinstance(current_expr_rebuilt, Multiply): # If __mul__ simplified it (e.g. to Constant(0) or one of operands)
            return current_expr_rebuilt.simplify() # Simplify further if possible

        # Flattening: Collect all factors from nested Multiply operations
        factors = []
        def collect_factors(expr, factor_list):
            if isinstance(expr, Multiply):
                collect_factors(expr.left, factor_list)
                collect_factors(expr.right, factor_list)
            else:
                factor_list.append(expr)

        collect_factors(current_expr_rebuilt, factors)

        # Separate constants and non-constants
        constants = [factor for factor in factors if isinstance(factor, Constant)]
        non_constants = [factor for factor in factors if not isinstance(factor, Constant)]

        # Multiply constants
        product_of_constants_val = 1
        for const_factor in constants:
            product_of_constants_val *= const_factor.value

        final_constant_factor = Constant(product_of_constants_val)

        if final_constant_factor.value == 0:
            return Constant(0) # Entire product is 0

        # Sort non-constant factors for a canonical form
        if len(non_constants) > 1:
            non_constants.sort(key=str)

        # If all factors were constants (already handled if product is 0)
        if not non_constants:
            return final_constant_factor # This will be Constant(product_of_constants_val)

        # Build the new list of factors, deciding whether to include the constant factor
        new_factors = []
        if final_constant_factor.value != 1:
            new_factors.append(final_constant_factor)

        new_factors.extend(non_constants) # Add sorted non-constant factors

        # If the list is empty at this point (e.g. only factor was Constant(1) and no non_constants),
        # the result is Constant(1). This case is covered if not non_constants returned final_constant_factor (which was 1).
        # If new_factors ended up containing only Constant(1) because non_constants was empty and final_constant_factor was 1,
        # or if non_constants became empty and the only remaining factor is Constant(1) after the extend.
        # More directly:
        if not new_factors: # This would happen if non_constants was empty and final_constant_factor was 1
             return Constant(1)

        if len(new_factors) == 1:
            return new_factors[0]

        # Rebuild the Multiply expression from the new factors using __mul__
        # This will ensure left-associativity for ((a*b)*c) structure from the list.
        current_product = new_factors[0]
        for i in range(1, len(new_factors)):
            current_product = current_product * new_factors[i] # Leverages __mul__ for its own simplifications

        return current_product

    def integrate(self, var: 'Variable'):
        """
        Integrates a product. Only handles Constant Factor Rule: Int(c*f)dx = c*Int(f)dx.
        General product integration (integration by parts) is not implemented yet.
        """
        if isinstance(self.left, Constant):
            # Case: Constant * f(var) -> Constant * Integral(f(var) dx)
            # __mul__ will handle if self.left is 0 or 1.
            return self.left * self.right.integrate(var)
        elif isinstance(self.right, Constant):
            # Case: f(var) * Constant -> Integral(f(var) dx) * Constant
            # __mul__ will handle if self.right is 0 or 1.
            return self.left.integrate(var) * self.right
        else:
            # Case: f(var) * g(var) (general product)
            raise NotImplementedError("General product integration (integration by parts) not implemented yet.")


class Divide(BinaryOperation):
    def diff(self, var):
        return (self.left.diff(var) * self.right - self.left * self.right.diff(var)) / (self.right ** Constant(2))

    def _op(self, left_val, right_val):
        if right_val == 0:
            raise ZeroDivisionError("division by zero")
        return left_val / right_val

    def __str__(self):
        return f"({self.left} / {self.right})"


class Power(BinaryOperation):
    def diff(self, var):
        u = self.left
        v = self.right

        if isinstance(v, Constant):
            # Simpler power rule: d/dx(u^c) = c * u^(c-1) * u'
            # Ensure exponent is not zero, though u^0 simplifies to 1, and 1.diff() is 0.
            # This rule is fine even if v.value is 0 or 1 due to how simplifications work.
            # e.g. if v.value = 1, then v-1 = 0, u**0 = 1. Result c * 1 * u' = u'
            # if v.value = 0, then result is 0 * u^-1 * u' = 0. Correct, as u^0=1, 1.diff()=0.

            # Handle 0^0 case for derivative of u^0 where u might become 0.
            # If u is Constant(0) and v is Constant(0), (0^0).diff() should be 0.
            # This is handled by (u**v) simplification to Constant(1) then Constant(1).diff() -> Constant(0).
            # If v is Constant(0), self simplifies to Constant(1), whose diff is Constant(0).
            # The __pow__ simplification handles this before diff is called.
            # So, if we reach here and v is Constant(0), it means u was not simplified away.
            if v.value == 0: # Should have been simplified to Constant(1), so diff is Constant(0)
                return Constant(0)

            # c * u^(c-1) * u'
            c = v
            # Need to handle c-1 potentially being non-integer.
            # Constant(v.value - 1) is fine.
            # u ** Constant(v.value - 1) will create a Power expression.
            return c * (u ** Constant(v.value - 1)) * u.diff(var)
        else:
            # General power rule: d/dx(u^v) = u^v * (v' * ln(u) + v * u'/u)
            # u^v = exp(v * ln(u))
            # d/dx(exp(v * ln(u))) = exp(v * ln(u)) * d/dx(v * ln(u))
            # d/dx(v * ln(u)) = v' * ln(u) + v * (u'/u)

            # (u^v) * (v' * ln(u) + v * u'/u)
            term1 = v.diff(var) * u.log()
            term2 = v * (u.diff(var) / u)
            return (u ** v) * (term1 + term2)

    def _op(self, left_val, right_val):
        return left_val ** right_val

    def __str__(self):
        return f"({self.left} ** {self.right})"

    def integrate(self, var: 'Variable'):
        """
        Integrates a power. Handles Int(x^n)dx and Int(K)dx (where K is const w.r.t var).
        K can be c^k or f(y)^k if var is x.
        """
        expr_base = self.left
        exponent = self.right

        # Case 1: x^n (base is the integration variable, exponent is constant)
        if expr_base == var and isinstance(exponent, Constant):
            n = exponent.value
            if n == -1:
                # Integral of x^-1 dx is Log(|x|)
                return Log(Absolute(var))
            else:
                # Integral of x^n dx is x^(n+1) / (n+1)
                new_exponent = Constant(n + 1)
                denominator = Constant(n + 1)
                # Denominator being zero (n=-1) is handled above.
                return Divide(Power(var, new_exponent), denominator)

        # Case 2: The entire Power expression self is constant w.r.t. var
        # This covers c^k, f(y)^k (where var is x), etc.
        # Check if self.diff(var) is Constant(0).
        # Need to be careful not to call self.diff(var) if var is not in self,
        # as diff might not be fully implemented for all types yet or might be complex.
        # A more direct check: are base and exponent constant w.r.t var?

        # Simplified check for "is self constant w.r.t. var"
        # This relies on diff working correctly for base and exponent.
        # If base.diff(var) is 0 AND exponent.diff(var) is 0, then self is constant w.r.t var.
        # However, a more direct check is if self.diff(var) itself is Constant(0)

        # Let's use the diff check on the whole expression as it's more general
        # We need to ensure Constant(0) comparison works (it should with __eq__)
        if self.diff(var) == Constant(0):
             # The whole expression self (e.g. c^k, or f(y)^k if var is x) is a constant w.r.t var.
             # Integral of a constant K is K*var
            return Multiply(self, var)

        # Case 3: Other cases (e.g., f(x)^n general u-sub, c^f(x))
        else:
            raise NotImplementedError(
                "General Power integration (e.g., u-substitution for f(x)^n "
                "or integration of c^f(x)) not implemented yet."
            )


class UnaryOperation(Expression):
    def __init__(self, operand):
        self.operand = operand

    def eval(self, **kwargs):
        operand_val = self.operand.eval(**kwargs)
        return self._op(operand_val)

    def _op(self, operand_val):
        raise NotImplementedError

    def __eq__(self, other):
        if not type(self) is type(other): # Ensures it's the exact same class, e.g. Log == Log
            return NotImplemented
        # Relies on operand __eq__ being defined for recursive comparison.
        return self.operand == other.operand

    def __hash__(self):
        return hash((type(self).__name__, self.operand))

    def simplify(self):
        """
        Simplifies a unary operation by simplifying its operand and then potentially itself.
        """
        self.operand = self.operand.simplify()

        # Constant folding: if operand is a constant, evaluate the operation.
        # Specific unary operation classes (Log, Exp, etc.) might have more
        # advanced simplification rules (e.g. Log(Exp(x)) -> x) in their __init__ or simplify.
        # This is a general fallback for UnaryOperation.
        if isinstance(self, (Log, Exp, Sign, Negate, Absolute)): # Check relevant UnaryOps
            if isinstance(self.operand, Constant):
                try:
                    # self._op is defined in concrete classes like Log, Exp etc.
                    return Constant(self._op(self.operand.value))
                except (ValueError, ZeroDivisionError):
                    # If evaluation fails (e.g., log of negative),
                    # the expression cannot be simplified to a single constant here.
                    pass # Return self as is
        return self

    def integrate(self, var: 'Variable'):
        """Base implementation for integrating unary operations."""
        raise NotImplementedError("Symbolic integration not implemented for this unary operation.")


class Negate(UnaryOperation):
    def diff(self, var):
        return -self.operand.diff(var)

    def _op(self, operand_val):
        return -operand_val

    def __str__(self):
        return f"(-{self.operand})"

    def integrate(self, var: 'Variable'):
        """Integrates a negation: Integral(-f)dx = -Integral(f)dx."""
        integrated_operand = self.operand.integrate(var)
        # Using the unary minus operator will call Expression.__neg__,
        # which correctly constructs a Negate object and handles simplifications.
        return -integrated_operand


class Absolute(UnaryOperation):
    def diff(self, var):
        # Derivative of |u| is u' * sgn(u)
        # Derivative of |u| is u' * sgn(u)
        return self.operand.diff(var) * Sign(self.operand)

    def _op(self, operand_val):
        return abs(operand_val)

    def __str__(self):
        return f"abs({self.operand})"


class Log(UnaryOperation):
    """Represents the natural logarithm of an expression."""
    def diff(self, var):
        # d/dx(ln(u)) = u'/u
        return self.operand.diff(var) / self.operand

    def _op(self, operand_val):
        if operand_val <= 0:
            raise ValueError("Logarithm undefined for non-positive values.")
        return math.log(operand_val)

    def __str__(self):
        return f"log({self.operand})"

    def integrate(self, var: 'Variable'):
        """Integrates log. Only handles Int(log(var))dv = var*log(var) - var."""
        if self.operand == var:
            # Integral of log(var) w.r.t. var is var*log(var) - var
            # var * self (where self is Log(var))
            term1 = Multiply(var, self)
            term2 = var
            # (var * Log(var)) - var
            # Expression.__sub__ will be used here.
            return term1 - term2
        else:
            raise NotImplementedError(
                "Integration of log(u) for u != var (e.g., log(f(x))) not implemented yet."
            )


class Exp(UnaryOperation):
    """Represents the exponential of an expression (e^x)."""
    def diff(self, var):
        # d/dx(e^u) = e^u * u'
        return Exp(self.operand) * self.operand.diff(var)

    def _op(self, operand_val):
        return math.exp(operand_val)

    def __str__(self):
        return f"exp({self.operand})"

    def integrate(self, var: 'Variable'):
        """Integrates exp. Only handles Int(exp(var))dv = exp(var)."""
        if self.operand == var:
            # Integral of exp(var) w.r.t. var is exp(var)
            return self # Returns the same Exp(var) object
        else:
            raise NotImplementedError(
                "Integration of exp(u) for u != var (e.g., exp(f(x))) not implemented yet."
            )


class Sign(UnaryOperation):
    """Represents the sign function (sgn)."""
    def __init__(self, operand):
        super().__init__(operand)

    def _op(self, operand_val):
        if operand_val == 0:
            return 0
        return math.copysign(1, operand_val)

    def diff(self, var):
        # Derivative of sgn(u) is 0 (for u != 0).
        # At u=0, the derivative is undefined (or can be seen as 2*delta(0) if using distributions).
        # For symbolic purposes, Constant(0) is a reasonable simplification.
        return Constant(0)

    def __str__(self):
        return f"sgn({self.operand})"
