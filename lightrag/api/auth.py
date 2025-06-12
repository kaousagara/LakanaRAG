from datetime import datetime, timedelta

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from pydantic import BaseModel

from .config import global_args
import json
import os

# use the .env that is inside the current folder
# allows to use different .env file for each lightrag instance
# the OS environment variables take precedence over the .env file
load_dotenv(dotenv_path=".env", override=False)


class TokenPayload(BaseModel):
    sub: str  # Username
    exp: datetime  # Expiration time
    role: str = "user"  # User role, default is regular user
    metadata: dict = {}  # Additional metadata


class AuthHandler:
    def __init__(self):
        self.secret = global_args.token_secret
        self.algorithm = global_args.jwt_algorithm
        self.expire_hours = global_args.token_expire_hours
        self.guest_expire_hours = global_args.guest_token_expire_hours
        self.accounts_file = global_args.accounts_file
        self.accounts = {}
        if os.path.isfile(self.accounts_file):
            try:
                with open(self.accounts_file, "r", encoding="utf-8") as f:
                    self.accounts = json.load(f)
            except Exception:
                self.accounts = {}
        else:
            auth_accounts = global_args.auth_accounts
            if auth_accounts:
                for i, account in enumerate(auth_accounts.split(",")):
                    username, password = account.split(":", 1)
                    role = "admin" if i == 0 else "user"
                    self.accounts[username] = {
                        "password": password,
                        "role": role,
                        "active": True,
                    }
            self._save_accounts()

    def _save_accounts(self):
        try:
            with open(self.accounts_file, "w", encoding="utf-8") as f:
                json.dump(self.accounts, f)
        except Exception:
            pass

    def list_accounts(self):
        return [
            {"username": u, **v}
            for u, v in self.accounts.items()
        ]

    def add_account(self, username: str, password: str, role: str = "user", active: bool = True):
        self.accounts[username] = {"password": password, "role": role, "active": active}
        self._save_accounts()

    def update_account(self, username: str, password: str | None = None, role: str | None = None, active: bool | None = None):
        account = self.accounts.get(username)
        if not account:
            raise KeyError("Account not found")
        if password is not None:
            account["password"] = password
        if role is not None:
            account["role"] = role
        if active is not None:
            account["active"] = active
        self.accounts[username] = account
        self._save_accounts()

    def delete_account(self, username: str):
        if username in self.accounts:
            del self.accounts[username]
            self._save_accounts()

    def create_token(
        self,
        username: str,
        role: str = "user",
        custom_expire_hours: int = None,
        metadata: dict = None,
    ) -> str:
        """
        Create JWT token

        Args:
            username: Username
            role: User role, default is "user", guest is "guest"
            custom_expire_hours: Custom expiration time (hours), if None use default value
            metadata: Additional metadata

        Returns:
            str: Encoded JWT token
        """
        # Choose default expiration time based on role
        if custom_expire_hours is None:
            if role == "guest":
                expire_hours = self.guest_expire_hours
            else:
                expire_hours = self.expire_hours
        else:
            expire_hours = custom_expire_hours

        expire = datetime.utcnow() + timedelta(hours=expire_hours)

        # Create payload
        payload = TokenPayload(
            sub=username, exp=expire, role=role, metadata=metadata or {}
        )

        return jwt.encode(payload.dict(), self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> dict:
        """
        Validate JWT token

        Args:
            token: JWT token

        Returns:
            dict: Dictionary containing user information

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            expire_timestamp = payload["exp"]
            expire_time = datetime.utcfromtimestamp(expire_timestamp)

            if datetime.utcnow() > expire_time:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
                )

            # Return complete payload instead of just username
            return {
                "username": payload["sub"],
                "role": payload.get("role", "user"),
                "metadata": payload.get("metadata", {}),
                "exp": expire_time,
            }
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )


auth_handler = AuthHandler()
