import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

# Ensure this file's directory is on sys.path so implicit namespace packages work
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from utils.logger import get_logger
from utils.request_manager import RequestManager
from output.exporter import Exporter
from parsers.linkedin_profile_parser import LinkedInProfileParser

CONFIG_PATH = os.path.join(THIS_DIR, "config", "settings.json")
DATA_DIR = os.path.join(os.path.dirname(THIS_DIR), "data")

def load_settings(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Missing settings file at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def read_input_urls(path: str) -> List[str]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="LinkedIn Person Data Scraper - extract public profile data into JSON."
    )
    p.add_argument(
        "-i", "--input",
        default=os.path.join(DATA_DIR, "input_urls.txt"),
        help="Path to a text file containing LinkedIn profile URLs (one per line)."
    )
    p.add_argument(
        "-o", "--output",
        default=os.path.join(DATA_DIR, f"output_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"),
        help="Path to write the JSON results."
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent workers (currently processed sequentially but reserved for future parallelism)."
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Per-request timeout in seconds; overrides settings.json if provided."
    )
    p.add_argument(
        "--user-agent",
        type=str,
        default=None,
        help="Custom User-Agent; overrides settings.json if provided."
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay (seconds) between requests; overrides settings.json if provided."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Process inputs and log results without writing output file."
    )
    p.add_argument(
        "--html-file",
        type=str,
        default=None,
        help="If provided, parse this local HTML file for every input URL (useful for testing parser without network)."
    )
    return p

def main():
    ensure_dir(DATA_DIR)
    args = build_arg_parser().parse_args()
    settings = load_settings(CONFIG_PATH)

    # Override settings from CLI if provided
    if args.timeout is not None:
        settings["network"]["timeout"] = args.timeout
    if args.user_agent is not None:
        settings["network"]["default_user_agent"] = args.user_agent
    if args.delay is not None:
        settings["throttling"]["delay_seconds"] = args.delay

    logger = get_logger(name="linkedin_scraper", level=settings.get("logging", {}).get("level", "INFO"))

    input_urls = read_input_urls(args.input)
    if not input_urls:
        logger.warning("No input URLs found. Provide at least one LinkedIn profile URL in the input file.")
        return

    req = RequestManager(
        timeout=settings["network"]["timeout"],
        default_headers={"User-Agent": settings["network"]["default_user_agent"]},
        max_retries=settings["network"]["max_retries"],
        backoff_base=settings["network"]["retry_backoff_seconds"],
        logger=logger
    )
    parser = LinkedInProfileParser(logger=logger)
    exporter = Exporter(logger=logger)

    delay = float(settings["throttling"]["delay_seconds"])
    results: List[Dict[str, Any]] = []

    for idx, url in enumerate(input_urls, start=1):
        logger.info(f"[{idx}/{len(input_urls)}] Processing: {url}")
        try:
            if args.html_file:
                # Local parse for testing
                logger.debug(f"Parsing local HTML file for URL {url}: {args.html_file}")
                with open(args.html_file, "r", encoding="utf-8") as f:
                    html = f.read()
            else:
                html = req.get(url)

            data = parser.parse_profile(url=url, html=html)
            results.append(data)
            logger.info(f"Parsed profile: {data.get('fullName') or '(name not found)'} from {url}")
        except Exception as e:
            logger.exception(f"Failed to process {url}: {e}")
        finally:
            if idx < len(input_urls):
                time.sleep(delay)

    if args.dry_run:
        logger.info("Dry-run enabled; not writing output file.")
        logger.info(json.dumps(results, indent=2, ensure_ascii=False))
        return

    ensure_dir(os.path.dirname(args.output))
    exporter.to_json(results, args.output)
    logger.info(f"Saved {len(results)} profiles to {args.output}")

if __name__ == "__main__":
    main()