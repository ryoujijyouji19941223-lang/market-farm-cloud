from datetime import datetime

def verified_public_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("public release time must include timezone")
    return dt

def usable_before_target(released_at: str, target_at: str) -> bool:
    release = verified_public_time(released_at)
    target = verified_public_time(target_at)
    return release < target
