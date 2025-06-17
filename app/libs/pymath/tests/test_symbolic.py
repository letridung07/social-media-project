import unittest
import math # For math.log, math.exp, math.e

# Attempt to import from pymath.symbolic.expression
# This structure assumes the tests will be run in an environment where pymath is in PYTHONPATH
# e.g., python -m unittest discover -s pymath
try:
    from pymath.symbolic.expression import (
        Expression, Constant, Variable,
        Add, Subtract, Multiply, Divide, Power,
        Negate, Absolute, Log, Exp, Sign
    )
except ImportError:
    # Fallback for running the script directly for testing, assuming it's in the parent of pymath
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from pymath.symbolic.expression import (
        Expression, Constant, Variable,
        Add, Subtract, Multiply, Divide, Power,
        Negate, Absolute, Log, Exp, Sign
    )

class TestSymbolicExpressions(unittest.TestCase):

    def test_creation_and_basic_properties(self):
        c1 = Constant(5)
        c2 = Constant(3.14)
        v1 = Variable('x')
        v2 = Variable('y_var')

        self.assertIsInstance(c1, Constant)
        self.assertEqual(c1.value, 5)
        self.assertEqual(str(c1), "5")

        self.assertIsInstance(c2, Constant)
        self.assertEqual(c2.value, 3.14)
        self.assertEqual(str(c2), "3.14")

        self.assertIsInstance(v1, Variable)
        self.assertEqual(v1.name, 'x')
        self.assertEqual(str(v1), "x")

        self.assertIsInstance(v2, Variable)
        self.assertEqual(v2.name, 'y_var')
        self.assertEqual(str(v2), "y_var")

    def test_arithmetic_operations_construction_and_str(self):
        x = Variable('x')
        y = Variable('y')
        c1 = Constant(1)
        c2 = Constant(2)

        expr_add = x + c1
        self.assertIsInstance(expr_add, Add)
        self.assertEqual(str(expr_add), "(x + 1)")

        # Test with number promotion
        expr_add_num = x + 2
        self.assertIsInstance(expr_add_num, Add)
        self.assertEqual(str(expr_add_num), "(x + 2)")

        expr_add_rev_num = 2 + x
        self.assertIsInstance(expr_add_rev_num, Add) # Should be Add if x is not 0
        self.assertEqual(str(expr_add_rev_num), "(2 + x)")


        expr_sub = y - c2
        self.assertIsInstance(expr_sub, Subtract)
        self.assertEqual(str(expr_sub), "(y - 2)")

        expr_sub_num = y - 3
        self.assertIsInstance(expr_sub_num, Subtract)
        self.assertEqual(str(expr_sub_num), "(y - 3)")

        expr_sub_rev_num = 3 - y
        self.assertIsInstance(expr_sub_rev_num, Subtract)
        self.assertEqual(str(expr_sub_rev_num), "(3 - y)")


        expr_mul = x * c1 # c1 is Constant(1)
        self.assertIs(expr_mul, x) # Simplified: x * 1 -> x
        self.assertEqual(str(expr_mul), "x")

        # Test Multiply instance for non-simplified case
        expr_mul_c2 = x * c2
        self.assertIsInstance(expr_mul_c2, Multiply)
        self.assertEqual(str(expr_mul_c2), "(x * 2)")

        expr_mul_complex = (x + c1) * y
        self.assertIsInstance(expr_mul_complex, Multiply)
        self.assertEqual(str(expr_mul_complex), "((x + 1) * y)")

        expr_div = x / c2
        self.assertIsInstance(expr_div, Divide)
        self.assertEqual(str(expr_div), "(x / 2)")

        expr_pow = x ** c2
        self.assertIsInstance(expr_pow, Power)
        self.assertEqual(str(expr_pow), "(x ** 2)")

        expr_pow_var = x ** y
        self.assertIsInstance(expr_pow_var, Power)
        self.assertEqual(str(expr_pow_var), "(x ** y)")

        expr_neg = -x
        self.assertIsInstance(expr_neg, Negate)
        self.assertEqual(str(expr_neg), "(-x)")

        # Test __repr__
        self.assertEqual(repr(c1), "1")
        self.assertEqual(repr(x), "x")
        self.assertEqual(repr(expr_add), "(x + 1)")

    def test_eval_method(self):
        x = Variable('x')
        y = Variable('y')
        c1 = Constant(5)
        c2 = Constant(2)

        self.assertEqual(c1.eval(), 5)
        self.assertEqual(x.eval(x=10), 10)

        with self.assertRaisesRegex(ValueError, "Variable x not found in evaluation context"):
            x.eval()
        with self.assertRaisesRegex(ValueError, "Variable z not found in evaluation context"):
            (x+Variable('z')).eval(x=1)

        expr_add = x + c2
        self.assertEqual(expr_add.eval(x=3), 5) # (3+2)

        expr_sub = x - c1
        self.assertEqual(expr_sub.eval(x=10), 5) # (10-5)

        expr_mul = x * c1
        self.assertEqual(expr_mul.eval(x=3), 15) # (3*5)

        expr_div = x / c2
        self.assertEqual(expr_div.eval(x=10), 5.0) # (10/2)

        with self.assertRaises(ZeroDivisionError):
            (x / Constant(0)).eval(x=1)
        with self.assertRaises(ZeroDivisionError):
            (x / y).eval(x=1, y=0)

        expr_pow = x ** c2
        self.assertEqual(expr_pow.eval(x=3), 9) # (3**2)

        expr_neg = -(x + c2)
        self.assertEqual(expr_neg.eval(x=3), -5) # -(3+2)

        # Test Log and Exp
        expr_log = Log(x)
        self.assertAlmostEqual(expr_log.eval(x=math.e), 1.0)
        self.assertAlmostEqual(expr_log.eval(x=1), 0.0)
        with self.assertRaises(ValueError): # Log of zero or negative
            expr_log.eval(x=0)

        expr_exp = Exp(x)
        self.assertAlmostEqual(expr_exp.eval(x=1), math.e)
        self.assertAlmostEqual(expr_exp.eval(x=0), 1.0)

        # More complex expression
        # (x * y + Exp(x / Constant(2)))
        expr_complex = (x * y) + Exp(x / c2)
        # x=2, y=3: (2*3) + Exp(2/2) = 6 + Exp(1) = 6 + e
        self.assertAlmostEqual(expr_complex.eval(x=2, y=3), 6 + math.e)


    def test_simplification_rules(self):
        x = Variable('x')
        y = Variable('y') # Another variable for non-simplification cases
        c0 = Constant(0)
        c1 = Constant(1)
        c2 = Constant(2)
        c5 = Constant(5)

        # Add
        self.assertIs(x + c0, x) # expr + 0 -> expr
        self.assertIs(c0 + x, x) # 0 + expr -> expr
        res_add_const = c2 + c5
        self.assertIsInstance(res_add_const, Constant)
        self.assertEqual(res_add_const.value, 7)
        # Ensure it doesn't over-simplify
        self.assertIsInstance(x + y, Add)
        self.assertIsInstance(x + c1, Add) # Should remain (x+1) if x is not 0

        # Multiply
        res_mul_c0_1 = x * c0
        self.assertIsInstance(res_mul_c0_1, Constant)
        self.assertEqual(res_mul_c0_1.value, 0) # expr * 0 -> Constant(0)

        res_mul_c0_2 = c0 * x
        self.assertIsInstance(res_mul_c0_2, Constant)
        self.assertEqual(res_mul_c0_2.value, 0) # 0 * expr -> Constant(0)

        self.assertIs(x * c1, x) # expr * 1 -> expr
        self.assertIs(c1 * x, x) # 1 * expr -> expr

        res_mul_const = c2 * c5
        self.assertIsInstance(res_mul_const, Constant)
        self.assertEqual(res_mul_const.value, 10)
        # Ensure it doesn't over-simplify
        self.assertIsInstance(x * y, Multiply)
        self.assertIsInstance(x * c2, Multiply) # Should remain (x*2) if x is not 0 or 1

        # Subtract
        self.assertIs(x - c0, x) # expr - 0 -> expr
        res_sub_const = c5 - c2
        self.assertIsInstance(res_sub_const, Constant)
        self.assertEqual(res_sub_const.value, 3)
        # Ensure it doesn't over-simplify
        self.assertIsInstance(x - y, Subtract)
        self.assertIsInstance(x - c1, Subtract)
        self.assertIsInstance(c1 - x, Subtract)


        # Divide
        res_div_0_x = c0 / x # 0 / x (assuming x is not 0)
        self.assertIsInstance(res_div_0_x, Constant)
        self.assertEqual(res_div_0_x.value, 0)

        res_div_0_c2 = c0 / c2 # 0 / 2
        self.assertIsInstance(res_div_0_c2, Constant)
        self.assertEqual(res_div_0_c2.value, 0)

        res_div_const = Constant(6) / c2 # 6 / 2
        self.assertIsInstance(res_div_const, Constant)
        self.assertEqual(res_div_const.value, 3)

        # Division by zero (should create Divide object, eval will raise error)
        div_by_zero_expr = x / c0
        self.assertIsInstance(div_by_zero_expr, Divide)
        with self.assertRaises(ZeroDivisionError):
            div_by_zero_expr.eval(x=1)

        div_by_zero_const = c5 / c0
        self.assertIsInstance(div_by_zero_const, Divide) # Constant / Constant(0)
        with self.assertRaises(ZeroDivisionError):
            div_by_zero_const.eval()


        # Power
        res_pow_0 = x ** c0 # expr ** 0 -> Constant(1)
        self.assertIsInstance(res_pow_0, Constant)
        self.assertEqual(res_pow_0.value, 1)

        self.assertIs(x ** c1, x) # expr ** 1 -> expr

        res_pow_c0_x = c0 ** x # 0 ** positive_expr (only if x is positive Constant)
        res_pow_c0_c2 = c0 ** c2 # 0 ** 2
        self.assertIsInstance(res_pow_c0_c2, Constant)
        self.assertEqual(res_pow_c0_c2.value, 0)

        # Test 0 ** non-positive constant (e.g. 0**0 = 1, 0**-1 = error)
        res_pow_c0_c0 = c0 ** c0 # 0 ** 0
        self.assertIsInstance(res_pow_c0_c0, Constant)
        self.assertEqual(res_pow_c0_c0.value, 1) # 0**0 is 1 by convention here

        with self.assertRaises(ValueError): # 0 ** -1
             c0 ** Constant(-1)


        res_pow_c1_x = c1 ** x # 1 ** expr -> Constant(1)
        self.assertIsInstance(res_pow_c1_x, Constant)
        self.assertEqual(res_pow_c1_x.value, 1)

        res_pow_consts = c2 ** Constant(3) # 2 ** 3
        self.assertIsInstance(res_pow_consts, Constant)
        self.assertEqual(res_pow_consts.value, 8)

        res_pow_consts_float = Constant(4.0) ** Constant(0.5) # 4.0 ** 0.5
        self.assertIsInstance(res_pow_consts_float, Constant)
        self.assertEqual(res_pow_consts_float.value, 2.0)

        # Negate
        res_neg_const = -c5
        self.assertIsInstance(res_neg_const, Constant)
        self.assertEqual(res_neg_const.value, -5)

        neg_x = -x
        self.assertIsInstance(neg_x, Negate)
        double_neg_x = -neg_x # -(-x) -> x
        self.assertIs(double_neg_x, x)

        # Test -(-(-x))
        triple_neg_x = -(-(-x))
        self.assertIsInstance(triple_neg_x, Negate)
        self.assertIs(triple_neg_x.operand, x)
        self.assertEqual(str(triple_neg_x), "(-x)")

    def test_differentiation(self):
        x = Variable('x')
        y = Variable('y')
        c0 = Constant(0)
        c1 = Constant(1)
        c2 = Constant(2)
        c5 = Constant(5)

        # Basic diff rules
        self.assertEqual(str(c5.diff(x)), str(c0)) # d(5)/dx = 0
        self.assertEqual(str(x.diff(x)), str(c1)) # d(x)/dx = 1
        self.assertEqual(str(y.diff(x)), str(c0)) # d(y)/dx = 0

        # Sum rule: (f+g)' = f' + g'
        # (x+5)' = 1+0 = 1
        expr_add = x + c5
        self.assertEqual(str(expr_add.diff(x)), "1")
        # (x+y)' = 1+0 = 1 (w.r.t x)
        expr_add_vars = x + y
        self.assertEqual(str(expr_add_vars.diff(x)), "1")
        # (x^2 + x).diff(x) = 2x + 1
        expr_add_complex = (x**c2) + x
        self.assertEqual(str(expr_add_complex.diff(x)), "((2 * x) + 1)") # Check actual simplified form

        # Product rule: (f*g)' = f'g + fg'
        # (x*5)' = 1*5 + x*0 = 5
        expr_mul = x * c5
        self.assertEqual(str(expr_mul.diff(x)), "5")
        # (x*y)' = 1*y + x*0 = y (w.r.t x)
        expr_mul_vars = x * y
        self.assertEqual(str(expr_mul_vars.diff(x)), str(y)) # Expect "y" due to simplification (1*y + x*0)

        # (x^2 * x).diff(x) = (x^3).diff(x) = 3x^2
        # Using product rule: (2x * x) + (x^2 * 1) = 2x^2 + x^2 = 3x^2
        expr_mul_complex = (x**c2) * x
        # Expected: ((2 * (x ** 1)) * x) + ((x ** 2) * 1)
        # Simplified: (2x * x) + x^2 = 2x^2 + x^2 = 3x^2
        # str output might be (( (2 * (x ** 1)) * x) + (x ** 2)) before more advanced simplification
        # Let's test eval of the derivative
        # (x^2 * x).diff(x) at x=2: ( (2*2*1) * 2) + (2^2 * 1) = 8 + 4 = 12
        # (3 * x^2).eval(x=2) = 3 * 4 = 12
        diff_expr = expr_mul_complex.diff(x)
        self.assertEqual(diff_expr.eval(x=2), 12)
        self.assertEqual(str(diff_expr), "(((2 * x) * x) + (x ** 2))") # String reflects x**1 -> x simplification

        # Quotient rule: (f/g)' = (f'g - fg') / g^2
        # (x/2)' = (1*2 - x*0) / 2^2 = 2 / 4 = 1/2
        expr_div = x / c2
        self.assertEqual(str(expr_div.diff(x)), "0.5") # (1*2 - x*0)/4 = 2/4 = 0.5

        # ( (x+1) / x )' = (1*x - (x+1)*1) / x^2 = (x - x - 1) / x^2 = -1 / x^2
        f = x + c1
        g = x
        expr_div_complex = f / g
        # Expected: ((1 * x) - ((x + 1) * 1)) / (x ** 2)
        # Simplified: (x - (x+1)) / x^2 = -1 / x^2
        # str: "(((1 * x) - ((x + 1) * 1)) / (x ** 2))"
        diff_expr_div = expr_div_complex.diff(x)
        # at x=2: -1 / 4 = -0.25
        self.assertEqual(diff_expr_div.eval(x=2), -0.25)
        self.assertEqual(str(diff_expr_div), "((x - (x + 1)) / (x ** 2))") # Reflects 1*expr and expr*1 simplifications


        # Power rule (f**c)' = c * f**(c-1) * f'
        # (x^5)' = 5 * x^4 * 1 = 5x^4
        expr_pow_const_exp = x ** c5
        # Expected: (5 * (x ** 4)) * 1  which simplifies to (5 * (x ** 4))
        # (x**Constant(4)) simplifies its string form if possible.
        # (x**4) might become str "(x ** 4)"
        # (5 * x^4)
        self.assertEqual(str(expr_pow_const_exp.diff(x)), "(5 * (x ** 4))") # This should be fine, x**4 doesn't simplify further by itself

        # ((x+1)^2)' = 2 * (x+1)^1 * 1 = 2*(x+1) = 2x+2
        expr_pow_complex_base = (x+c1)**c2
        # Expected: ((2 * ((x + 1) ** 1)) * 1) which simplifies to (2 * (x+1))
        # (x+1)**1 simplifies to (x+1). So, (2 * (x+1)).
        self.assertEqual(str(expr_pow_complex_base.diff(x)), "(2 * (x + 1))")


        # General power rule (f**g)' = (f**g) * (g' * log(f) + g * f'/f)
        # (x ** x).diff(x) = (x**x) * (1*log(x) + x * 1/x) = (x**x) * (log(x) + 1)
        expr_fpowg = x ** x
        # Expected: ((x ** x) * ((1 * log(x)) + (x * (1 / x))))
        # Actual based on current simplifications: ((x ** x) * (log(x) + (x * (1 / x))))
        # (1*log(x) simplifies to log(x), but x*(1/x) does not simplify to 1 yet)
        diff_fpowg = expr_fpowg.diff(x)
        self.assertEqual(str(diff_fpowg), "((x ** x) * (log(x) + (x * (1 / x))))")
        # Eval at x=2: (2**2) * (log(2)+1) = 4 * (log(2)+1)
        # The eval should still be correct as x*(1/x) evaluates to 1 for x!=0
        self.assertAlmostEqual(diff_fpowg.eval(x=2), (2**2)*(math.log(2)+1)) # (4 * (log(2) + (2*(1/2)))) = 4 * (log(2)+1)

        # ( (x+1) ** (x+2) ).diff(x)
        f = x + c1 # f' = 1
        g = x + c2 # g' = 1
        expr_fpowg_complex = f ** g
        # (f**g) * ( g'*log(f) + g * f'/f )
        # ((x+1)**(x+2)) * ( 1*log(x+1) + (x+2) * 1/(x+1) )
        # str: "(((x + 1) ** (x + 2)) * ((1 * log((x + 1))) + ((x + 2) * (1 / (x + 1)))))"
        diff_fpowg_complex = expr_fpowg_complex.diff(x)
        expected_str = "(((x + 1) ** (x + 2)) * (log((x + 1)) + ((x + 2) / (x + 1))))" # 1*log simplifies, 1/(x+1) can become / (x+1)
        # The actual string might have more parentheses or slight variations based on internal str representations of subexpressions.
        # Let's check eval
        # f(x) = (x+1)**(x+2). At x=1: (1+1)**(1+2) = 2**3 = 8
        # f'(x) = ( (x+1)**(x+2) ) * ( log(x+1) + (x+2)/(x+1) )
        # f'(1) = ( (1+1)**(1+2) ) * ( log(1+1) + (1+2)/(1+1) )
        #       = ( 2**3 ) * ( log(2) + 3/2 ) = 8 * (log(2) + 1.5)
        val_at_1 = 8 * (math.log(2) + 1.5)
        self.assertAlmostEqual(diff_fpowg_complex.eval(x=1), val_at_1)


        # Log rule: (log(f))' = f'/f
        # (log(x))' = 1/x
        expr_log_x = Log(x)
        self.assertEqual(str(expr_log_x.diff(x)), "(1 / x)")
        # (log(x^2))' = (2x) / x^2 = 2/x
        expr_log_x_sq = Log(x**c2)
        # Expected: ((2 * (x ** 1)) * 1) / (x ** 2)  which simplifies to (2x) / x^2 -> 2/x
        # str: "((2 * x) / (x ** 2))" due to (x**1) -> x simplification
        self.assertEqual(str(expr_log_x_sq.diff(x)), "((2 * x) / (x ** 2))") # before full simplification to 2/x
        self.assertEqual(expr_log_x_sq.diff(x).eval(x=2), 1.0) # 2/2 = 1


        # Exp rule: (exp(f))' = exp(f) * f'
        # (exp(x))' = exp(x) * 1 = exp(x)
        expr_exp_x = Exp(x)
        self.assertEqual(str(expr_exp_x.diff(x)), "exp(x)") # (exp(x) * 1) simplifies to exp(x)
        # (exp(x^2))' = exp(x^2) * 2x
        expr_exp_x_sq = Exp(x**c2)
        # Expected: (exp(x^2) * (2x*1))
        # str: "(exp((x ** 2)) * (2 * x))"
        self.assertEqual(str(expr_exp_x_sq.diff(x)), "(exp((x ** 2)) * (2 * x))")
        # Eval at x=1: exp(1)*2 = 2e
        self.assertAlmostEqual(expr_exp_x_sq.diff(x).eval(x=1), 2*math.e)

        # Negate rule: (-f)' = -f'
        # (-(x^2))' = -(2x)
        expr_neg_x_sq = -(x**c2)
        # Expected: - (2x*1)
        # str: "(-(2 * x))"
        self.assertEqual(str(expr_neg_x_sq.diff(x)), "(-(2 * x))")
        self.assertEqual(expr_neg_x_sq.diff(x).eval(x=2), -4.0)

        # Combined and complex cases
        # d/dx (sin(x^2)) is not possible as sin is not defined
        # d/dx (log(x+1) * exp(x))
        f = Log(x+c1) # f' = 1/(x+1)
        g = Exp(x)    # g' = exp(x)
        # (f'g + fg')
        # ( (1/(x+1))*exp(x) + log(x+1)*exp(x) )
        expr_combo = f * g
        # str: "(((1 / (x + 1)) * exp(x)) + (log((x + 1)) * (exp(x) * 1)))"
        # Simplified str: "(((1 / (x + 1)) * exp(x)) + (log((x + 1)) * exp(x)))"
        diff_combo = expr_combo.diff(x)
        expected_str_combo = "(((1 / (x + 1)) * exp(x)) + (log((x + 1)) * exp(x)))"
        self.assertEqual(str(diff_combo), expected_str_combo)
        # Eval at x=0: (1/1 * exp(0)) + (log(1) * exp(0)) = (1*1) + (0*1) = 1
        self.assertAlmostEqual(diff_combo.eval(x=0), 1.0)

        # Test that diff of an expression without the variable is 0
        expr_no_x = y + Constant(5)
        self.assertEqual(str(expr_no_x.diff(x)), "0") # (0+0) -> 0

        # Test diff of nested expression
        # ( (x+1)^2 + x^2 )' = 2(x+1) + 2x = 2x+2+2x = 4x+2
        term1 = (x+c1)**c2 # (x+1)^2, diff is 2*(x+1)
        term2 = x**c2      # x^2, diff is 2*x
        expr_nested_sum = term1 + term2
        # diff: (2*(x+1)*1) + (2*x*1)
        # str: "((2 * (x + 1)) + (2 * x))"
        diff_nested = expr_nested_sum.diff(x)
        self.assertEqual(str(diff_nested), "((2 * (x + 1)) + (2 * x))")
        # Eval at x=1: (2*(1+1)) + (2*1) = 4 + 2 = 6
        self.assertEqual(diff_nested.eval(x=1), 6.0)

    # test_absolute_value_diff_not_implemented was removed as Absolute.diff is now implemented

    def test_sign_evaluation(self):
        x = Variable('x')
        self.assertEqual(Sign(Constant(5)).eval(), 1)
        self.assertEqual(Sign(Constant(-3)).eval(), -1)
        self.assertEqual(Sign(Constant(0)).eval(), 0)

        self.assertEqual(Sign(x).eval(x=5), 1)
        self.assertEqual(Sign(x).eval(x=-3), -1)
        self.assertEqual(Sign(x).eval(x=0), 0)

        expr_complex = Sign(Add(x, Constant(2))) # sgn(x+2)
        self.assertEqual(expr_complex.eval(x=-5), -1) # sgn(-3) -> -1
        self.assertEqual(expr_complex.eval(x=-2), 0)  # sgn(0) -> 0
        self.assertEqual(expr_complex.eval(x=3), 1)   # sgn(5) -> 1

    def test_sign_differentiation(self):
        x = Variable('x')
        c5 = Constant(5)

        # diff(sgn(x), x) -> 0
        diff_sign_x = Sign(x).diff(x)
        self.assertIsInstance(diff_sign_x, Constant)
        self.assertEqual(diff_sign_x.eval(), 0)
        self.assertEqual(str(diff_sign_x), "0")

        # diff(sgn(5), x) -> 0
        diff_sign_c5 = Sign(c5).diff(x)
        self.assertIsInstance(diff_sign_c5, Constant)
        self.assertEqual(diff_sign_c5.eval(), 0)
        self.assertEqual(str(diff_sign_c5), "0")

        # diff(sgn(x^2), x) should be 0 (as derivative of sgn(u) is 0)
        # Note: This is a simplification. Derivative of sgn(u) is 2*delta(u)*u',
        # but we've defined sgn(u).diff() as Constant(0).
        expr_complex = Sign(x ** Constant(2))
        diff_complex = expr_complex.diff(x)
        self.assertIsInstance(diff_complex, Constant)
        self.assertEqual(diff_complex.eval(), 0)
        self.assertEqual(str(diff_complex), "0")


    def test_sign_str(self):
        x = Variable('x')
        c5 = Constant(5)
        expr_add = Add(x, Constant(1))

        self.assertEqual(str(Sign(x)), "sgn(x)")
        self.assertEqual(str(Sign(c5)), "sgn(5)")
        self.assertEqual(str(Sign(expr_add)), "sgn((x + 1))")

    def test_absolute_diff_variable_x(self):
        x = Variable('x')
        abs_x = Absolute(x)
        deriv_abs_x = abs_x.diff(x) # Should be 1 * sgn(x), which simplifies to sgn(x)

        # String representation: d(|x|)/dx = sgn(x)
        self.assertEqual(str(deriv_abs_x), "sgn(x)")

        # Evaluation:
        self.assertEqual(deriv_abs_x.eval(x=2), 1)   # sgn(2) = 1
        self.assertEqual(deriv_abs_x.eval(x=-2), -1) # sgn(-2) = -1
        self.assertEqual(deriv_abs_x.eval(x=0), 0)   # sgn(0) = 0

    def test_absolute_diff_constant(self):
        x = Variable('x')
        # d(|5|)/dx = 0
        abs_c_pos = Absolute(Constant(5))
        deriv_abs_c_pos = abs_c_pos.diff(x) # (0 * sgn(5)) -> 0
        self.assertIsInstance(deriv_abs_c_pos, Constant)
        self.assertEqual(deriv_abs_c_pos.value, 0)
        self.assertEqual(str(deriv_abs_c_pos), "0")
        self.assertEqual(deriv_abs_c_pos.eval(), 0)

        # d(|-5|)/dx = 0
        abs_c_neg = Absolute(Constant(-5))
        deriv_abs_c_neg = abs_c_neg.diff(x) # (0 * sgn(-5)) -> 0
        self.assertIsInstance(deriv_abs_c_neg, Constant)
        self.assertEqual(deriv_abs_c_neg.value, 0)
        self.assertEqual(str(deriv_abs_c_neg), "0")
        self.assertEqual(deriv_abs_c_neg.eval(), 0)

    def test_absolute_diff_power_x_sq(self):
        x = Variable('x')
        # d(|x^2|)/dx = 2x * sgn(x^2)
        x_sq = x ** Constant(2)
        abs_x_sq = Absolute(x_sq)
        deriv_abs_x_sq = abs_x_sq.diff(x) # (2x * sgn(x^2))

        # String representation
        # (x_sq.diff(x)) is (2*x)
        # Sign(x_sq) is sgn((x ** 2))
        # So, deriv is ((2 * x) * sgn((x ** 2)))
        self.assertEqual(str(deriv_abs_x_sq), "((2 * x) * sgn((x ** 2)))")

        # Evaluation
        self.assertEqual(deriv_abs_x_sq.eval(x=2), 4)  # (2*2) * sgn(4) = 4 * 1 = 4
        self.assertEqual(deriv_abs_x_sq.eval(x=-2), -4) # (2*-2) * sgn(4) = -4 * 1 = -4
        self.assertEqual(deriv_abs_x_sq.eval(x=0), 0)   # (2*0) * sgn(0) = 0 * 0 = 0

    def test_absolute_diff_x_minus_c(self):
        x = Variable('x')
        c2 = Constant(2)
        # d(|x-2|)/dx = 1 * sgn(x-2) = sgn(x-2)
        expr_x_minus_2 = x - c2
        abs_expr = Absolute(expr_x_minus_2)
        deriv_abs_expr = abs_expr.diff(x) # (1 * sgn((x-2))) which simplifies to sgn((x-2))

        # String representation
        self.assertEqual(str(deriv_abs_expr), "sgn((x - 2))")

        # Evaluation
        self.assertEqual(deriv_abs_expr.eval(x=3), 1)  # sgn(1) = 1
        self.assertEqual(deriv_abs_expr.eval(x=1), -1) # sgn(-1) = -1
        self.assertEqual(deriv_abs_expr.eval(x=2), 0)  # sgn(0) = 0

    def test_absolute_eval(self): # Added a basic test for Absolute.eval
        x = Variable('x')
        c_pos = Constant(5)
        c_neg = Constant(-3)
        c_zero = Constant(0)

        self.assertEqual(Absolute(c_pos).eval(), 5)
        self.assertEqual(Absolute(c_neg).eval(), 3)
        self.assertEqual(Absolute(c_zero).eval(), 0)

        self.assertEqual(Absolute(x).eval(x=4), 4)
        self.assertEqual(Absolute(x).eval(x=-4), 4)
        self.assertEqual(Absolute(x).eval(x=0), 0)

        expr_complex = Absolute(Subtract(x, Constant(5))) # |x-5|
        self.assertEqual(expr_complex.eval(x=7), 2)  # |2| = 2
        self.assertEqual(expr_complex.eval(x=2), 3)  # |-3| = 3
        self.assertEqual(expr_complex.eval(x=5), 0)  # |0| = 0


if __name__ == '__main__':
    unittest.main()
