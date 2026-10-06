def unused_sheet_name(stem, *workbooks):
    """Use one collision-free input name in both outputs; keep history inputs."""
    used = {name.casefold() for book in workbooks for name in book}
    candidate = stem[:31]
    number = 2
    while candidate.casefold() in used:
        suffix = '_' + str(number)
        candidate = stem[:31-len(suffix)] + suffix
        number += 1
    return candidate
