"""Run from repository root: python backend/manage_users.py --username ... --role hr"""
import argparse
import sqlite3
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv

from auth import AuthService
from data_loader import get_data_loader
from rewards import RewardsStore


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Create a local Career Quest account; password is read securely")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=["employee", "hr"], required=True)
    parser.add_argument("--employee-id")
    args = parser.parse_args()
    store = RewardsStore()
    loader = get_data_loader()
    store.restore(loader)
    if args.role == "employee" and (not args.employee_id or not loader.get_employee(args.employee_id)):
        parser.error("Specify an existing employee using --employee-id")
    password = getpass("Password (12+ characters): ")
    if password != getpass("Repeat password: "):
        parser.error("Passwords do not match")
    try:
        AuthService(store).create_user(args.username, password, args.role, args.employee_id)
    except (ValueError, sqlite3.IntegrityError) as exc:
        parser.error(f"Cannot create account: {exc}")
    print(f"Account created: {args.username}, role: {args.role}")


if __name__ == "__main__":
    main()
