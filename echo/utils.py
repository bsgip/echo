def _to_values(profile, key):
    if isinstance(profile, dict):
        return profile[key]
    return dict(enumerate(profile[key].values))