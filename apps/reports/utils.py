def _to_date(value):
    """Accepts either a date or a datetime and returns a date."""
    return value.date() if hasattr(value, "date") else value


def bucket_key(value, period):
    """Groups a date/datetime into a daily/weekly/monthly bucket label."""
    d = _to_date(value)
    if period == "daily":
        return d.isoformat()
    if period == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return d.strftime("%Y-%m")
