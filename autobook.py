import argparse
import atexit
import signal
import subprocess
import time
from datetime import datetime, timedelta

import pytz

from extract_authentication_headers import extract_authentication_headers
from reserve import reserve

CENTRAL_TZ = pytz.timezone("America/Chicago")

AUTH_HOUR = 8
AUTH_MINUTE = 55
BOOK_HOUR = 9
BOOK_MINUTE = 0


def start_caffeinate() -> subprocess.Popen:
    proc = subprocess.Popen(["caffeinate", "-i"])
    atexit.register(proc.terminate)
    signal.signal(signal.SIGTERM, lambda *_: (proc.terminate(), exit(0)))
    return proc


def now_central() -> datetime:
    return datetime.now(tz=CENTRAL_TZ)


def central_today_at(hour: int, minute: int, second: int = 0) -> datetime:
    now = now_central()
    return CENTRAL_TZ.localize(
        datetime(now.year, now.month, now.day, hour, minute, second)
    )


def hybrid_wait_until(target: datetime, label: str, on_status=None) -> None:
    """Sleep coarsely until close to `target`, then tight-poll the final seconds."""
    msg = f"Waiting until {target.strftime('%H:%M:%S %Z')} ({label})..."
    print(msg)
    if on_status:
        on_status(msg)

    while True:
        remaining = (target - now_central()).total_seconds()
        if remaining <= 0:
            break
        if remaining > 5:
            # coarse sleep — wake up with 5 seconds to spare
            time.sleep(remaining - 5)
        else:
            # tight poll for the final stretch
            time.sleep(0.01)

    print(f"It's {now_central().strftime('%H:%M:%S %Z')} — proceeding with {label}.")


def booking_window_date(date: str) -> datetime:
    """Return the date the booking window opens for a given target date."""
    target_date = datetime.strptime(date, "%Y-%m-%d")
    return (target_date - timedelta(days=8)).date()


def is_too_early(date: str) -> bool:
    """Check if the booking window hasn't opened yet for the given date."""
    return booking_window_date(date) > now_central().date()


def autobook(
    date: str,
    book_time: str,
    court: int = 3,
    duration: int = 90,
    on_status=None,
) -> None:
    """Run the full autobook flow. Optional `on_status` callback receives status strings.

    When called from CLI, the too-early check is handled via input().
    When called from the GUI, the caller should check is_too_early() beforehand
    and handle the prompt itself.
    """
    caffeinate_proc = start_caffeinate()
    print("Caffeinate started — macOS will stay awake until this script exits.")

    target_date = datetime.strptime(date, "%Y-%m-%d")
    run_date = (target_date - timedelta(days=8)).date()
    today = now_central().date()

    # CLI-only too-early guard — GUI callers should check is_too_early() first
    if run_date > today and on_status is None:
        answer = input(
            f"Booking window for {date} doesn't open until {run_date}. Proceed anyway? (y/n): "
        )
        if answer.strip().lower() != "y":
            print("Exiting.")
            return

    now = now_central()
    auth_time = central_today_at(AUTH_HOUR, AUTH_MINUTE)
    book_time_target = central_today_at(BOOK_HOUR, BOOK_MINUTE)

    past_book = now >= book_time_target
    past_auth = now >= auth_time

    if not past_auth:
        hybrid_wait_until(auth_time, "authentication", on_status)

    if on_status:
        on_status("Authenticating...")
    print()
    extract_authentication_headers()
    print()

    if not past_book:
        hybrid_wait_until(book_time_target, "booking", on_status)

    if on_status:
        on_status("Booking...")
    print()
    reserve(date=date, time=book_time, court=court, duration=duration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Wait until the booking window opens, then authenticate and book a court.",
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Date to book. Format: YYYY-MM-DD. Example: 2025-04-28",
    )
    parser.add_argument(
        "--time",
        type=str,
        required=True,
        help="Time to book. Format: HH:MM (24-hour format). Example: 14:30",
    )
    parser.add_argument(
        "--court",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Court number. Default is 3.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        choices=[30, 60, 90],
        default=90,
        help="Length of the booking. Default is 90 minutes.",
    )
    args = parser.parse_args()
    autobook(
        date=args.date,
        book_time=args.time,
        court=args.court,
        duration=args.duration,
    )
