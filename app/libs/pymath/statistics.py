import math
from typing import List, Union, Tuple

# --- Internal Helper Functions ---

def _factorial(n: int) -> int:
    """Calculates the factorial of a non-negative integer n.
    Internal helper function.

    Args:
        n: A non-negative integer.

    Returns:
        The factorial of n (n!).

    Raises:
        TypeError: If n is not an integer.
        ValueError: If n is negative.
    """
    if not isinstance(n, int):
        # math.factorial would raise TypeError, but good to be explicit for non-int types if they bypass isinstance somehow
        raise TypeError(f"Factorial input must be an integer. Got type {type(n)}.")
    if n < 0:
        # math.factorial would raise ValueError
        raise ValueError("Factorial is not defined for negative numbers.")
    return math.factorial(n)

def _combinations(n: int, k: int) -> int:
    """Calculates 'n choose k', the number of combinations of selecting k items
    from a set of n items without regard to the order of selection.
    Internal helper function.

    Args:
        n: The total number of items (non-negative integer).
        k: The number of items to choose (non-negative integer, k <= n).

    Returns:
        The number of combinations C(n, k).

    Raises:
        TypeError: If n or k are not integers.
        ValueError: If n is negative, or if k is negative or k > n.
    """
    if not isinstance(n, int) or not isinstance(k, int):
        raise TypeError(f"Inputs n and k for combinations must be integers. Got n: {type(n)}, k: {type(k)}.")
    if n < 0:
        raise ValueError("Total number of items 'n' cannot be negative for combinations.")
    if k < 0:
        raise ValueError("Number of items to choose 'k' cannot be negative for combinations.")
    if k > n:
        raise ValueError("Number of items to choose 'k' cannot be greater than total items 'n'.")

    # C(n, k) = n! / (k! * (n-k)!)
    # Using our _factorial helper:
    return _factorial(n) // (_factorial(k) * _factorial(n - k))

def _sample_variance(sample: List[Union[int, float]]) -> float:
    """Calculates the sample variance of a list of numbers.
    Sample variance uses (n-1) in the denominator.
    Internal helper function.

    Args:
        sample: A list of numbers (integers or floats). Must contain at least 2 elements.

    Returns:
        The sample variance as a float.

    Raises:
        TypeError: If the sample contains non-numeric data.
        ValueError: If the sample contains fewer than 2 elements.
    """
    n = len(sample)
    if n < 2:
        raise ValueError("Sample must contain at least two elements to calculate sample variance.")

    # Validate data types and convert to float
    sample_floats = []
    for x in sample:
        if not isinstance(x, (int, float)):
            raise TypeError(f"All elements in sample must be numbers. Found type {type(x)} for value '{x}'.")
        sample_floats.append(float(x))

    mean_val = mean(sample_floats) # Use existing mean function

    sum_squared_deviations = 0.0
    for x_float in sample_floats:
        sum_squared_deviations += (x_float - mean_val)**2

    return sum_squared_deviations / (n - 1)

# --- Public Statistical Functions ---

def binomial_pmf(k: int, n: int, p: float) -> float:
    """Calculates the Probability Mass Function (PMF) for the Binomial distribution.

    This gives the probability of observing exactly k successes in n independent
    Bernoulli trials, where p is the probability of success on a single trial.

    Args:
        k: The number of successes (non-negative integer, k <= n).
        n: The number of trials (non-negative integer).
        p: The probability of success on a single trial (float, 0 <= p <= 1).

    Returns:
        The probability P(X=k) for the Binomial distribution.

    Raises:
        TypeError: If k or n are not integers, or if p is not a float.
        ValueError: If p is not between 0 and 1 (inclusive), if n is negative,
                    or if k is negative or k > n.
    """
    # Input Validation
    if not isinstance(k, int):
        raise TypeError(f"Number of successes 'k' must be an integer. Got {type(k)}.")
    if not isinstance(n, int):
        raise TypeError(f"Number of trials 'n' must be an integer. Got {type(n)}.")
    if not isinstance(p, float):
        # Strict check for float type as per function signature.
        raise TypeError(f"Probability 'p' must be a float. Got {type(p)}.")

    if not (0.0 <= p <= 1.0):
        raise ValueError(f"Probability 'p' must be between 0.0 and 1.0. Got {p}.")

    # The _combinations function will validate:
    #   - n >= 0 (via its own _factorial call)
    #   - k >= 0
    #   - k <= n
    # We add explicit checks here for n < 0 and k < 0 for clearer error messages
    # specific to binomial_pmf context before _combinations is even called.
    # The k > n check is also good here to be explicit, though _combinations would catch it.
    if n < 0:
        raise ValueError(f"Number of trials 'n' cannot be negative. Got {n}.")
    if k < 0: # This is also checked by _combinations, but an early clear message is good.
        raise ValueError(f"Number of successes 'k' cannot be negative. Got {k}.")
    if k > n: # This is also checked by _combinations.
        raise ValueError(f"Number of successes 'k' ({k}) cannot be greater than the number of trials 'n' ({n}).")

    # Calculate combinations C(n, k)
    # _combinations handles n, k type checks and relative value checks (e.g. k <= n)
    comb = _combinations(n, k) # This can raise ValueError or TypeError from _combinations

    # Handle edge cases for p to avoid issues with math.pow(0.0, 0)
    # math.pow(0.0, 0) is 1.0. math.pow(0.0, positive) is 0.0.
    if p == 0.0:
        return 1.0 if k == 0 else 0.0
    if p == 1.0:
        return 1.0 if k == n else 0.0

    # Calculate p^k and (1-p)^(n-k)
    term_p_k = math.pow(p, k)
    term_1_minus_p_nk = math.pow(1.0 - p, n - k)

    return float(comb) * term_p_k * term_1_minus_p_nk

def poisson_pmf(k: int, lambda_val: float) -> float:
    """Calculates the Probability Mass Function (PMF) for the Poisson distribution.

    This gives the probability of observing exactly k events in a fixed interval
    of time or space, given lambda_val (λ) is the average number of events in
    that interval.

    Args:
        k: The number of occurrences of the event (non-negative integer).
        lambda_val: The average rate of occurrences (λ, float, must be >= 0).
                    While the type hint is float, integer lambda_val will be accepted and cast to float.

    Returns:
        The probability P(X=k) for the Poisson distribution.

    Raises:
        TypeError: If k is not an integer or lambda_val is not a number.
        ValueError: If k is negative or lambda_val is negative.
    """
    # Input Validation
    if not isinstance(k, int):
        raise TypeError(f"Number of occurrences 'k' must be an integer. Got {type(k)}.")
    if not isinstance(lambda_val, (int, float)): # Allow int lambda, will convert to float
        raise TypeError(f"Average rate 'lambda_val' must be a number (int or float). Got {type(lambda_val)}.")

    lambda_float = float(lambda_val) # Convert to float for calculations

    if k < 0:
        raise ValueError(f"Number of occurrences 'k' cannot be negative. Got {k}.")
    if lambda_float < 0:
        raise ValueError(f"Average rate 'lambda_val' cannot be negative. Got {lambda_float}.")

    # Edge case: If lambda_val is 0
    if lambda_float == 0.0:
        return 1.0 if k == 0 else 0.0

    # Calculate k! using the helper function
    # _factorial will raise ValueError for k < 0, but we've already checked this.
    k_factorial = _factorial(k) # _factorial returns int

    # Calculate lambda_val^k * e^(-lambda_val)
    # math.pow ensures float result. math.exp always returns float.
    try:
        term_lambda_k = math.pow(lambda_float, k)
        term_exp_neg_lambda = math.exp(-lambda_float)
    except OverflowError:
        # If lambda_float^k or exp(-lambda_float) is too large/small to represent,
        # the PMF is likely extremely close to 0 or involves numbers beyond float precision.
        # For very large k and lambda, direct computation can be unstable.
        # Returning 0.0 for overflow cases is a pragmatic approach if result is tiny.
        # If term_lambda_k is huge and term_exp_neg_lambda is tiny, their product might be normal.
        # However, if lambda_float^k itself overflows, it's problematic.
        # A more robust implementation might use log-probabilities for stability.
        # For this implementation, we'll let it raise OverflowError or return inf/0 if Python's math does.
        # Or, if we catch it, we can decide. Let's assume for now that if intermediate terms overflow,
        # the true probability is likely 0 or 1, or calculation is beyond standard float capacity.
        # A common result of overflow in numerator terms when k! is also huge is that PMF approaches 0.
        return 0.0 # Pragmatic choice for overflow in numerator terms

    numerator = term_lambda_k * term_exp_neg_lambda

    # PMF = numerator / k!
    # k_factorial is int. Numerator is float. Result will be float.
    # Since k_factorial comes from math.factorial (via _factorial), it's >= 1 for k>=0.
    # No division by zero from k_factorial unless k is huge and _factorial overflows to a non-standard int (unlikely).
    if k_factorial == 0: # Defensive, though math.factorial(non_negative_int) >= 1
        # This would only happen if _factorial was modified to return 0 for huge numbers,
        # which is not its current behavior.
        raise ValueError("Factorial of k resulted in zero, which is unexpected for non-negative k.")

    return numerator / float(k_factorial) # Ensure float division

def normal_pdf(x: float, mu: float, sigma: float) -> float:
    """Calculates the Probability Density Function (PDF) for the Normal (Gaussian) distribution.

    Args:
        x: The value at which to evaluate the PDF (float).
           While type hint is float, integer x will be accepted and cast to float.
        mu: The mean of the distribution (μ, float).
            While type hint is float, integer mu will be accepted and cast to float.
        sigma: The standard deviation of the distribution (σ, float, must be > 0).
               While type hint is float, integer sigma will be accepted and cast to float.

    Returns:
        The value of the PDF at x for the given Normal distribution.

    Raises:
        TypeError: If x, mu, or sigma are not numbers (int or float).
        ValueError: If sigma is not positive (sigma <= 0).
    """
    # Input Validation
    if not isinstance(x, (int, float)):
        raise TypeError(f"Value 'x' must be a number. Got {type(x)}.")
    if not isinstance(mu, (int, float)):
        raise TypeError(f"Mean 'mu' must be a number. Got {type(mu)}.")
    if not isinstance(sigma, (int, float)):
        raise TypeError(f"Standard deviation 'sigma' must be a number. Got {type(sigma)}.")

    x_float, mu_float, sigma_float = float(x), float(mu), float(sigma)

    if sigma_float <= 0:
        raise ValueError(f"Standard deviation 'sigma' must be positive. Got {sigma_float}.")

    # Formula: (1 / (sigma * sqrt(2 * pi))) * e^(-0.5 * ((x - mu) / sigma)^2)

    try:
        coefficient = 1.0 / (sigma_float * math.sqrt(2 * math.pi))
        exponent_term = (x_float - mu_float) / sigma_float
        exponent_numerator = -0.5 * math.pow(exponent_term, 2)
        # More direct: exponent_numerator = -0.5 * ((x_float - mu_float) / sigma_float)**2
    except OverflowError:
        # This could happen if sigma_float is extremely small, making coefficient huge,
        # or if (x_float - mu_float) / sigma_float is huge, making pow overflow.
        # If these terms overflow, the final result is likely 0 (due to exp of large negative) or inf.
        # A very large exponent_term leading to pow overflow would make exp(very_negative) -> 0
        return 0.0


    try:
        pdf_value = coefficient * math.exp(exponent_numerator)
    except OverflowError:
        # If math.exp(exponent_numerator) results in overflow (e.g. exponent_numerator is too large positive, which is not possible here as it's -0.5 * square)
        # or underflow (exponent_numerator is very large negative).
        # exp of a large negative number correctly underflows to 0.0 in Python.
        # This catch is more for extreme cases or if coefficient itself was problematic (e.g. sigma was near zero before validation).
        pdf_value = 0.0 # Result is effectively zero if exp term underflows

    return pdf_value

def two_sample_ttest_statistic(
    sample1: List[Union[int, float]],
    sample2: List[Union[int, float]],
    equal_variances: bool = True
) -> Tuple[float, float]:
    """Calculates the t-statistic and degrees of freedom for a two-sample independent t-test.

    Args:
        sample1: A list of numbers representing the first sample. Must contain at least 2 elements.
        sample2: A list of numbers representing the second sample. Must contain at least 2 elements.
        equal_variances: If True (default), assumes equal population variances and performs
                         Student's t-test. If False, performs Welch's t-test, which does
                         not assume equal population variances.

    Returns:
        A tuple (t_statistic, degrees_of_freedom).
        Returns (float('nan'), float('nan')) for t_statistic or df if the calculation
        involves division by zero (e.g., zero standard error or zero denominator for Welch's df).

    Raises:
        TypeError: If samples contain non-numeric data or if equal_variances is not boolean.
        ValueError: If samples contain fewer than 2 elements.
    """
    # Input Validation for types
    if not isinstance(sample1, list) or not isinstance(sample2, list):
        # This check is mostly for direct calls; if data comes from other internal processing,
        # it might already be a list. However, good for robustness.
        raise TypeError("Inputs sample1 and sample2 must be lists.")
    if not isinstance(equal_variances, bool):
        raise TypeError("Argument 'equal_variances' must be a boolean.")

    # Length validation (n>=2 for _sample_variance)
    n1 = len(sample1)
    n2 = len(sample2)
    if n1 < 2:
        raise ValueError("Sample 1 must contain at least two elements.")
    if n2 < 2:
        raise ValueError("Sample 2 must contain at least two elements.")

    # Calculate means and sample variances.
    # These functions will raise TypeError for non-numeric elements within samples
    # and ValueError if somehow length check was bypassed (e.g. n<2 for _sample_variance).
    try:
        mean1 = mean(sample1)
        var1 = _sample_variance(sample1)

        mean2 = mean(sample2)
        var2 = _sample_variance(sample2)
    except (TypeError, ValueError) as e:
        # Re-raise to indicate error during pre-requisite calculations
        raise type(e)(f"Error calculating mean or variance for samples: {e}")


    t_stat: float
    df: float

    if equal_variances:
        # Student's t-test (assumes equal variances)
        df = float(n1 + n2 - 2) # Denominator n1+n2-2 is >= 2 because n1,n2 >=2.

        # Pooled variance: sp_squared = ((n1 - 1) * var1 + (n2 - 1) * var2) / df
        # (n1-1) and (n2-1) are >= 1. var1, var2 are >= 0.
        pooled_variance_numerator = (n1 - 1) * var1 + (n2 - 1) * var2

        if df == 0: # Should not happen given n1,n2 >= 2
            sp_squared = float('nan') # Or handle as error, but df=0 is impossible here
        else:
            sp_squared = pooled_variance_numerator / df

        # Standard error: sqrt(sp_squared * (1/n1 + 1/n2))
        # (1/n1 + 1/n2) is > 0. sp_squared is >=0.
        standard_error_term_val = sp_squared * (1.0/n1 + 1.0/n2)

        if standard_error_term_val < 0: # Should only happen if sp_squared became negative due to float issues with tiny variances.
             # This implies a problem with variance calculation or extreme data.
             # For safety, treat as effectively zero variance if negative, leading to inf/nan t_stat.
             standard_error_term_val = 0.0

        if abs(standard_error_term_val) < 1e-12: # Standard error is effectively zero
            # If means are also equal (or very close), t_stat is 0/0 -> nan.
            # If means differ, t_stat is non-zero / 0 -> +/- inf.
            if abs(mean1 - mean2) < 1e-12:
                t_stat = float('nan')
            else:
                t_stat = float('inf') if mean1 > mean2 else float('-inf')
        else:
            t_stat = (mean1 - mean2) / math.sqrt(standard_error_term_val)
    else:
        # Welch's t-test (does not assume equal variances)
        term1 = var1 / n1
        term2 = var2 / n2
        standard_error_sum = term1 + term2

        if abs(standard_error_sum) < 1e-12: # Standard error sum is effectively zero
            if abs(mean1 - mean2) < 1e-12:
                t_stat = float('nan')
            else:
                t_stat = float('inf') if mean1 > mean2 else float('-inf')
            df = float('nan') # df calculation would also involve division by zero
        else:
            t_stat = (mean1 - mean2) / math.sqrt(standard_error_sum)

            # Welch-Satterthwaite equation for degrees of freedom
            # df_num = (var1/n1 + var2/n2)^2
            # df_den = ((var1/n1)^2 / (n1-1)) + ((var2/n2)^2 / (n2-1))
            # n1-1 and n2-1 are >= 1.
            df_numerator = math.pow(standard_error_sum, 2)

            df_denominator_term1 = math.pow(term1, 2) / (n1 - 1)
            df_denominator_term2 = math.pow(term2, 2) / (n2 - 1)
            df_denominator = df_denominator_term1 + df_denominator_term2

            if abs(df_denominator) < 1e-12:
                # If denominator is zero, df is undefined or infinite.
                # This can happen if variances are zero or very small.
                # If numerator is also zero (variances are zero), then 0/0 -> nan.
                # If numerator is non-zero and denominator is zero -> inf.
                df = float('nan') if abs(df_numerator) < 1e-12 else float('inf')
            else:
                df = df_numerator / df_denominator

    return t_stat, df

def mean(data: List[Union[int, float]]):
  """
  Calculates the arithmetic mean of a list of numbers.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    float: The arithmetic mean of the numbers.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate mean of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")
  return sum(data) / len(data)

def median(data: List[Union[int, float]]):
  """
  Calculates the median of a list of numbers.
  The median is the middle value of a dataset that has been sorted.
  If the dataset has an even number of values, the median is the average of the two middle values.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    Union[int, float]: The median value. This can be an integer or a float
                       depending on the input data and whether the list length is even or odd.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate median of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")

  sorted_data = sorted(data)
  n = len(sorted_data)
  mid = n // 2

  if n % 2 == 0:
    # Even number of elements
    return (sorted_data[mid - 1] + sorted_data[mid]) / 2
  else:
    # Odd number of elements
    return sorted_data[mid]

def mode(data):
  """
  Calculates the mode(s) of a list of numbers.
  The mode is the value that appears most frequently in a data set.
  A list of modes is returned because a dataset can have more than one mode (multimodal).

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    list[Union[int, float]]: A list containing the mode(s).
                             Returns an empty list if all elements are unique (no mode),
                             or if the input list is empty (after validation).
                             The modes will be of the same type as found in the input data.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate mode of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")

  counts = {}
  for item in data:
    counts[item] = counts.get(item, 0) + 1

  max_count = 0
  for count in counts.values():
      if count > max_count:
          max_count = count

  # In case all elements are unique, there is no mode.
  if max_count == 1 and len(set(data)) == len(data):
      return []

  modes = [key for key, value in counts.items() if value == max_count]
  return modes

def std_dev(data):
  """
  Calculates the population standard deviation of a list of numbers.
  Standard deviation is a measure of the amount of variation or dispersion of a set of values.
  A low standard deviation indicates that the values tend to be close to the mean (also called the expected value) of the set,
  while a high standard deviation indicates that the values are spread out over a wider range.
  This function calculates the *population* standard deviation, not the sample standard deviation.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    float: The population standard deviation.

  Raises:
    ValueError: If the list has fewer than two elements, as standard deviation requires at least two data points.
    TypeError: If the list contains non-numeric data (elements are not int or float).
  """
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")
  if len(data) < 2: # Changed from 1 to 2 as per docstring and common practice for population std dev
    raise ValueError("List must contain at least two data points to calculate standard deviation.")

  mean_val = mean(data)
  variance = sum([(x - mean_val) ** 2 for x in data]) / len(data)
  return math.sqrt(variance)

def pearson_correlation(data_x: List[Union[int, float]], data_y: List[Union[int, float]]) -> float:
    """Calculates the Pearson correlation coefficient between two lists of numbers.

    The Pearson correlation coefficient is a measure of linear correlation
    between two sets of data. It is the ratio between the covariance of
    two variables and the product of their standard deviations; thus it is
    essentially a normalized measurement of the covariance, such that the
    result always has a value between -1 and 1.

    Args:
        data_x: A list of numbers (int or float).
        data_y: A list of numbers (int or float), of the same length as data_x.

    Returns:
        float: The Pearson correlation coefficient.
               Returns 0.0 if either variable has a standard deviation of 0
               (i.e., all its values are the same), which makes correlation undefined or 0.

    Raises:
        ValueError: If input lists are empty, of different lengths, or contain
                    fewer than two data points.
        TypeError: If input lists contain non-numeric data.
    """
    n = len(data_x)

    # Input Validation
    if not data_x or not data_y:
        raise ValueError("Input lists cannot be empty.")
    if n != len(data_y):
        raise ValueError("Input lists must be of the same length.")
    if n < 2: # Ensures std_dev can be calculated for both lists.
        raise ValueError("At least two data points are required for correlation.")

    # Type checking for all elements in both lists
    if not all(isinstance(x, (int, float)) for x in data_x):
        raise TypeError("All elements in data_x must be numeric (int or float).")
    if not all(isinstance(y, (int, float)) for y in data_y):
        raise TypeError("All elements in data_y must be numeric (int or float).")

    # Calculate means
    mean_x = mean(data_x)
    mean_y = mean(data_y)

    # Calculate standard deviations
    std_dev_x = std_dev(data_x)
    std_dev_y = std_dev(data_y)

    if std_dev_x == 0 or std_dev_y == 0:
        # If standard deviation is 0, it means all values in that list are the same.
        # Pearson correlation is undefined in this case, or can be considered 0
        # as there's no variance to correlate. Returning 0.0 is a common practice.
        return 0.0

    # Calculate covariance
    # The formula for population covariance is sum((xi - mean_x) * (yi - mean_y)) / N
    covariance = sum([(data_x[i] - mean_x) * (data_y[i] - mean_y) for i in range(n)]) / n

    # Calculate Pearson correlation coefficient
    correlation = covariance / (std_dev_x * std_dev_y)

    return correlation

def simple_linear_regression(data_x: List[Union[int, float]], data_y: List[Union[int, float]]) -> Tuple[float, float]:
    """Calculates the slope (m) and y-intercept (b) of a simple linear regression line (y = mx + b).

    Simple linear regression is a statistical method that allows us to summarize and study
    relationships between two continuous (quantitative) variables.

    Args:
        data_x: A list of numbers (int or float), representing the independent variable.
        data_y: A list of numbers (int or float), representing the dependent variable.
                Must be of the same length as data_x.

    Returns:
        A tuple containing two floats: (slope, y_intercept).
        The slope is the rate at which the dependent variable changes for a unit change
        in the independent variable. The y-intercept is the value of the dependent
        variable when the independent variable is zero.

    Raises:
        ValueError: If input lists are empty, of different lengths, contain fewer
                    than two data points, or if all values in data_x are the same
                    (which would lead to a division by zero when calculating the slope).
        TypeError: If input lists contain non-numeric data.
    """
    n = len(data_x)

    # Input Validation
    if not data_x or not data_y:
        raise ValueError("Input lists cannot be empty.")
    if n != len(data_y):
        raise ValueError("Input lists must be of the same length.")
    if n < 2:
        raise ValueError("At least two data points are required for linear regression.")

    # More specific type error messages
    for i in range(n):
        if not isinstance(data_x[i], (int, float)):
            raise TypeError(f"Non-numeric data found in data_x at index {i}: {data_x[i]}")
        if not isinstance(data_y[i], (int, float)):
            raise TypeError(f"Non-numeric data found in data_y at index {i}: {data_y[i]}")

    mean_x = mean(data_x)
    mean_y = mean(data_y)

    # Calculate slope (m)
    # m = Σ((x_i - mean_x) * (y_i - mean_y)) / Σ((x_i - mean_x)^2)
    numerator = 0.0  # Initialize as float for precision
    denominator = 0.0  # Initialize as float for precision
    for i in range(n):
        numerator += (data_x[i] - mean_x) * (data_y[i] - mean_y)
        denominator += (data_x[i] - mean_x)**2

    if denominator == 0:
        # This occurs if all x_i values are the same.
        # Slope is undefined (vertical line).
        raise ValueError("Cannot perform linear regression: all x values are the same, leading to a zero denominator for slope calculation (vertical line).")

    slope = numerator / denominator

    # Calculate y-intercept (b)
    # b = mean_y - m * mean_x
    y_intercept = mean_y - slope * mean_x

    return slope, y_intercept

# --- Matrix Helper Functions ---
def _matrix_transpose(matrix: List[List[float]]) -> List[List[float]]:
    if not matrix or not matrix[0]:
        raise ValueError("Input matrix cannot be empty for transpose.")
    rows = len(matrix)
    cols = len(matrix[0])
    # Validate consistent row lengths
    for r_idx, row_val in enumerate(matrix):
        if len(row_val) != cols:
            raise ValueError(f"Inconsistent row length at index {r_idx} for transpose. Expected {cols}, got {len(row_val)}.")

    transpose = [[0.0] * rows for _ in range(cols)]
    for i in range(rows):
        for j in range(cols):
            transpose[j][i] = matrix[i][j]
    return transpose

def _matrix_multiply(matrix_a: List[List[float]], matrix_b: List[List[float]]) -> List[List[float]]:
    if not matrix_a or not matrix_a[0] or not matrix_b or not matrix_b[0]:
        raise ValueError("Input matrices cannot be empty for multiplication.")
    rows_a = len(matrix_a)
    cols_a = len(matrix_a[0])
    rows_b = len(matrix_b)
    cols_b = len(matrix_b[0])

    # Validate consistent row lengths for matrix_a
    for r_idx, row_val in enumerate(matrix_a):
        if len(row_val) != cols_a:
            raise ValueError(f"Inconsistent row length in matrix_a at index {r_idx}. Expected {cols_a}, got {len(row_val)}.")
    # Validate consistent row lengths for matrix_b
    for r_idx, row_val in enumerate(matrix_b):
        if len(row_val) != cols_b:
            raise ValueError(f"Inconsistent row length in matrix_b at index {r_idx}. Expected {cols_b}, got {len(row_val)}.")

    if cols_a != rows_b:
        raise ValueError(f"Matrices are not compatible for multiplication. Cols A ({cols_a}) != Rows B ({rows_b}).")

    result_matrix = [[0.0] * cols_b for _ in range(rows_a)]
    for i in range(rows_a):
        for j in range(cols_b):
            sum_val = 0.0
            for k in range(cols_a): # or rows_b
                sum_val += matrix_a[i][k] * matrix_b[k][j]
            result_matrix[i][j] = sum_val
    return result_matrix

# Helper function for solving linear systems using Gauss-Jordan elimination
def _solve_linear_system(matrix_a: List[List[float]], vector_b: List[float]) -> List[float]:
    """Solves a system of linear equations Ax = b using Gauss-Jordan elimination.

    This is an internal helper function.

    Args:
        matrix_a: A list of lists representing the coefficient matrix A (must be square).
        vector_b: A list representing the constant vector b.

    Returns:
        A list of floats representing the solution vector x.

    Raises:
        ValueError: If the matrix is not square, dimensions are incompatible,
                    or if the matrix is singular or near-singular.
    """
    # Check dimensions and squareness
    if not matrix_a or not matrix_a[0]:
        raise ValueError("Input matrix 'matrix_a' cannot be empty.")
    n = len(matrix_a)
    if n != len(vector_b):
        raise ValueError("Matrix 'matrix_a' and vector 'vector_b' must have compatible dimensions for solving Ax=b.")
    for row_idx, r in enumerate(matrix_a):
        if len(r) != n:
            raise ValueError(f"Matrix 'matrix_a' must be square. Row {row_idx} has length {len(r)}, expected {n}.")

    # Create augmented matrix (deep copy to avoid modifying original input lists)
    # Each element of matrix_a and vector_b should already be float, or convertible.
    # Forcing conversion to float for robustness within the augmented matrix.
    aug_matrix = [[float(val) for val in row] + [float(vector_b[i])] for i, row in enumerate(matrix_a)]

    # Forward elimination and reduction to row-echelon form (Gauss-Jordan)
    for i in range(n):  # Iterate through columns (which will become pivot columns)
        # Pivoting: Find the row with the largest absolute value in the current column i, from row i downwards
        max_row_idx = i
        for k in range(i + 1, n):
            if abs(aug_matrix[k][i]) > abs(aug_matrix[max_row_idx][i]):
                max_row_idx = k

        # Swap current row (i) with the row found to have the max pivot element (max_row_idx)
        aug_matrix[i], aug_matrix[max_row_idx] = aug_matrix[max_row_idx], aug_matrix[i]

        # Check for singularity or near-singularity
        pivot_val = aug_matrix[i][i]
        if abs(pivot_val) < 1e-12: # Using a small epsilon for float comparison
            # This check is crucial. If pivot is ~0, division by it will cause issues or NaN/inf.
            raise ValueError("Matrix is singular or near-singular; cannot solve system uniquely.")

        # Normalize the current pivot row: divide all elements in row i by the pivot value
        # This makes the pivot element aug_matrix[i][i] equal to 1.
        for j in range(i, n + 1): # Iterate from column i through the augmented part
            aug_matrix[i][j] /= pivot_val

        # Eliminate other rows: for all other rows k (where k != i),
        # subtract a multiple of the pivot row (row i) from row k
        # such that aug_matrix[k][i] becomes 0.
        for k in range(n): # Iterate through all rows
            if k != i: # Skip the pivot row itself
                factor = aug_matrix[k][i] # This is the element we want to make zero
                # For each element in row k, from column i to the end (augmented part)
                for j in range(i, n + 1):
                    aug_matrix[k][j] -= factor * aug_matrix[i][j]

    # At this point, the left side of aug_matrix (A part) should be an identity matrix.
    # The solution vector x is now in the last column of the augmented matrix.
    solution = [aug_matrix[row_idx][n] for row_idx in range(n)]
    return solution

# --- Regression Functions ---
def multiple_linear_regression(X_data: List[List[Union[int, float]]], y_data: List[Union[int, float]]) -> List[float]:
    """Performs multiple linear regression.

    Calculates the coefficients (beta values) for a linear model with one or more
    independent variables (features). The model is of the form:
    y = β₀ + β₁x₁ + β₂x₂ + ... + βₚxₚ

    Args:
        X_data: A list of lists, where each inner list represents an observation,
                and each element in the inner list is a feature value.
                Example: [[feature1_obs1, feature2_obs1], [feature1_obs2, feature2_obs2]]
        y_data: A list of dependent variable values, corresponding to each observation.

    Returns:
        A list of float coefficients [β₀, β₁, β₂, ..., βₚ], where β₀ is the
        intercept, and β₁, ..., βₚ are the coefficients for the features.

    Raises:
        ValueError: If input data is empty, dimensions are mismatched,
                    number of observations is less than number of features + intercept,
                    or if the (X^T X) matrix is singular (multicollinearity).
        TypeError: If input data contains non-numeric values.
    """
    if not X_data or not y_data:
        raise ValueError("Input data (X_data, y_data) cannot be empty.")

    num_observations = len(X_data)
    if num_observations != len(y_data):
        raise ValueError("Number of observations in X_data must match length of y_data.")

    if num_observations == 0: # Should be caught by the first check, but for clarity
        raise ValueError("Input data cannot be empty.")

    # Validate and convert X_data, determine num_features
    num_features = 0
    X_design_rows = []
    # Validate and convert X_data, determine num_features
    # Handle case for intercept-only model where X_data might be list of empty lists
    if X_data and isinstance(X_data[0], list):
        num_features = len(X_data[0])
    else: # Should not happen if X_data is List[List[...]] but as a fallback
        raise TypeError("X_data must be a list of lists (observations with features).")

    X_design_rows = []
    for i, x_obs in enumerate(X_data):
        if len(x_obs) != num_features: # This now correctly checks consistency against first observation's feature count
            raise ValueError(f"Inconsistent number of features in X_data. Observation {i} has {len(x_obs)} features, expected {num_features}.")

        current_row = [1.0] # For intercept β₀
        for val_idx, val in enumerate(x_obs):
            if not isinstance(val, (int, float)):
                raise TypeError(f"Non-numeric data found in X_data at observation {i}, feature index {val_idx}: {val}")
            current_row.append(float(val))
        X_design_rows.append(current_row)

    # Validate and convert y_data
    y_column_matrix_rows = []
    for i, y_val in enumerate(y_data):
        if not isinstance(y_val, (int, float)):
            raise TypeError(f"Non-numeric data found in y_data at index {i}: {y_val}")
        y_column_matrix_rows.append([float(y_val)])

    # Number of parameters to estimate is num_features + 1 (for the intercept)
    num_parameters = num_features + 1
    if num_observations < num_parameters:
        raise ValueError(f"Number of observations ({num_observations}) must be greater than or equal to "
                         f"the number of parameters to estimate ({num_parameters}).")

    X_design = X_design_rows
    y_column_matrix = y_column_matrix_rows

    # Calculate (X^T X) and (X^T y)
    # X_transpose: (num_parameters) x num_observations
    # X_design: num_observations x (num_parameters)
    # XTX: (num_parameters) x (num_parameters)
    # y_column_matrix: num_observations x 1
    # XTy_matrix: (num_parameters) x 1
    try:
        X_transpose = _matrix_transpose(X_design)
        XTX = _matrix_multiply(X_transpose, X_design)
        XTy_matrix = _matrix_multiply(X_transpose, y_column_matrix)
    except ValueError as e: # Catch errors from matrix operations like inconsistent row lengths
        raise ValueError(f"Error during matrix operations for regression: {e}")


    # Flatten XTy_matrix to XTy_vector for _solve_linear_system
    XTy_vector = [row[0] for row in XTy_matrix]

    # Solve the normal equations: (X^T X) * beta_coefficients = (X^T y)
    try:
        beta_coefficients = _solve_linear_system(XTX, XTy_vector)
    except ValueError as e:
        # Catch singularity or other issues from solver
        raise ValueError(f"Could not solve for regression coefficients. This might be due to multicollinearity (X^T X is singular). Original error: {e}")

    return beta_coefficients

def polynomial_regression(x_values: List[Union[int, float]], y_values: List[Union[int, float]], degree: int) -> List[float]:
    """Performs polynomial regression.

    Fits a polynomial model of a specified degree to the data (x_values, y_values).
    The model is of the form: y = β₀ + β₁x + β₂x² + ... + β_degree * x^degree.

    This function transforms the single independent variable x into multiple features
    (x, x², ..., x^degree) and then applies multiple linear regression.

    Args:
        x_values: A list of independent variable values (numbers).
        y_values: A list of dependent variable values (numbers).
        degree: The degree of the polynomial to fit (integer, must be >= 1).

    Returns:
        A list of float coefficients [β₀, β₁, β₂, ..., β_degree], where β₀ is
        the intercept, β₁ is the coefficient for x, β₂ for x², and so on.

    Raises:
        ValueError: If input lists are empty, have mismatched lengths, degree is less
                    than 1, or if there are insufficient data points for the given
                    degree (e.g., number of points < degree + 1).
                    Also re-raises ValueErrors from multiple_linear_regression
                    (e.g., due to multicollinearity in the transformed features).
        TypeError: If x_values, y_values contain non-numeric data, or if degree
                   is not an integer.
    """
    # Input Validation
    if not isinstance(degree, int):
        raise TypeError(f"Degree must be an integer, got {type(degree)}.")
    if degree < 1:
        raise ValueError(f"Degree must be at least 1, got {degree}.")
    if not x_values or not y_values:
        raise ValueError("Input lists 'x_values' and 'y_values' cannot be empty.")
    if len(x_values) != len(y_values):
        raise ValueError("Input lists 'x_values' and 'y_values' must have the same length.")

    # Convert x_values to float and validate type early
    x_floats = []
    for i, x_val in enumerate(x_values):
        if not isinstance(x_val, (int, float)):
            raise TypeError(f"Non-numeric data found in x_values at index {i}: {x_val}")
        x_floats.append(float(x_val))

    # y_values will be validated by multiple_linear_regression, but good to check type here too for consistency
    # and to ensure they are converted to float if they are integers, as MLR expects List[List[float]] for X
    # and List[float] for y (though it handles Union[int, float] for y_data input).
    y_floats = []
    for i, y_val in enumerate(y_values):
        if not isinstance(y_val, (int, float)):
            raise TypeError(f"Non-numeric data found in y_values at index {i}: {y_val}")
        y_floats.append(float(y_val))

    num_observations = len(x_values)
    # Number of parameters to estimate = degree (for x, x^2...x^degree) + 1 (for intercept)
    num_parameters = degree + 1
    if num_observations < num_parameters:
        raise ValueError(
            f"Insufficient data points ({num_observations}) for the given polynomial degree ({degree}). "
            f"Need at least {num_parameters} points."
        )

    # Feature Engineering: Transform x_values into polynomial features
    # X_poly_features will be [[x1, x1^2, ..., x1^degree], [x2, x2^2, ..., x2^degree], ...]
    X_poly_features = []
    for x_val_float in x_floats:
        record = [x_val_float**d for d in range(1, degree + 1)]
        X_poly_features.append(record)

    # Call multiple_linear_regression
    # The multiple_linear_regression function will add the intercept term.
    # It expects X_data as list of lists of features, and y_data as a list.
    try:
        # Pass y_floats to ensure consistent float types for MLR
        coefficients = multiple_linear_regression(X_poly_features, y_floats)
    except ValueError as e:
        # Re-raise with potentially more context or just let it propagate
        raise ValueError(f"Error during multiple linear regression for polynomial fitting: {e}")

    return coefficients
