#!/usr/bin/env python3
"""
CLI tool for managing API keys.

Usage:
    python manage_api_keys.py create "My App" --rate-limit 200
    python manage_api_keys.py revoke loco_xxxxxxxxxxxxx
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.api.auth import APIKeyManager


def create_key(name: str, rate_limit: int):
    """Create a new API key."""
    print(f"Creating API key for: {name}")
    print(f"Rate limit: {rate_limit} requests/hour")
    
    api_key = APIKeyManager.create_api_key(name, rate_limit)
    
    print("\n" + "="*60)
    print("✅ API Key Created Successfully!")
    print("="*60)
    print(f"\nAPI Key: {api_key}")
    print("\n⚠️  IMPORTANT: Save this key now! It won't be shown again.")
    print("\nUsage:")
    print(f'  curl -H "X-API-Key: {api_key}" \\')
    print('       https://your-domain.com/api/v1/events/search \\')
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"city": "San Francisco", "max_pages": 3}\'')
    print("="*60 + "\n")


def revoke_key(api_key: str):
    """Revoke an API key."""
    print(f"Revoking API key: {api_key[:15]}...")
    
    success = APIKeyManager.revoke_key(api_key)
    
    if success:
        print("✅ API key revoked successfully!")
    else:
        print("❌ API key not found!")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Manage API keys for Local Life Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new API key
  python manage_api_keys.py create "My Application"
  
  # Create with custom rate limit
  python manage_api_keys.py create "High Volume App" --rate-limit 500
  
  # Revoke an API key
  python manage_api_keys.py revoke loco_xxxxxxxxxxxxx
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("name", help="Descriptive name for the API key")
    create_parser.add_argument(
        "--rate-limit",
        type=int,
        default=100,
        help="Requests per hour limit (default: 100)",
    )
    
    # Revoke command
    revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key")
    revoke_parser.add_argument("api_key", help="API key to revoke")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "create":
        create_key(args.name, args.rate_limit)
    elif args.command == "revoke":
        revoke_key(args.api_key)


if __name__ == "__main__":
    main()

