"""Dump all Mem0 cloud entries as raw JSON."""
import os
import json
import argparse
from dotenv import load_dotenv
from mem0 import MemoryClient

load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Dump Mem0 cloud entries as raw JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dump all users
  uv run python dump_mem0_entries.py

  # Dump specific user
  uv run python dump_mem0_entries.py --user-id alice

  # Save to custom file
  uv run python dump_mem0_entries.py --output custom_dump.json
"""
    )
    parser.add_argument(
        "--user-id",
        type=str,
        help="Specific user_id to dump (default: all known users)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="mem0_dump.json",
        help="Output JSON file (default: mem0_dump.json)"
    )

    args = parser.parse_args()

    MEM0_API_KEY = os.getenv("MEM0_API_KEY")
    if not MEM0_API_KEY:
        print("ERROR: MEM0_API_KEY not found in environment")
        print("Get your free API key from https://app.mem0.ai/dashboard")
        exit(1)

    client = MemoryClient(api_key=MEM0_API_KEY)

    # Determine which users to query
    if args.user_id:
        users_to_query = [args.user_id]
        print(f"\n{'='*70}")
        print(f"Dumping Mem0 Entries for user_id: {args.user_id}")
        print("="*70 + "\n")
    else:
        # Query all known users
        users_to_query = [
            "demo_user",
            "alice",
            "carol"

        ]
        print(f"\n{'='*70}")
        print("Dumping ALL Mem0 Cloud Entries (all known users)")
        print("="*70 + "\n")

    all_entries = []

    for user_id in users_to_query:
        print(f"\nFetching memories for user_id: {user_id}...")

        try:
            response = client.get_all(filters={"user_id": user_id}, version="v2")
            if isinstance(response, dict):
                memories = response.get("results", response.get("memories", []))
            else:
                memories = response if isinstance(response, list) else []

            print(f"  Found {len(memories)} memories")

            for mem in memories:
                mem["_queried_user_id"] = user_id
                all_entries.append(mem)

            if not memories:
                print(f"  No memories found for {user_id}")
        except Exception as e:
            print(f"  Error fetching memories for {user_id}: {e}")

    print(f"\n{'='*70}")
    print(f"Total entries retrieved: {len(all_entries)}")
    print("="*70 + "\n")

    # Write to JSON file
    with open(args.output, "w") as f:
        json.dump(all_entries, f, indent=2, default=str)

    print(f"✓ Saved to {args.output}")

    # Also print to console for quick inspection
    print(f"\n{'='*70}")
    print(f"Sample entries (first 3):")
    print("="*70 + "\n")

    for i, entry in enumerate(all_entries[:3], 1):
        print(f"\nEntry {i}:")
        print(json.dumps(entry, indent=2, default=str))
        print()

    if len(all_entries) > 3:
        print(f"... and {len(all_entries) - 3} more entries")

    print(f"\n✓ Full dump available in: {args.output}\n")


if __name__ == "__main__":
    main()
