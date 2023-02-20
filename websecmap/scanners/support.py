from typing import List


def kwargs_to_params(kwargs, prefix="-") -> List[str]:
    """
    Convert a dictionary of keyword arguments to a list of command-line
    parameters.

    """

    arguments = []

    if not kwargs:
        return arguments

    if "SPECIAL_DIRECT" in kwargs:
        arguments.append(kwargs["SPECIAL_DIRECT"])

    if "args" not in kwargs:
        return arguments

    for arg in kwargs["args"]:

        param = f"{prefix}{arg['name']}"

        if arg["type"] == "no-value":
            arguments.append(param)

        # Directly used argument
        if arg["type"] == "single-argument":
            arguments.extend((param, arg["value"]))

        # Kwargs are dicts, usual dicts are reduced to one unique key. So {"test": 1, "test": 2} = {"test": 2}
        if arg["type"] == "list-to-duplicate-arguments":
            for subarg in arg["value"]:
                arguments.extend((param, subarg))

        if arg["type"] == "list-to-single-csv-argument":
            arguments.extend((param, ",".join(arg["value"])))

    return arguments
