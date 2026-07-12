#!/usr/bin/env python3
"""
jobs_parser.py - Recalculează câmpul `engineer` din jobs.json.

Ține logica de detectare separat de jobs_scraper.py, ca să poți edita
ENGINEER_STACK_KEYWORDS / EXCLUDE_STACK_KEYWORDS și să re-aplici regulile
peste job-urile deja salvate, fără să mai fie nevoie de un nou fetch de la
jobs.ch (descrierea HTML e deja stocată în `job_description`).

Usage:
    python jobs_parser.py [--input jobs.json]
"""

import argparse
import json
import re
from pathlib import Path

# Fișier cu job-urile filtrate (engineer = True), gata de analizat de un AI.
# Rescris integral de fiecare dată când rulează jobs_parser.py sau jobs_scraper.py.
PARSED_OUTPUT_FILE = "jobs_parsed.json"

# Verificate PRIMA dată: dacă descrierea conține unul din aceste cuvinte,
# jobul e exclus direct (engineer = False), indiferent ce mai conține.
EXCLUDE_STACK_KEYWORDS = [
    "java",
    "golang",
    "c#",
    "dotnet", "asp.net", ".net",
    "ruby", "ruby on rails",
    'informatiker',
    'qualitätssicherung',
]

# Verificate doar dacă niciun cuvânt din EXCLUDE_STACK_KEYWORDS nu a fost găsit.
ENGINEER_STACK_KEYWORDS = [
    # --- Core / forte (9+ ani) ---
    "php", "laravel", "symfony",

    # --- Stack adiacent (2-3 ani) ---
    "javascript", "typescript", "node.js", "node",
    "python",
    "vue", "vue.js", "react", "react.js", "angular",

    # --- Semnale backend/full-stack generale ---
    "docker", "kubernetes", "microservices",
    "rest api", "mysql", "postgresql", "graphql",

    # --- Titluri de rol EN (full-stack / solution architecture) ---
    "full-stack", "fullstack", "full stack",
    "backend", "back-end", "back end",
    "software engineer", "software developer",
    "solution architect", "solutions architect", "software architect",

    # --- Titluri de rol DE (piață elvețiană) ---
    "softwareentwickler", "entwickler", "backend-entwickler",
    "full-stack-entwickler", "softwarearchitekt", "systemarchitekt",
    "informatiker",

    # --- Carve-out QA Tester / Python Developer (schimbare de carieră) ---
    "qa engineer", "qa tester", "test automation", "test engineer",
    "software tester", "softwaretester", "qualitätssicherung",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _contains_any(text, keywords):
    """
    Caută fiecare cuvânt-cheie ca „unitate" separată, delimitată de caractere
    non-alfanumerice (sau start/sfârșit de text) în ambele capete.
    Nu folosim \\b: pentru cuvinte-cheie care încep/se termină cu un caracter
    non-word (ex: "c#", ".net"), \\b nu creează niciodată o graniță acolo,
    deci regexul nu s-ar potrivi niciodată.
    """
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text)
        for kw in keywords
    )


def is_engineer_role(description_html):
    """
    True doar dacă descrierea (HTML) conține un cuvânt din
    ENGINEER_STACK_KEYWORDS și NU conține niciun cuvânt din
    EXCLUDE_STACK_KEYWORDS (verificat primul).
    """
    text = _HTML_TAG_RE.sub(" ", description_html or "").lower()
    if _contains_any(text, EXCLUDE_STACK_KEYWORDS):
        return False
    return _contains_any(text, ENGINEER_STACK_KEYWORDS)


def write_parsed_jobs(jobs, path=PARSED_OUTPUT_FILE):
    """
    Rescrie integral PARSED_OUTPUT_FILE cu doar job-urile marcate engineer=True,
    gata de analizat de un AI. Apelat atât din jobs_parser.py, cât și din
    jobs_scraper.py, la finalul fiecărei rulări.
    """
    engineer_jobs = [job for job in jobs if job.get("engineer") is True]
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(engineer_jobs, f, ensure_ascii=False, indent=2)
    return len(engineer_jobs)


def parse_jobs_file(path):
    """Reaplică is_engineer_role peste toate job-urile din fișierul JSON dat, în loc."""
    with path.open("r", encoding="utf-8") as f:
        jobs = json.load(f)

    changed = 0
    for job in jobs:
        new_value = is_engineer_role(job.get("job_description", ""))
        if job.get("engineer") != new_value:
            changed += 1
        job["engineer"] = new_value

    with path.open("w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    parsed_count = write_parsed_jobs(jobs)

    return len(jobs), changed, parsed_count


def main():
    parser = argparse.ArgumentParser(description="Recalculează câmpul 'engineer' din jobs.json")
    parser.add_argument("--input", default="jobs.json", help="Fișier JSON de recalculat (default: jobs.json)")
    args = parser.parse_args()

    total, changed, parsed_count = parse_jobs_file(Path(args.input))
    print(f"Procesate {total} job-uri din {args.input}. Valori 'engineer' modificate: {changed}.")
    print(f"{PARSED_OUTPUT_FILE} rescris cu {parsed_count} job-uri (engineer=True).")


if __name__ == "__main__":
    main()
