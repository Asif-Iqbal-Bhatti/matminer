def flatten_dict(nested_dict, lead_key=None, unwind_arrays=True):
    """
    Helper function to flatten nested dictionary, recursively
    walks through nested dictionary to get keys corresponding
    to dot-notation keys, e. g. converts
    {"a": {"b": 1, "c": 2}} to {"a.b": 1, "a.c": 2}

    Args:
        nested_dict ({}): nested dictionary to flatten
        unwind_arrays (bool): whether to flatten lists/tuples
            with numerically indexed dot notation, defaults to True
        lead_key (str): string to append to front of all keys,
            used primarily for recursion

    Returns:
        non-nested dictionary
    """
    flattened = {}

    for key, value in nested_dict.items():
        flat_key = f"{lead_key}.{key}" if lead_key else key

        if isinstance(value, dict):
            flattened |= flatten_dict(value, flat_key, unwind_arrays)

        elif isinstance(value, (list, tuple)) and unwind_arrays:
            array_dict = dict(enumerate(value))
            flattened.update(flatten_dict(array_dict, flat_key, unwind_arrays))

        else:
            flattened[flat_key] = value
    return flattened
