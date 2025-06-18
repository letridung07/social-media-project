import math
from typing import List, Union, Tuple

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
