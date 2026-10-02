from users import User, UserRepository


def validate_and_save_user(repository: UserRepository, email: str, password: str, display_name: str) -> User:
    user = User(email=trim_and_lowercase(email), password_hash=password, display_name=display_name)
    repository.add(user)
    return user


def trim_and_lowercase(email: str) -> str:
    return email.strip().lower()
