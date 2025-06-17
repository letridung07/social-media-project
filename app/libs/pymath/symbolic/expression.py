import math

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
        # Note: x - x -> 0 is omitted as per instructions
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
        # Note: x / x -> 1 is omitted
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

    def diff(self, var):
        raise NotImplementedError

    def eval(self, **kwargs):
        raise NotImplementedError

    def __str__(self):
        raise NotImplementedError

    def __repr__(self):
        return self.__str__()


class Constant(Expression):
    def __init__(self, value):
        self.value = value

    def diff(self, var):
        return Constant(0)

    def eval(self, **kwargs):
        return self.value

    def __str__(self):
        return str(self.value)


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


class Add(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) + self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val + right_val

    def __str__(self):
        return f"({self.left} + {self.right})"


class Subtract(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) - self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val - right_val

    def __str__(self):
        return f"({self.left} - {self.right})"


class Multiply(BinaryOperation):
    def diff(self, var):
        return self.left.diff(var) * self.right + self.left * self.right.diff(var)

    def _op(self, left_val, right_val):
        return left_val * right_val

    def __str__(self):
        return f"({self.left} * {self.right})"


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


class UnaryOperation(Expression):
    def __init__(self, operand):
        self.operand = operand

    def eval(self, **kwargs):
        operand_val = self.operand.eval(**kwargs)
        return self._op(operand_val)

    def _op(self, operand_val):
        raise NotImplementedError


class Negate(UnaryOperation):
    def diff(self, var):
        return -self.operand.diff(var)

    def _op(self, operand_val):
        return -operand_val

    def __str__(self):
        return f"(-{self.operand})"


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


class Exp(UnaryOperation):
    """Represents the exponential of an expression (e^x)."""
    def diff(self, var):
        # d/dx(e^u) = e^u * u'
        return Exp(self.operand) * self.operand.diff(var)

    def _op(self, operand_val):
        return math.exp(operand_val)

    def __str__(self):
        return f"exp({self.operand})"


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
