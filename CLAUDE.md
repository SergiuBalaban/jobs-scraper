# Context: jobs.ch scraper

## Scop
Script Python (`jobs_scraper.py`) care extrage job-uri de pe jobs.ch dintr-un
URL de căutare cu filtre deja aplicate, și le salvează cumulativ în `jobs.json`,
fără duplicate (deduplicare după `name` + `role`).

## De ce nu se folosește un browser (Selenium/Playwright)
Site-ul e un SPA (React) cu server-side rendering. Am descoperit că:

1. **Lista de job-uri** pentru pagina curentă e deja embedată ca JSON în HTML,
   într-un `<script>` tag inline, sub variabila `window.__INIT__`.
   Path relevant: `__INIT__.vacancy.results.main.results` (array de job-uri
   pentru pagina curentă) și `__INIT__.vacancy.results.main.meta`
   (`numPages`, `totalHits`, `searchHash`).

2. **Detaliul complet al unui job** (inclusiv descrierea) NU necesită click
   în UI / interceptare de request-uri XHR vizibile — există un endpoint
   public simplu:
   `GET https://www.jobs.ch/api/v1/public/search/job/{job_id}`
   care întoarce JSON direct, accesibil și cu `requests` simplu (fără sesiune
   de browser), confirmat prin `fetch()` direct din consolă.

3. Câmpul cu descrierea job-ului în răspunsul acelui endpoint este
   **`template_text`** (conține HTML). Am verificat și alte câmpuri similare
   ca nume:
   - `template` — conține un template mai brut/necompletat, NU e descrierea finală.
   - `template_profession` — doar titlul jobului duplicat, NU descriere.
   - `template_contact_address` — adresă de contact, poate fi `null`.

4. **Pagination**: se face prin query param `&page=N` (1-indexat) adăugat
   la URL-ul original de căutare. `numPages` se citește din meta-ul primei
   pagini fetch-uite.

5. **URL companie**: se construiește din `company_slug` (din răspunsul de
   detaliu), care deja conține ID-ul numeric + slug: ex.
   `21174-dormakaba-schweiz-ag`. Formula:
   `https://www.jobs.ch/en/companies/{company_slug}/`

## Parsarea `__INIT__`
Tag-ul `<script>` fără `src` conține MAI MULTE variabile în același bloc:
`__GLOBAL__`, `__INIT__`, `__TRANSLATIONS__`, `__REACT_QUERY_STATE__`.
Nu există un delimitator text stabil între ele (regex-urile pe nume de
variabilă următoare au eșuat în explorare). Soluția robustă, folosită în
script: găsim indexul lui `"__INIT__"`, apoi prima acoladă `{` de după el,
și folosim `json.JSONDecoder().raw_decode(html, brace_idx)` — asta parsează
DOAR obiectul JSON valid, ignorând tot ce urmează în script.

## Structura unui job în `jobs.json`
```json
{
  "key": "<sha256 hex, derivat din name+role lowercased>",
  "role": "Software Projektleiter 80% - 100% w/m/d",
  "name": "dormakaba Schweiz AG",
  "url": "https://www.jobs.ch/en/companies/21174-dormakaba-schweiz-ag/",
  "city": "Rümlang",
  "description": "<p>...HTML brut...</p>"
}
```
Cheia de unicitate (`key`) e SHA256 din `name.lower()+role.lower()`. Job-urile
existente în fișier NU sunt re-fetch-uite la detaliu (optimizare + politeness),
sunt sărite direct dacă `key`-ul lor există deja.

## Rate limiting / anti-bot
Pagina folosește **AWS WAF Captcha** (`AWS_CAPTCHA_REGIONAL` găsit în config-ul
global al paginii `__GLOBAL__`). Scriptul introduce delay aleator (implicit
1-3s, configurabil din CLI) între FIECARE cerere HTTP (atât pentru paginile
de listă, cât și pentru detaliile de job). Dacă apar blocaje/captcha în
viitor, prima soluție de încercat e mărirea delay-ului, nu eliminarea lui.

## Endpoint-uri de EVITAT
`https://www.jobs.ch/api/v1/public/job/{id}/hit` și
`https://www.jobs.ch/api/v1/public/job/impression` sunt beacon-uri de
tracking (incrementează contorul de vizualizări al anunțului). NU trebuie
apelate de scraper — ar genera trafic fals în statisticile jobs.ch.

## Idei pentru extindere viitoare
- Curățare HTML → text simplu pentru `description` (ar necesita `beautifulsoup4`,
  momentan neinstalat — utilizatorul a fost de acord să-l adăugăm dacă e nevoie
  și pentru alte câmpuri).
- Suport pentru mai multe URL-uri de căutare într-o singură rulare
  (listă de URL-uri, tot spre același `jobs.json`).
- Retry/backoff automat pe erori HTTP 429/503 (posibil semn de captcha).
- Logging structurat în loc de `print`.