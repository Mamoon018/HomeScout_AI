def get_welcome_message(*, user_id: str, user_name: str) -> str:
    """Build a greeting scoped to this user. user_id is required even though the copy uses the name."""
    if not user_id:
        raise ValueError("user_id is required")
    if not user_name:
        raise ValueError("user_name is required")
    return f"Welcome {user_name}!"
