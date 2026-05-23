#!/usr/bin/env python3
"""
Generate synthetic trip CSV fixtures for load testing.

Usage:
  python3 gen_trips.py [--sizes SIZE1 SIZE2 ...] [--output-dir PATH]

Output:
  trips_1k.csv  (1000 trips)
  trips_5k.csv  (5000 trips)
  trips_10k.csv (10000 trips)

Schema (compatible with POST /operations/upload):
  tripId,lineCode,startTime,endTime,originId,destinationId

Constraints:
  - startTime != endTime (valid duration)
  - originId != destinationId (no loops; they're filtered by backend)
  - Times in minutes-from-midnight (0-1440)
  - Realistic distribution: operating hours 6h-22h (360-1320 min), 20-90 min duration
"""
import csv
import random
import argparse
import sys
from pathlib import Path


def generate_trips(count: int, seed: int = 42) -> list[dict]:
    """Generate realistic synthetic trips.

    Args:
        count: number of trips to generate
        seed: random seed for reproducibility

    Returns:
        List of dicts with keys: tripId, lineCode, startTime, endTime, originId, destinationId
    """
    random.seed(seed)
    trips = []

    # Operating window: 6h (360 min) to 22h (1320 min)
    MIN_START = 360
    MAX_START = 1320
    MIN_DURATION = 20
    MAX_DURATION = 90

    # Number of lines (realistic: 1-10 depending on dataset size)
    num_lines = max(1, count // 500)

    # Number of origins/destinations (realistic: 10-200 depending on size)
    num_origins = max(5, min(200, count // 50))

    for i in range(1, count + 1):
        start_time = random.randint(MIN_START, MAX_START)
        duration = random.randint(MIN_DURATION, MAX_DURATION)
        end_time = start_time + duration

        # Wrap to next day if needed (realistic for overnight routes)
        if end_time > 1440:
            end_time = end_time % 1440

        # Origin != Destination (backend filters loops)
        origin = random.randint(1, num_origins)
        destination = random.randint(1, num_origins)
        while destination == origin:
            destination = random.randint(1, num_origins)

        line_id = random.randint(1, num_lines)

        trips.append({
            'tripId': i,
            'lineCode': f'L{line_id}',
            'startTime': start_time,
            'endTime': end_time,
            'originId': origin,
            'destinationId': destination,
        })

    return trips


def write_csv(trips: list[dict], output_path: Path) -> None:
    """Write trips to CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['tripId', 'lineCode', 'startTime', 'endTime', 'originId', 'destinationId']
        )
        writer.writeheader()
        writer.writerows(trips)

    print(f"✅ Generated {len(trips)} trips → {output_path.name} ({output_path.stat().st_size} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--sizes',
        nargs='+',
        type=int,
        default=[1000, 5000, 10000],
        help='Trip counts to generate (default: 1000 5000 10000)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).parent,
        help='Output directory (default: same dir as script)'
    )

    args = parser.parse_args()

    print(f"🔄 Generating {len(args.sizes)} datasets: {args.sizes}")

    for size in sorted(args.sizes):
        trips = generate_trips(size)

        # Map size to filename
        if size == 1000:
            filename = 'trips_1k.csv'
        elif size == 5000:
            filename = 'trips_5k.csv'
        elif size == 10000:
            filename = 'trips_10k.csv'
        else:
            filename = f'trips_{size}.csv'

        output_path = args.output_dir / filename
        write_csv(trips, output_path)

    print(f"\n✅ All datasets generated in {args.output_dir}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
