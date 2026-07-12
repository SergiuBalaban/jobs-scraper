#!/usr/bin/env python3
"""
sync_jobs_from_AI.py - Sincronizează câmpurile completate de AI din
json/jobs_analised.json înapoi în json/jobs.json.

Un AI analizează job-urile în batch-uri (pe baza `job_description`) și
completează `german`, `match`, `stack`, `cover_letter` într-un fișier
separat (jobs_analised.json). Acest script ia acele valori și le scrie
înapoi în jobs.json (lista completă cu toate job-urile), potrivind
job-urile după `key`. Restul câmpurilor din jobs.json rămân neatinse.

Usage:
    python tasks/sync_jobs_from_AI.py [--jobs json/jobs.json] [--analised json/jobs_analised.json]
"""

import argparse
import json
from pathlib import Path

SYNCED_FIELDS = ["german", "match", "stack", "cover_letter"]


def load_json_list(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
    return None


def save_json_list(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sync_jobs(jobs_path, analised_path):
    """
    Pentru fiecare job din analised_path, găsește job-ul corespunzător (după
    `key`) în jobs_path și suprascrie doar SYNCED_FIELDS. Rescrie integral
    jobs_path la final. Întoarce (nr. job-uri sincronizate, key-uri negăsite).
    """
    jobs = load_json_list(jobs_path)
    analised_jobs = load_json_list(analised_path)

    jobs_by_key = {job["key"]: job for job in jobs}

    updated = 0
    missing = []
    for analised_job in analised_jobs:
        key = analised_job["key"]
        job = jobs_by_key.get(key)
        if job is None:
            missing.append(key)
            continue
        for field in SYNCED_FIELDS:
            job[field] = analised_job.get(field, job.get(field))
        updated += 1

    save_json_list(jobs_path, jobs)
    return updated, missing


def main():
    parser = argparse.ArgumentParser(
        description="Sincronizează german/match/stack/cover_letter din jobs_analised.json în jobs.json"
    )
    parser.add_argument("--jobs", default="../json/jobs.json", help="Fișier JSON țintă (default: json/jobs.json)")
    parser.add_argument(
        "--analised", default="../json/jobs_analised.json",
        help="Fișier JSON cu rezultatele AI (default: json/jobs_analised.json)",
    )
    args = parser.parse_args()

    updated, missing = sync_jobs(Path(args.jobs), Path(args.analised))
    print(f"Sincronizate {updated} job-uri în {args.jobs}.")
    if missing:
        print(f"Nu am găsit {len(missing)} key-uri din {args.analised} în {args.jobs}:")
        for key in missing:
            print(f"  - {key}")


if __name__ == "__main__":
    main()
