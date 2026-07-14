#!/usr/bin/env python3
"""
jobs_scraper.py - Scraper pentru rezultatele de căutare jobs.ch.

Nu folosește un browser headless: lista de job-uri e extrasă din
JSON-ul embedat (window.__INIT__) în HTML-ul paginii de căutare
(server-side rendered), iar detaliile (inclusiv descrierea) vin
de la endpoint-ul public REST al jobs.ch.

Vezi CLAUDE.md pentru arhitectură, endpoint-uri și note de extindere.

Usage:
    python jobs_scraper.py "<jobs.ch search URL>" [--output jobs.json] [--min-delay 1] [--max-delay 3]
"""

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

from tasks.filter_jobs_for_AI import is_engineer_role, write_parsed_jobs

LOG_FILE = "logs/scrape_run.log"

logger = logging.getLogger("jobs_scraper")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DETAIL_API = "https://www.jobs.ch/api/v1/public/search/job/{job_id}"
DETAIL_JOB_URL = "https://www.jobs.ch/en/vacancies/detail/{job_id}"

# URL de căutare implicit, folosit dacă nu se pasează unul explicit ca argument.
# Filtrele (category, region, publication-date etc.) se pot schimba în timp;
# formatul de bază al URL-ului rămâne același.
# DEFAULT_SEARCH_URL = (
#     "https://www.jobs.ch/en/vacancies/information-technology-telecom/testing-audit-security/"
#     "?category=170&category=171&category=174&category=175&category=176&category=177&category=179"
#     "&employment-type=5&language-skill=en&publication-date=30"
#     "&region=7&region=11&region=12&region=13&region=14&region=15"
#     "&term=&jobid=1a04b9c3-6b7d-42e2-b2a7-a1e07ee2b481"
# )

# DEFAULT_SEARCH_URL = "https://www.jobs.ch/en/vacancies/information-technology-telecom/testing-audit-security/?category=170&category=171&category=174&category=175&category=176&category=177&category=178&category=179&category=180&employment-type=2&employment-type=5&language-skill=de&publication-date=30&region=7&region=11&region=12&region=13&region=14&region=15&term=" #German
# DEFAULT_SEARCH_URL = "https://www.jobs.ch/en/vacancies/information-technology-telecom/testing-audit-security/?category=170&category=171&category=174&category=175&category=176&category=177&category=178&category=179&category=180&employment-type=2&employment-type=5&language-skill=en&publication-date=30&region=7&region=11&region=12&region=13&region=14&region=15&term=" #English
DEFAULT_SEARCH_URL = "https://www.jobs.ch/en/vacancies/information-technology-telecom/testing-audit-security/?category=170&category=171&category=174&category=175&category=176&category=177&category=178&category=179&category=180&employment-type=2&employment-type=5&language-skill=de&language-skill=en&publication-date=30&region=7&region=11&region=12&region=13&region=14&region=15&term=" #English + German

def build_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-CH,en;q=0.9",
    })
    return s


def extract_init_json(html):
    """
    Pagina de căutare embedează mai multe variabile JS în același
    <script> tag: __GLOBAL__, __INIT__, __TRANSLATIONS__,
    __REACT_QUERY_STATE__ etc. Nu putem despărți după numele
    următoarei variabile (nu e un delimitator stabil), așa că găsim
    "__INIT__ = " și apoi folosim json.JSONDecoder.raw_decode ca să
    parsăm DOAR obiectul JSON valid care urmează, ignorând restul JS.
    """
    marker = "__INIT__"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("Nu am găsit __INIT__ în pagină")

    brace_idx = html.find("{", idx)
    if brace_idx == -1:
        raise ValueError("Nu am găsit '{' după __INIT__")

    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(html, brace_idx)
    return obj


def fetch_search_page(session, url, page):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs["page"] = [str(page)]
    new_query = urlencode(qs, doseq=True)
    page_url = urlunparse(parsed._replace(query=new_query))
    resp = session.get(page_url, timeout=30)
    resp.raise_for_status()
    return page_url, extract_init_json(resp.text)


def fetch_job_detail(session, job_id):
    resp = session.get(DETAIL_API.format(job_id=job_id), timeout=30)
    resp.raise_for_status()
    return resp.json()


def make_key(name, role):
    """Cheie unică stabilă, derivată din name + role (case-insensitive)."""
    raw = f"{name.strip().lower()}||{role.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def polite_sleep(min_delay, max_delay):
    time.sleep(random.uniform(min_delay, max_delay))


def load_existing(path):
    if path.exists() and path.stat().st_size > 0:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return {job["key"]: job for job in data}
    return {}


def save_jobs(path, jobs_by_key):
    with path.open("w", encoding="utf-8") as f:
        json.dump(list(jobs_by_key.values()), f, ensure_ascii=False, indent=2)


def setup_logging():
    """Loghează atât în consolă, cât și cumulativ (append) în LOG_FILE,
    cu dată și oră pe fiecare linie, astfel încât fiecare rulare a
    scriptului să rămână identificabilă în istoricul din fișier."""
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = Path(LOG_FILE)
    if log_path.exists() and log_path.stat().st_size > 0:
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n")

    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def main():
    parser = argparse.ArgumentParser(description="Scrape jobs.ch search results into jobs.json")
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_SEARCH_URL,
        help="URL de căutare jobs.ch (cu filtrele deja aplicate). "
             "Dacă lipsește, se folosește DEFAULT_SEARCH_URL din script.",
    )
    parser.add_argument("--output", default="json/jobs.json", help="Fișier JSON de output (default: jobs.json)")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Delay minim între cereri (secunde)")
    parser.add_argument("--max-delay", type=float, default=2.0, help="Delay maxim între cereri (secunde)")
    args = parser.parse_args()

    setup_logging()
    run_start = datetime.now()
    output_path = Path(args.output)
    session = build_session()

    logger.info(f"Fetching page 1: {args.url}")
    _, first_page_data = fetch_search_page(session, args.url, 1)
    main_results = first_page_data["vacancy"]["results"]["main"]
    num_pages = main_results["meta"]["numPages"]
    total_hits = main_results["meta"]["totalHits"]
    logger.info(f"Găsite {total_hits} job-uri pe {num_pages} pagini")

    all_list_items = list(main_results["results"])

    for page in range(2, num_pages + 1):
        polite_sleep(args.min_delay, args.max_delay)
        logger.info(f"Fetching page {page}/{num_pages}")
        _, page_data = fetch_search_page(session, args.url, page)
        all_list_items.extend(page_data["vacancy"]["results"]["main"]["results"])

    logger.info(f"Colectate {len(all_list_items)} intrări din listă. Preiau detaliile...")

    jobs_by_key = load_existing(output_path)
    logger.info(f"Încărcate {len(jobs_by_key)} job-uri existente din {output_path}")

    new_count = 0
    for i, item in enumerate(all_list_items, 1):
        job_id = item["id"]
        role = item.get("title", "")
        company_name = item.get("company", {}).get("name", "")
        key = make_key(company_name, role)

        if key in jobs_by_key:
            continue  # deja există acest name+role, sărim peste fetch-ul de detaliu

        polite_sleep(args.min_delay, args.max_delay)
        logger.info(f"[{i}/{len(all_list_items)}] Fetching detail: {role} @ {company_name}")
        try:
            detail = fetch_job_detail(session, job_id)
        except requests.RequestException as e:
            logger.error(f"  EROARE la fetch detaliu job {job_id}: {e}")
            continue

        company_slug = detail.get("company_slug", "")
        company_url = f"https://www.jobs.ch/en/companies/{company_slug}/" if company_slug else ""
        city = detail.get("place", item.get("place", ""))
        description_html = detail.get("template_text", "")
        job_url = DETAIL_JOB_URL.format(job_id=job_id)
        publication_date = detail.get("publication_date", "")
        application_url = detail.get("application_url", "")

        jobs_by_key[key] = {
            "key": key,
            "company_name": detail.get("company_name", company_name),
            "company_url": company_url,
            "company_city": city,
            "job_role": detail.get("title", role),
            "job_url": job_url,
            "job_description": description_html,
            "engineer": is_engineer_role(description_html),
            "german": "",
            "match": 0,
            "stack": "",
            "cover_letter": "",
            "application_url": application_url,
            "publication_date": publication_date
        }
        new_count += 1

    save_jobs(output_path, jobs_by_key)
    logger.info(f"Gata. Adăugate {new_count} job-uri noi. Total în {output_path}: {len(jobs_by_key)}")

    parsed_count = write_parsed_jobs(list(jobs_by_key.values()))
    logger.info(f"jobs_parsed.json rescris cu {parsed_count} job-uri (engineer=True)")

    elapsed = int((datetime.now() - run_start).total_seconds())
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    logger.info(f"Timp de execuție: {h:02d}:{m:02d}:{s:02d}")


if __name__ == "__main__":
    main()