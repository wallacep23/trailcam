# Trail Camera Analyzer: Design Plan v1

Oct 11, 2026 · @Patrick

## 1. Overview

Trail Camera Analyzer (working name; repo `trailcam`) is a local-first desktop/web app. It ingests thousands of trail-camera videos and photos, automatically detects, counts, classifies and tracks deer, and turns them into statistically backed movement patterns that answer one question: **where and when should I hunt, given tomorrow's conditions?**

**The problem today.** The owner runs 3 trail cameras that move between sites on one property. They produce thousands of clips, many of them empty (wind, condensation) or blurry. Watching them all is too slow, remembered patterns are unreliable, and nothing is statistically backed. A prior tool, TrailcamParser, made manual tagging fast; about 513 clips were hand-labeled with it, and those are the seed ground truth.

**What the app does:**

1. Ingests folders of media, each tagged by the user with a camera site and facing direction (a *deployment*).
2. Resolves accurate timestamps, removes empty clips, and runs a vision pipeline: detect, track, count, classify (buck, doe, fawn, other species), direction of travel, and individual buck re-identification.
3. Joins every sighting with its conditions: weather and wind, sun position relative to dawn and dusk, moon phase, season and rut phase.
4. Shows the results as a map with per-camera movement vectors and cross-camera links, a condition-filtered historical replay, an analytics viewer, highlighted clips of interest (big and returning bucks), and a ranked hunt forecast.
5. Keeps a human in the loop only for uncertain cases: rapid-fire review whose corrections immediately improve the system.

**Primary goal:** never have to watch every clip again.

**Success criteria for v1:**

- At least 90% of clips are handled automatically (accepted with no human touch) at 95% or better precision on the labeled golden set.
- Empty clips are filtered with 98% or better recall of animal clips. An animal clip must never be silently dropped.
- Every analytics number is normalized by camera effort, with sample size and uncertainty shown.
- A new user gets useful output with **zero training**, using only shipped model weights.
- A full season (\~5,000 clips) processes overnight on one consumer GPU (RTX 3070, 8 GB).

## 2. Scope

v1 serves one hunter on one property, running everything locally on a Windows PC with an NVIDIA GPU. The design must not block a later multi-user, commercial product.

**Users**

- *Owner/hunter (v1):* drops in SD-card folders, reviews uncertain clips, reads patterns and forecasts.
- *Future customers:* other hunters and land managers with any camera brand, sometimes with no GPU, and several properties.

**In scope for v1**

- Properties, camera sites, deployments; folder ingest with a location picker and heading entry.
- Timestamp resolution, dedupe, empty-clip filtering, quality scoring.
- Detection, tracking, counting, buck/doe/fawn/other classification, direction of travel.
- Import of TrailcamParser legacy labels as ground truth.
- Review queue with hotkeys; corrections feed the learning loop.
- Conditions enrichment (weather history, sun, moon, season).
- Analytics viewer, map with vectors, highlights.
- Individual buck re-ID (assisted, top-k suggestions) arrives in a later milestone of v1.
- Replay and forecast are the final v1 milestones.

**Non-goals for v1**

- Cellular camera APIs and cloud upload. Files come from SD cards or folders.
- Mobile app. The web UI should still be usable on a tablet.
- Multi-tenant hosting, accounts and billing.
- Age estimation of bucks, antler scoring in inches, and pose analysis.
- Training detector backbones from scratch.

**Commercialization constraints to respect now**

- Use only permissively licensed models and libraries (MIT, Apache-2.0, BSD) in the shipped path. Keep AGPL models out of the product.
- No per-user training required. Shipped weights plus on-device adaptation from corrections.
- Camera-brand agnostic: no assumptions about filenames, overlays or metadata beyond what is detected at ingest.
- All user media stays local by default; any sharing is explicit opt-in.

## 3. Glossary

The central idea: **clips are evidence, events are the unit of analysis.** Every report, map and replay is a query over events joined to conditions.

| Term | Meaning |
| --- | --- |
| Property | A piece of land with a boundary polygon and a timezone. |
| Camera | A physical device (serial or nickname). Moves between sites. |
| Site | A fixed spot on the map where a camera can hang (lat/lon, name, alias such as `E`, `FP E`, `SE`). |
| Deployment | One camera at one site with one heading, from start to end time. **One ingested folder = one deployment.** Moving a camera = new deployment. |
| Media | One immutable source file (video or photo), identified by content hash. |
| Frame sample | A decoded frame at a known offset used for inference. |
| Detection | One bounding box in one frame with class and confidence. |
| Track | A detection chain for one animal across frames of one clip. Carries entry/exit points and screen-space motion. |
| Observation | A track enriched with class (buck/doe/fawn/other species), quality, direction (world bearing), and optional individual ID. |
| Event (visit) | Observations at one deployment grouped into an independent visit (default: gaps under 30 min merge). Analytics count events, not clips. |
| Individual | A named or auto-clustered specific buck, linked to observations. |
| Conditions | Weather, sun, moon and calendar values attached to an event timestamp. |
| Effort | Camera-hours a deployment was active; the denominator for every rate. |
| Label | A fact about media/track/observation with a source (`human_legacy`, `human_review`, `model:<name>@<version>`) and a trust level. Human labels never get overwritten by models. |
| Golden set | A frozen set of human labels used only to evaluate models. |
| Direction labels | Always **world-frame** compass directions (map north), never camera-relative. |

## 4. Functional requirements

IDs are stable so code, tests and commits can reference them (for example `FR-ING-3`). Priority: **M** = must for v1, **S** = should, **C** = could.

**Property and sites (SITE)**

- `FR-SITE-1` (M) Create a property with name, timezone (default from browser), and optional boundary polygon drawn on a satellite map.
- `FR-SITE-2` (M) Create sites by clicking the map, with name and short aliases. Sites are reusable across deployments.
- `FR-SITE-3` (M) Set a deployment heading with a draggable compass cone on the map, plus a numeric degrees field.
- `FR-SITE-4` (S) Store a reference "scene fingerprint" image per site, used to auto-suggest the site for new folders.

**Ingest (ING)**

- `FR-ING-1` (M) Add a folder (recursive scan of `.mp4 .mov .avi .jpg .jpeg`, case-insensitive) as a deployment. The user confirms site, camera, heading and date range in one dialog.
- `FR-ING-2` (M) Parse folder names like `8-28-26 FP E` into a pull date (deployment end) and site alias. Pre-fill the dialog; never require a naming convention.
- `FR-ING-3` (M) Resolve each media file's capture time with source and confidence (section 9). Never trust file modified time alone.
- `FR-ING-4` (M) Identify media by content hash. Re-adding the same files (copies, re-extracted zips) creates no duplicates.
- `FR-ING-5` (M) Never modify, rename, move or delete user media. All derived data lives in the app's database and cache directory.
- `FR-ING-6` (M) Ingest is resumable and idempotent. Stopping and restarting continues where it left off.
- `FR-ING-7` (S) Watch folders: new files in a registered folder are picked up automatically.
- `FR-ING-8` (S) Detect a mid-folder camera move (scene fingerprint changes) and propose splitting the deployment.
- `FR-ING-9` (M) Import TrailcamParser `.trailcam-metadata.json` labels as ground truth (section 12).

**Vision pipeline (VIS)**

- `FR-VIS-1` (M) Classify each media file as empty or not. An animal clip must not be dropped below the recall target. Low-confidence empties go to review, not to the trash.
- `FR-VIS-2` (M) Detect animals, people and vehicles per sampled frame; track animals within a clip; count = number of animal tracks.
- `FR-VIS-3` (M) Classify each deer track: buck, doe, fawn, antlerless adult, deer-unknown. Classify non-deer by species (turkey, coyote and so on).
- `FR-VIS-4` (M) Compute direction of travel per track as entry and exit world bearings, using the deployment heading.
- `FR-VIS-5` (M) Compute a quality score per clip and track (blur, condensation/fog, darkness, occlusion, size in frame). Low quality limits what can be claimed: presence yes, sex or ID no.
- `FR-VIS-6` (S) Score a "notable buck" value per buck track (big-buck ranking).
- `FR-VIS-7` (S) Re-identify individual bucks: suggest top-3 known individuals with similarity, or "new buck".
- `FR-VIS-8` (C) OCR the burned-in overlay for temperature and other camera fields.

**Review and learning (REV)**

- `FR-REV-1` (M) A review queue sorted by expected value of a label: uncertainty × importance (bucks first).
- `FR-REV-2` (M) Keyboard-only review that keeps the TrailcamParser hotkeys: `B D F U O` counts, `1`/`2` from/to, `N S E W` directions, `Space` pause, `4` big buck, `3` favorite, arrows to navigate. Each item shows a short looping snippet with boxes, not the full clip.
- `FR-REV-3` (M) Every correction is stored as a human label and immediately updates the per-property memory (section 11), with no retrain needed.
- `FR-REV-4` (M) Auto-accept threshold per decision type, calibrated on the golden set to hit target precision.
- `FR-REV-5` (S) Bulk actions: accept all similar, mark burst as same animal, merge or split individuals.
- `FR-REV-6` (M) A visible "automation rate at precision" metric per stage.

**Conditions (CON)**

- `FR-CON-1` (M) Attach hourly historical weather to each event: temperature, wind speed and direction, gusts, pressure and 3 h pressure trend, precipitation, cloud cover, humidity. Also temperature change vs the previous day.
- `FR-CON-2` (M) Compute locally: sunrise/sunset/civil twilight, minutes relative to nearest sunrise/sunset, moon phase and illumination, moon altitude (overhead/underfoot), day length.
- `FR-CON-3` (M) Calendar features: day of year, season, and a user-editable rut-phase calendar (pre-rut, seeking, chasing, breeding, post-rut).
- `FR-CON-4` (S) Human pressure: people and vehicles detected at any camera, plus user-logged hunt sits.

**Analytics and map (ANA, MAP)**

- `FR-ANA-1` (M) Rates per 100 camera-hours, never raw counts, for any filter of class × site × conditions.
- `FR-ANA-2` (M) Charts: activity clock relative to sunrise/sunset; wind rose of events; calendar heatmap; rate by condition bins with confidence intervals and n shown; per-buck profile.
- `FR-ANA-3` (M) Model-based effects (section 13) with plain-language summaries, such as "bucks 2.1× more active at Food Plot E with NW wind (95% CI 1.4–3.2, n=41)".
- `FR-MAP-1` (M) Satellite map of the property with sites, heading cones, and an in/out bearing rose per site.
- `FR-MAP-2` (S) Cross-camera links: same individual (or same class within a plausible travel window) at two sites drawn as arrows, weighted by frequency.
- `FR-MAP-3` (S) Replay: set conditions and a time-of-day window relative to sunset; a time-of-year slider; matching historical events animate on the map.

**Highlights and forecast (HL, FC)**

- `FR-HL-1` (M) Highlights feed: big bucks, starred individuals, first-seen bucks, bucks returning after 14+ days or from last season, daylight mature-buck sightings.
- `FR-HL-2` (S) Per-individual timeline and site history.
- `FR-FC-1` (S) Hunt forecast: pull the forecast for the next 3 days, score each site for morning and evening sits, and show why (top contributing conditions).

## 5. Non-functional requirements

| ID | Requirement |
| --- | --- |
| `NFR-1` Hardware | Runs on Windows 10/11 with an NVIDIA RTX 3070 (8 GB VRAM), 16+ GB RAM. Must degrade to CPU-only (slower, same results). |
| `NFR-2` Throughput | At least 1 clip per second end to end on the 3070 for 20–30 s 1080p clips at default sampling. A 5,000-clip season finishes in under 2 h of pipeline time. |
| `NFR-3` UI latency | Review queue item ready in under 200 ms (pre-rendered snippets). Analytics queries under 1 s for 100k events. |
| `NFR-4` Data safety | Source media is read-only to the app. The database is backed up before every migration. |
| `NFR-5` Reproducibility | Every derived row records pipeline stage, model name, model version and config hash. Any stage can be re-run for one deployment without touching others. |
| `NFR-6` Swappable models | Every model sits behind an interface. Swapping MegaDetector v6 for a future version is a config change plus a re-run. |
| `NFR-7` Licensing | Only MIT, Apache-2.0 or BSD components in the shipped path. Each model's license is recorded in `models/registry.yaml` and checked in CI. |
| `NFR-8` Privacy | Offline by default. Network calls only for weather history/forecast and map tiles, both cacheable. People detections are blurred in exports. |
| `NFR-9` Maintainability | Typed Python (mypy strict on `core/`), typed TypeScript, generated API client, 80% or better test coverage on `core/`, and each pipeline stage testable in isolation with fixture clips. |
| `NFR-10` Packaging | v1: `docker compose up` (GPU) or a documented `uv` + `pnpm` dev setup on Windows. Later: a single installer (Tauri shell + Python sidecar). |
| `NFR-11` Observability | Structured JSON logs, a jobs page with per-stage progress and errors, and a per-media audit trail of which stage produced what. |

## 6. Architecture and tech stack

Architecture: a React web UI talking to a thin FastAPI service. A separate GPU worker process runs pipeline jobs from a Postgres-backed queue. Everything runs locally.

&#91;embedded content: system components · dashed = external or offline\]

The UI only talks to the API. The API never runs models; it writes jobs to Postgres, and the GPU worker picks them up, reads media read-only, and writes results back.

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | React 18 + TypeScript + Vite, TanStack Query, Zustand, Tailwind | Fast iteration, typed, large ecosystem |
| Map | MapLibre GL JS + deck.gl (ArcLayer, IconLayer, TripsLayer for replay) | Open source, GPU-rendered, animated flows |
| Charts | Observable Plot or ECharts | Polar/rose charts, heatmaps, CIs |
| API | Python 3.12, FastAPI, Pydantic v2 | Same language as ML; OpenAPI generated for free |
| API client | `openapi-typescript` + `openapi-fetch`, generated into `apps/web/src/api/` | Frontend and backend types can never drift |
| Database | PostgreSQL 16 + PostGIS + pgvector | One store for relational, geospatial and embedding search |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | Typed models, versioned schema |
| Job queue | Postgres-backed queue (`procrastinate`, or a minimal `jobs` table with `SELECT … FOR UPDATE SKIP LOCKED`) | No Redis to run; jobs are transactional with data |
| Video decode | PyAV (FFmpeg) with keyframe-aware seeking; NVDEC optional later | Decoding is the real bottleneck, not Python |
| Inference | PyTorch for dev; ONNX Runtime (CUDA EP) for shipped models; TensorRT optional | Fast, portable, swappable |
| Detection | MegaDetector v6, MIT or Apache-2.0 variant (via PytorchWildlife), exported to ONNX | Animal/person/vehicle detector built for camera traps |
| Species | Google SpeciesNet (Apache-2.0) on detection crops | \~2,000 labels including white-tailed deer, turkey, coyote |
| Tracking | ByteTrack (or BoT-SORT) via `supervision` | Simple, fast, good for few objects |
| Embeddings | Frozen foundation backbone, configurable: MegaDescriptor (re-ID), DINOv2 or BioCLIP (classification heads). Licenses verified per model | Heads train in minutes; no backbone training |
| Heads | scikit-learn / PyTorch linear or MLP heads, calibrated (temperature or isotonic) | Tiny, fast, explainable |
| Stats | statsmodels (GLM negative binomial), pyGAM or mgcv-style splines, numpy/pandas/polars | Effort-offset count models with CIs |
| Astro | `astral` (sun) + `skyfield` or `ephem` (moon) | Local, offline, accurate |
| Weather | Open-Meteo historical + forecast API, cached in DB | Free, hourly, no key for non-commercial use (check terms before commercial use) |
| Tooling | `uv` (Python), `pnpm` (JS), ruff, mypy, pytest, vitest, Playwright, pre-commit, GitHub Actions | Fast and strict |
| Packaging | Docker Compose (api, worker, db, web) for v1; Tauri desktop shell later | Easy start, path to installer |

**Why not Rust or C++ now.** The bottleneck is video decode and GPU inference, both already native code behind Python. Rust earns a place later for an edge device or desktop installer, not v1.

## 7. Repository skeleton

A single monorepo. Python packages live under `backend/src/trailcam/` with strict layering: `core` has no I/O; `pipeline` and `api` depend on `core` and `db`; nothing depends on `api`.

```
trailcam/
├─ README.md                  # setup, run, architecture summary
├─ CLAUDE.md                  # coding-agent instructions (section 18)
├─ docs/
│  ├─ DESIGN.md               # this document
│  └─ adr/                    # architecture decision records, one per decision
├─ docker-compose.yml         # db (postgis+pgvector), api, worker, web
├─ .env.example
├─ backend/
│  ├─ pyproject.toml           # uv-managed; ruff, mypy, pytest config
│  ├─ alembic/                 # migrations
│  ├─ src/trailcam/
│  │  ├─ config.py             # pydantic-settings; paths, GPU, thresholds
│  │  ├─ core/                 # PURE logic, no I/O, heavily unit-tested
│  │  │  ├─ geometry.py        # bearings, screen->world mapping, haversine
│  │  │  ├─ astro.py           # sun/moon features
│  │  │  ├─ timeresolve.py     # timestamp candidate scoring
│  │  │  ├─ folder_names.py    # "8-28-26 FP E" parser
│  │  │  ├─ events.py          # track -> observation -> event grouping
│  │  │  ├─ label_transfer.py  # clip labels -> track labels
│  │  │  ├─ stats/             # effort, rates, GLM wrappers, CIs
│  │  │  └─ types.py           # domain dataclasses / enums
│  │  ├─ db/
│  │  │  ├─ models.py          # SQLAlchemy tables (section 8)
│  │  │  ├─ session.py
│  │  │  └─ repo/              # query functions per aggregate
│  │  ├─ models/               # ML model adapters behind interfaces
│  │  │  ├─ base.py            # Detector, Tracker, Classifier, Embedder, QualityScorer protocols
│  │  │  ├─ megadetector.py
│  │  │  ├─ speciesnet.py
│  │  │  ├─ bytetrack.py
│  │  │  ├─ embedder.py        # MegaDescriptor / DINOv2 / BioCLIP
│  │  │  ├─ heads.py           # sex/age-class + notable-buck heads
│  │  │  └─ registry.py        # loads models/registry.yaml
│  │  ├─ pipeline/
│  │  │  ├─ jobs.py            # queue, job types, retries
│  │  │  ├─ runner.py          # worker entrypoint
│  │  │  └─ stages/            # one module per stage, idempotent
│  │  │     ├─ scan.py  hash.py  timestamps.py  sample.py
│  │  │     ├─ detect.py  track.py  classify.py  direction.py
│  │  │     ├─ quality.py  embed.py  reid.py  events.py
│  │  │     └─ conditions.py  snippets.py
│  │  ├─ learning/
│  │  │  ├─ memory.py          # per-property kNN memory (layer 2)
│  │  │  ├─ calibrate.py       # thresholds for target precision
│  │  │  └─ active.py          # review-queue priority
│  │  ├─ importers/
│  │  │  ├─ base.py            # LabelSource protocol
│  │  │  ├─ trailcamparser.py  # legacy .trailcam-metadata.json
│  │  │  └─ folder_species.py  # "Does/", "Turkeys/" style folders
│  │  ├─ integrations/
│  │  │  └─ weather.py         # Open-Meteo client + cache
│  │  └─ api/
│  │     ├─ main.py            # FastAPI app factory
│  │     ├─ schemas.py         # Pydantic DTOs (source of OpenAPI)
│  │     └─ routers/           # properties, sites, deployments, media, review,
│  │                           # individuals, analytics, map, jobs, models
│  └─ tests/
│     ├─ unit/                 # core/* tests, no DB or GPU
│     ├─ integration/          # DB + API with testcontainers
│     └─ fixtures/             # 10–20 tiny clips + label JSON
├─ training/                  # offline, not imported by the app
│  ├─ export_dataset.py        # labels -> crops + manifest (parquet)
│  ├─ train_heads.py           # frozen backbone -> heads -> ONNX
│  ├─ evaluate.py              # golden-set report (section 16)
│  └─ configs/*.yaml
├─ models/
│  ├─ registry.yaml            # name, version, file, sha256, license, source URL
│  └─ weights/                 # gitignored; fetched by scripts/get_models.py
├─ apps/web/
│  ├─ package.json  vite.config.ts
│  └─ src/
│     ├─ api/                  # GENERATED client; do not hand-edit
│     ├─ features/             # one folder per screen (section 14)
│     │  ├─ setup/  ingest/  review/  clips/  map/
│     │  ├─ analytics/  individuals/  highlights/  forecast/  jobs/
│     ├─ components/           # shared UI (VideoSnippet, CompassPicker, …)
│     └─ lib/                  # hotkeys, formatting, map helpers
└─ scripts/
   ├─ get_models.py            # download + verify weights
   ├─ gen_api_client.sh
   └─ dev_seed.py              # demo property from fixtures
```

## 8. Data model

Postgres is the source of truth. All timestamps are stored as `timestamptz` in UTC, with the property timezone used only for display. All ids are UUIDv7. Every derived row carries `produced_by` (stage, model name, model version, config hash).

| Table | Key fields | Notes |
| --- | --- | --- |
| `property` | id, name, tz, boundary `geography(Polygon)` |  |
| `site` | id, property\_id, name, aliases `text[]`, location `geography(Point)`, scene\_fingerprint `vector` |  |
| `camera` | id, property\_id, nickname, make, model, serial | Optional for v1 |
| `deployment` | id, site\_id, camera\_id?, heading\_deg, fov\_deg (default 55), start\_at, end\_at, source\_folder, frame\_calibration jsonb, notes | One folder = one deployment |
| `media` | id, deployment\_id, sha256 unique, path, kind (video/photo), bytes, duration\_s, fps, width, height, captured\_at, time\_source, time\_confidence, raw\_time\_candidates jsonb, seq\_no, burst\_id, status | Never mutates the file |
| `media_quality` | media\_id, blur, fog, darkness, is\_ir\_night, score |  |
| `frame_sample` | id, media\_id, t\_offset\_s, frame\_idx | Frames cached as JPEG in cache dir |
| `detection` | id, frame\_sample\_id, class (animal/person/vehicle), conf, bbox (x, y, w, h normalized), produced\_by |  |
| `track` | id, media\_id, det\_ids, first\_t, last\_t, entry\_xy, exit\_xy, screen\_motion jsonb, mean\_box\_area, quality |  |
| `observation` | id, track\_id, species, deer\_class (buck/doe/fawn/antlerless/unknown), class\_probs jsonb, entry\_bearing\_deg, exit\_bearing\_deg, notable\_score, individual\_id?, accepted (bool), produced\_by | What analytics read |
| `embedding` | id, track\_id, model, vector `vector(N)`, crop\_ref | pgvector HNSW index |
| `individual` | id, property\_id, name, starred, first\_seen, last\_seen, notes, cover\_crop\_ref | Named bucks |
| `event` | id, deployment\_id, start\_at, end\_at, n\_deer, n\_bucks, n\_does, n\_fawns, species\_set, dominant\_direction, has\_notable\_buck, individual\_ids `uuid[]` | Independent visits |
| `conditions_hourly` | property\_id, hour\_utc, temp\_c, wind\_ms, wind\_dir\_deg, gust\_ms, pressure\_hpa, precip\_mm, cloud\_pct, humidity, source | Cached weather |
| `event_conditions` | event\_id, all hourly fields + pressure\_trend\_3h, temp\_delta\_24h, mins\_from\_sunrise, mins\_from\_sunset, sun\_alt, moon\_phase, moon\_illum, moon\_alt, day\_of\_year, rut\_phase | Denormalized for fast queries |
| `effort` | deployment\_id, hour\_utc, active (bool) | From first/last media + gaps; the denominator |
| `label` | id, target\_type (media/track/observation/individual), target\_id, field, value jsonb, source (`human_legacy`/`human_review`/`import:<name>`), trust (`ground_truth`/`human`/`model`), author, created\_at, supersedes\_id? | Append-only; latest human wins |
| `golden_split` | target\_id, split (train/val/test), split\_key (deployment) | Frozen evaluation splits |
| `model_version` | name, version, sha256, license, metrics jsonb, created\_at | Mirrors `models/registry.yaml` |
| `job` | id, type, payload, status, attempts, error, started\_at, finished\_at, progress | Queue |
| `hunt_log` | id, site\_id, start\_at, end\_at, notes | Human pressure + forecast validation |

**Resolution rule for any field:** latest `human_review` > `human_legacy`/import ground truth > model output. Model writes never overwrite human labels; they create new `produced_by` rows and the view picks by precedence.

## 9. Ingest pipeline

Ingest turns a folder into one deployment of hashed, correctly timed media. It never touches the files themselves.

**9.1 Add-folder flow**

1. The user picks a folder. In the browser UI that is a server-side path picker, because the API reads disk directly; the File System Access API is not used.
2. `folder_names.parse()` proposes a pull date and site alias. Examples from the real data: `8-28-26 FP E` → 2026-08-28, alias `FP E`. `10-3 FP W` → Oct 3 with the year inferred from file dates. `East Side/6-11-26` → parent folder names the site. `9-4-26 SE corner` → alias `SE corner`.
3. The site is suggested by alias match, then by scene-fingerprint similarity (median-frame embedding vs each site's reference) with a confidence. The user confirms or picks on the map.
4. Heading defaults to the site's last heading. The user can adjust it with the compass cone.
5. Deployment start defaults to the previous pull at that site (or the first media time). End defaults to the pull date (or the last media time).
6. The user confirms and the `scan` job is queued.

**9.2 Stages (each an idempotent job keyed by `(media_id, stage, model_version)`)**

1. `scan`: list files, skip non-media and dot-files (including `.trailcam-metadata.json`, which goes to the importer), and create `media` rows with status `discovered`.
2. `hash`: sha256 of the file. Duplicates across deployments link to the existing media; the user is warned if they disagree on deployment.
3. `probe`: ffprobe duration, fps, size, container `creation_time`, and the camera sequence number from the filename (`DSCF0042` → 42, `IMG_0042`, `PICT0042`, and so on).
4. `timestamps`: resolve capture time (9.3).
5. `sample`: decode frames at 2 fps (configurable; photos are 1 frame; bursts are grouped) and cache JPEGs at 1280 px on the long side.
6. Hand off to the vision stages (section 10).

**9.3 Timestamp resolution**

Each media gets a list of candidates `{source, value, confidence}`. A deterministic scorer in `core/timeresolve.py` picks one.

| Priority | Source | Notes |
| --- | --- | --- |
| 1 | Burned-in overlay OCR | Most cameras print date/time. OCR a configurable region (default bottom 12%) on 3 frames; accept only if 2 of 3 agree. The format is learned per deployment from the first successes. Tesseract or PaddleOCR. |
| 2 | Container metadata `creation_time` | Often local time mislabeled as UTC; interpret using the property timezone, then cross-check with OCR. |
| 3 | Filename `YYYYMMDD_HHMMSS(_n)` | The legacy app renamed many files into this form, so it is reliable for those folders. |
| 4 | EXIF `DateTimeOriginal` (photos) |  |
| 5 | File modified time | Weakest. Copying resets it: the East Side copies all show Aug 25, 2026. Use only if consistent with sequence order and the deployment range. |

**Consistency checks (flag, don't silently fix)**

- Times must increase as the sequence number increases.
- All times must fall inside the deployment window.
- A year of 2000 or 1970 means the camera clock reset.
- A constant offset vs OCR suggests a timezone or DST error.
- Duplicate seconds get `+n` s ordering by sequence number, matching the legacy behaviour.

**Per-deployment clock offset.** The user can enter a correction, or the system proposes one from the setup clip. When the first clip of a deployment contains a person (the hunter hanging the camera), it is anchored to the user-entered hang time.

**9.4 Effort**

A deployment is active from its first to its last media time, minus gaps longer than 72 h with no triggers when a battery or SD failure is suspected (configurable, flagged for the user). Effort is stored hourly in `effort`. Every rate in analytics divides by it.

**9.5 Other sources and edge cases**

- Zip files are ignored. The user extracts them; this is documented.
- `.DS_Store` and `__MACOSX` are ignored.
- Nested media folders (`Corner/100MEDIA/older`) belong to the same deployment unless the user splits them.
- Photos and videos in one folder are both supported. Photo bursts (3 shots within 10 s) are grouped by `burst_id` and treated like one clip.

## 10. Vision pipeline

Cheap stages run first, and every stage may abstain. An abstention routes to review instead of guessing.

1. **Detect** (`stages/detect.py`). MegaDetector v6 (permissive-license variant, ONNX) on every sampled frame.
   - Classes: animal, person, vehicle.
   - Keep boxes at conf ≥ 0.15 for tracking; clip-level animal presence at max conf ≥ 0.35. Calibrate both on the golden set.
   - Batch frames across clips to fill the GPU, with a batch size that fits 8 GB.
2. **Empty filter.** A clip with no animal box at or above threshold in any frame is `empty`. If the max conf falls in a grey band (0.1–0.35), status is `maybe_empty` and it goes to review at low priority. Nothing is deleted.
3. **Track** (`stages/track.py`). ByteTrack over the per-frame animal boxes.
   - Merge fragments when the gap is ≤ 1.5 s and IoU or embedding similarity is high.
   - Count = number of animal tracks longer than 0.5 s.
   - Store entry and exit points, and the box-area trend (growing = approaching camera).
4. **Quality** (`stages/quality.py`). Per frame:
   - Laplacian variance (blur) and contrast/dark-channel (fog and condensation).
   - Mean luminance plus IR detection (grayscale night).
   - Box size and truncation at the frame edge.
   - Per-track quality = median over its frames. Thresholds decide what may be claimed: presence always; sex class only if quality ≥ q1; individual ID only if quality ≥ q2.
5. **Species** (`stages/classify.py`). SpeciesNet on the top-3 crops per track (largest, sharpest), with geofencing to the property's country and state. Output: white-tailed deer vs other species.
6. **Deer class** (same stage). Layer 1 head on frozen-backbone embeddings of up to 8 crops per track, mean-pooled.
   - Classes: buck, doe, fawn, antlerless-adult, unknown.
   - Seasonal prior from the calendar: antlerless-adult is more likely from about January to April (shed to early growth), and fawn spots run roughly June to September.
   - Combined with Layer 2 memory (section 11). Calibrated probabilities are stored.
7. **Direction** (`stages/direction.py`). Turn screen motion into world bearings (math in `core/geometry.py`):
   - The horizontal pixel position maps to an angle off the camera axis: `angle = (x − 0.5) × fov`.
   - The box-area trend gives a toward/away component.
   - Entry bearing = heading + entry angle, adjusted by the toward/away sign. Exit bearing likewise.
   - Report both and an 8-point compass label.
   - **Calibration from labels:** for deployments with human direction labels, fit per-deployment `heading` and `fov` by minimizing angular error. This validates the user-entered heading and flags bad ones.
   - Optional manual frame calibration: the user marks frame edges with named destinations ("left exit = toward bedding").
8. **Embed** (`stages/embed.py`). Re-ID embedding (MegaDescriptor-L or similar) for each buck track with quality ≥ q2, from the 3 best crops, stored in pgvector.
9. **Re-ID** (`stages/reid.py`). Nearest neighbours against the property's known individuals, using each individual's **recent** sightings (last 30 days weighted higher, which handles antler growth).
   - The score adds priors: same site or recent nearby sighting (spatio-temporal), season compatibility.
   - Output: top-3 candidates + "new".
   - Auto-assign only if similarity is above the calibrated threshold **and** the margin over the second candidate is above the margin threshold. Otherwise suggest.
   - Unassigned bucks are clustered with HDBSCAN into proposed individuals for the user to name.
10. **Notable buck** (`heads.py`). A ranking score from a Layer 1 head trained on legacy `goodBuck` flags (34 positives; weak, so used for ranking only) plus box-normalized antler-region features. Users' thumbs-up and thumbs-down feed Layer 2.
11. **Events** (`stages/events.py`). Group accepted observations per deployment into visits (gap < 30 min, configurable), then attach conditions (section 13).
12. **Snippets** (`stages/snippets.py`). Pre-render a 2–4 s looping MP4/WebM per track with boxes drawn, for review and highlights.

**Performance notes**

- Decode with PyAV in a separate process pool; inference in one GPU process.
- Pipeline is producer/consumer with bounded queues. Skip decoding frames not needed (seek to keyframes at 2 fps).
- Night IR clips are usually smaller and lower quality, so lean on tracking.

## 11. Learning system

The product ships with no per-user training. Accuracy comes from three stacked layers, and human corrections improve the third layer instantly.

| Layer | What | Trained by | Updates |
| --- | --- | --- | --- |
| 0 Pretrained | MegaDetector, SpeciesNet, ByteTrack, embedding backbones, direction geometry | Upstream authors | When we bump versions |
| 1 Shipped heads | Deer-class head; notable-buck head; quality thresholds; calibration | The owner, once, before release (`training/`) | Each app release |
| 2 Property memory | Labeled embeddings from this property's corrections; named individuals; per-deployment heading/fov fits | The user's normal review | Instantly, per correction |

**11.1 Clip → track label transfer (`core/label_transfer.py`)**

Legacy and review labels are often clip-level counts. They are converted to track-level labels like this:

- If the clip has exactly one non-zero class and the number of deer tracks equals the human count, every track gets that class with `trust=ground_truth`. This is unambiguous for **88% of the legacy positives (450 of 513)**, including all 99 buck-only clips.
- If counts mismatch (tracker found 2, human said 1), keep the human count on the clip and mark the tracks `needs_resolution`. These mismatches are also detector/tracker evaluation data.
- Mixed-class clips (for example 1 buck + 2 does) go to a one-tap "which one is the buck?" queue showing each track's best crop.
- A clip-level `goodBuck` is attached to the buck track when exactly one buck track exists; otherwise it goes to the resolution queue.

**11.2 Layer 1 training (offline, minutes on an RTX 3070)**

1. `export_dataset.py`: for each labeled track, save up to 8 crops plus metadata (deployment, site, date, IR/day, quality) to a parquet manifest.
2. Compute frozen embeddings once and cache them.
3. `train_heads.py`: logistic regression or a 1-hidden-layer MLP per head.
   - Class-balanced. Splits are **by deployment** (never random): train on some deployments, test on held-out ones, and also report East Edge ↔ West Hub cross-site.
4. Calibrate (temperature scaling) on the validation split. Export ONNX plus `head_card.json` (classes, metrics, data counts, backbone id).
5. Register in `models/registry.yaml`.

Augment with public camera-trap deer data where licenses allow (search LILA BC datasets for white-tailed deer with sex labels). Verify each dataset's license before using it for a shipped model.

**11.3 Layer 2 property memory (`learning/memory.py`)**

- Each human-labeled track embedding is stored with its label in pgvector, scoped to the property.
- At inference: `p_final = normalize(w_head · p_head + w_mem · p_knn)`, where `p_knn` is a distance-weighted vote of the k=15 nearest labeled neighbours.
  - `w_mem` grows with the number and closeness of neighbours, so a brand-new property relies on the shipped head.
- A correction inserts or updates one memory row, and its effect is visible on the next item.
- **Re-predict:** after a correction, re-score unaccepted observations within that embedding neighbourhood (a cheap ANN query), so similar mistakes get fixed in bulk.
- Optional background refit: once a property has 200+ new labels, refit a property-specific linear head in seconds and A/B it on that property's held-out labels. Keep it only if it improves.

**11.4 Review queue priority (`learning/active.py`)**

priority = uncertainty (1 − max prob, or re-ID margin) × importance (buck 3, unknown deer 2, doe/fawn 1, other species 0.5) × novelty (distance to nearest labeled example) × recency boost.

High-confidence items skip the queue. A daily random 2% audit sample is always included to measure real precision.

**11.5 Feedback upstream (later, opt-in)**

Users may share corrected crops (never full media or locations) to improve the next Layer 1 release. The design keeps crops, labels and backbone ids portable to make this possible.

## 12. Legacy TrailcamParser import

The owner's earlier tool (`C:\Users\pwall\Desktop\Code\TrailcamParser`, a browser app using the File System Access API) wrote one JSON file per folder. These labels are human-reviewed ground truth and seed the golden set. The owner will clean up remaining inconsistencies before import, so the importer validates and reports but does not need to auto-fix.

**12.1 File format: `<folder>/.trailcam-metadata.json`**

```json
{
  "__folder": { "compassRotation": 222.52 },
  "20260322_073137.mp4": {
    "location": "East Edge",
    "bucks": 1, "does": 0, "fawns": 0, "unknowns": 0, "otherCreatures": 0,
    "comingFrom": "W", "goingTo": "E",
    "comingFromRotation": 0, "goingToRotation": 0,
    "favorite": false, "goodBuck": true
  }
}
```

**12.2 Mapping rules**

| Legacy field | New system |
| --- | --- |
| folder | `deployment` (`source_folder`); the date range comes from resolved media times |
| `location` | `site` by name (`East Edge`, `West Hub`; `Default`/empty = unknown, ask the user) |
| `__folder.compassRotation` | Hint for `deployment.heading_deg`. It is a UI dial angle; the user re-enters or confirms the heading on the map. Store the raw value in `deployment.notes` |
| `bucks/does/fawns/unknowns/otherCreatures` | Clip-level count labels (`source=human_legacy`, `trust=ground_truth`) → label transfer (11.1). `unknowns` = deer of unknown class; `otherCreatures` = non-deer, species unknown (SpeciesNet fills it in) |
| `comingFrom` / `goingTo` | **World-frame** cardinal directions (map north; confirmed by the owner). N=0°, E=90°, S=180°, W=270°. Entry bearing = comingFrom, exit bearing = goingTo. Both are evaluation targets for the direction stage |
| `*Rotation` fields | Ignored (always 0) |
| `goodBuck` | `notable=true` on the buck track (or clip if unresolved) |
| `favorite` | `starred=true` on the media |
| filename key | Matched to media by filename within the folder; a filename `YYYYMMDD_HHMMSS(_n)` is also a timestamp candidate |

**12.3 Semantics that must be respected**

- **All-zero entries are "not tagged", not "empty".** An entry with every count 0 means the user viewed the clip but did not tag it. Import it as no label, never as a negative.
- A clip is only a ground-truth positive if any count > 0.
- "Fully tagged" in the legacy app = video + location + comingFrom + goingTo + any count > 0.
- The legacy app deleted unwanted clips (wind/empty) from tagged folders. Absence of a file is therefore not informative.
- Folders named for a species (`Does/`, `Predators/`, `Turkeys/`) are imported by `importers/folder_species.py` as weak species-presence labels (`trust=human`, clip-level), after user confirmation.

**12.4 What the existing data contains (audit, 2026-10-11)**

| Folder | Site | compassRotation | Entries | With animals | Bucks | goodBuck | Dir-tagged |
| --- | --- | --- | --- | --- | --- | --- | --- |
| East Side/4-28-26-2 | East Edge | 222.5 | 89 | 89 | 19 | 0 | 88 |
| East Side/6-11-26 | East Edge | 218.3 | 178 | 149 | 51 | 3 | 147 |
| East Side/7-12-26 | East Edge | 222.4 | 87 | 87 | 20 | 7 | 87 |
| East Side/8-8-26 | East Edge | 203.0 | 66 | 64 | 17 | 5 | 66 |
| West Side/4-28-26 | West Hub | 241.8 | 168 | 7 | 1 | 0 | 7 |
| West Side/7-12-26-2 | West Hub | 240.0 | 46 | 40 | 6 | 5 | 40 |
| West Side/7-8-26-2 | West Hub | 242.2 | 233 | 77 | 23 | 14 | 83 |

**Totals:** 513 positive clips, 119 clips with bucks (137 bucks), 211 does, 126 fawns, 169 unknown deer, 87 other creatures, 34 goodBuck, 518 direction-tagged.

- 450 of 513 positives (88%) are single-class; 381 (74%) are single-animal.
- Dates span March–August 2026.
- Folders `10-1-26 SE`, `10-3-26 FP E` and `9-12-26 SE` have metadata files with no tags (all zeros), so they are unlabeled.
- Untagged media folders: `Spring 2026 Trail cameras/` (Barn, Corner, Far), `8-19-26`, `8-22-26 East/west`, `8-28-26 E/SE/W/we`, `9-4-26 *`, `9-12-26 FP E/W`, `10-3 FP W`, `w`.
- Known hygiene issues the owner will fix: 3 goodBuck clips with bucks=0; 7 labeled clips with camera filenames (`DSCF####.MP4` in West Side/4-28-26), whose time comes from mtime, which is reliable there because it was not copied.
- Sanity pattern already visible: buck clips peak at 05–06 h and 20–21 h.

Media root on the owner's PC: `C:\Users\pwall\Desktop\TrailCamera\Judy's\` ("Judy's" is the property). There is about 60 GB+ of media in total, including two zips (12 GB and 2 GB) that duplicate extracted folders.

## 13. Conditions and analytics methodology

Patterns are only trusted when they are effort-normalized, built from independent events, and shown with sample size and uncertainty.

**13.1 Conditions enrichment (`stages/conditions.py`)**

- **Weather:** Open-Meteo archive API for the property centroid, hourly, fetched per deployment window and cached in `conditions_hourly`.
  - Fields: temperature, wind speed/direction/gusts, surface pressure, precipitation, cloud cover, humidity.
  - Derived: 3 h pressure trend, 24 h temperature delta, front passage flag (pressure drop > 3 hPa in 6 h).
  - Forecast for the forecast page comes from the same provider.
- **Wind relative to the site:** for each event, the wind direction relative to the site and to the deer's travel bearing (headwind, tailwind, crosswind). Deer movement vs wind is a key hunter question.
- **Sun:** sunrise, sunset, civil twilight (`astral`), minutes from nearest sunrise and sunset (signed), sun altitude, daylight flag (legal shooting light = 30 min before sunrise to 30 min after sunset; configurable by state).
- **Moon:** phase angle, illumination %, altitude at event time, and moon-overhead/underfoot timing (`skyfield`).
- **Calendar:** day of year, week, season, rut phase from a user-editable calendar. Default for southern Michigan (property near South Lyon, centroid 42.493, -83.665, timezone America/Detroit): seeking Oct 25–Nov 5, chasing Nov 5–12, breeding Nov 12–25 (approximate; editable per season).
- **Human pressure:** people/vehicle detections and `hunt_log` sits in the previous 24/72 h per site.

**13.2 Units of analysis**

- Analytics count **events** (independent visits), not clips.
- Rates = events / active camera-hours × 100, from `effort`.
- Filters: class (buck / any deer / doe / named individual), site, date range, and any condition range.

**13.3 Models (`core/stats/`)**

- Descriptive: rate by condition bin with Poisson or bootstrap 95% CI. Bins with n < 10 events are greyed out.
- Explanatory: negative-binomial GLM per hour-of-day-relative-to-sun × site, with `log(effort_hours)` offset.
  - Covariates: cyclic splines for mins-from-sunset and day-of-year; wind speed; wind direction (sin/cos); temperature delta; pressure trend; moon illumination; rut phase; human pressure.
  - Report incidence-rate ratios with CIs. Translate to plain language only when the CI excludes 1.
- Guardrails:
  - Every chart shows n and effort hours.
  - Never show a pattern drawn from a single deployment as general.
  - Multiple-comparison caution: a "lucky" condition gets a note when many bins were tested.
- Forecast score per site × sit window = predicted buck-event rate from the GLM given forecast conditions, with an interval. Sites are ranked; the top 3 drivers are shown.

**13.4 Cross-camera movement**

- Same individual seen at site A then site B within a plausible window (distance / 1.5 km/h plus slack; max 6 h) creates a movement link.
- Without individual ID, an anonymous link (same class, matching exit/entry bearings toward each other, within the window) is drawn lighter.
- Links aggregate into corridor weights per site pair × time-of-day × season.
- With no link, each site still shows its own in/out bearing rose, which is the default view.

## 14. Frontend screens

Eleven screens, each a folder under `apps/web/src/features/`. Dark theme by default (it is used at night and pre-dawn); keyboard-first everywhere.

| Screen | Purpose | Key elements |
| --- | --- | --- |
| Setup | Property, sites, cameras | Satellite map, draw boundary, click to add site, alias chips, site list |
| Ingest | Add folders, confirm deployments | Server path picker; detected folders table (parsed date, suggested site + confidence, file count, legacy labels found); confirm dialog with compass cone; job progress |
| Review | Rapid human correction | Snippet player (loops, boxes); model's guess pre-filled; hotkeys; queue counter + automation rate; undo; "why is this here" reason |
| Clips | Browse everything | Grid of thumbnails with filters (site, date, class, notable, individual, status, quality); scrub-on-hover; open in a detail drawer with tracks, labels and history |
| Map | Spatial patterns | Sites with heading cones; per-site in/out bearing roses; cross-camera arcs; filters panel shared with analytics |
| Replay | Conditions-matched history | Condition filters; time-of-day scrubber relative to sunset (−180 to +180 min); time-of-year slider (week window); play animates matching events as pulses and arrows |
| Analytics | Statistics | Activity clock (radial, minutes from sunrise/sunset); wind rose; calendar heatmap; rate-by-condition with CIs; model effects table in plain language; every chart shows n and effort |
| Individuals | Named bucks | Cards with best crop, first/last seen, sites, daylight %; timeline; merge/split; star; candidate clusters to name |
| Highlights | Of-interest feed | Big bucks, starred, first-seen, returning, daylight mature; each opens the snippet |
| Forecast | Where to sit | Next 3 days × AM/PM, site ranking with predicted rate + interval and top drivers; wind arrow vs site |
| Jobs / Models | System health | Job list with progress/errors; model registry with versions, licenses, golden-set metrics |

**Review hotkeys** (carried over from TrailcamParser so muscle memory transfers)

| Key | Action |
| --- | --- |
| `B` `D` `F` `U` `O` | Set or increment buck / doe / fawn / unknown deer / other on the focused track |
| `↑` `↓` | Adjust last count |
| `1` / `2` | Select coming-from / going-to |
| `N` `S` `E` `W` (+ `Shift` for NE/NW/SE/SW) | Set direction |
| `Enter` | Accept as shown and go to next |
| `Tab` | Next track within clip |
| `4` | Toggle big/notable buck |
| `3` | Toggle favorite/star |
| `I` then `1`–`3` | Pick re-ID candidate; `I` then `0` = new buck |
| `X` | Mark empty/false trigger |
| `Space` | Pause; `←`/`→` previous/next; `Ctrl+Z` undo |

**Shared UI components:** `VideoSnippet`, `CompassPicker` (cone on map + numeric), `BearingRose`, `ConditionFilters`, `ConfidenceBadge`, `CIBar`, `SiteBadge`, `IndividualChip`.

## 15. API surface

REST under `/api/v1`, JSON, defined by Pydantic schemas. The OpenAPI spec generates the TypeScript client. Media and snippets are served with HTTP range support.

| Area | Endpoints |
| --- | --- |
| Properties & sites | `GET/POST /properties`, `GET/PATCH /properties/{id}`, `GET/POST /properties/{id}/sites`, `PATCH /sites/{id}` |
| Deployments | `POST /deployments/preview` (path → parsed name, suggested site, file counts, legacy labels found), `POST /deployments` (confirm + queue ingest), `GET /deployments?property_id`, `PATCH /deployments/{id}` (heading, window, clock offset), `POST /deployments/{id}/split` |
| Filesystem | `GET /fs/browse?path=` (server-side folder picker, restricted to configured roots) |
| Media | `GET /media?filters…` (paged), `GET /media/{id}`, `GET /media/{id}/file`, `GET /media/{id}/frames/{n}.jpg`, `GET /tracks/{id}/snippet.mp4` |
| Review | `GET /review/next?n=20`, `POST /review/{item_id}/labels` (batch of label ops), `POST /review/undo`, `GET /review/stats` |
| Labels | `GET /labels?target`, `POST /labels` (generic, append-only) |
| Individuals | `GET/POST /individuals`, `PATCH /individuals/{id}`, `POST /individuals/merge`, `POST /individuals/{id}/split`, `GET /individuals/{id}/timeline`, `GET /individuals/candidates` (clusters to name) |
| Analytics | `POST /analytics/rates` (filters + group-by → rates, n, effort, CI), `POST /analytics/activity-clock`, `POST /analytics/wind-rose`, `POST /analytics/heatmap`, `POST /analytics/effects` (GLM summary) |
| Map | `POST /map/site-roses`, `POST /map/links`, `POST /map/replay` (filters + window → time-ordered events) |
| Highlights & forecast | `GET /highlights?kind`, `GET /forecast?days=3` |
| Import | `POST /import/trailcamparser` (path) → dry-run report, then `?commit=true`; `POST /import/folder-species` |
| Jobs & models | `GET /jobs`, `POST /jobs/{id}/retry`, `POST /pipeline/rerun` (stage + scope), `GET /models`, `GET /models/{name}/metrics` |

Shared filter object (one Pydantic model reused by analytics, map, replay and clips):

```json
{
  "property_id": "…",
  "site_ids": [],
  "date_from": null, "date_to": null, "doy_window": null,
  "classes": ["buck"], "individual_ids": [],
  "mins_from_sunset": [-120, 60], "mins_from_sunrise": null,
  "wind_dir_deg": [270, 360], "wind_ms": [0, 6],
  "temp_delta_24h": null, "pressure_trend_3h": null,
  "moon_illum": null, "rut_phase": [], "daylight_only": false,
  "min_quality": 0.0, "accepted_only": true
}
```

## 16. Evaluation, testing and quality gates

The legacy labels become a frozen golden set. No model version ships unless it meets these gates on the held-out deployments.

**16.1 Golden set**

- Built by the importer from `trust=ground_truth` labels and frozen in `golden_split`.
- Split by deployment: test = `East Side/8-8-26` + `West Side/7-12-26-2`, val = `East Side/7-12-26`, train = the rest. Adjust once more data is labeled, but always keep whole deployments together.
- Cross-site check: train on East Edge only, test on West Hub, and report separately.
- Over time, the random 2% audit sample from review adds to the test pool.

**16.2 Metrics (`training/evaluate.py` → HTML + JSON report stored in `model_version.metrics`)**

| Stage | Metric | v1 gate |
| --- | --- | --- |
| Empty filter | Recall of animal clips | ≥ 98% |
| Empty filter | Share of truly empty clips removed | report only (legacy folders were pre-cleaned) |
| Count | Exact clip count match | ≥ 85% |
| Count | Mean absolute count error | ≤ 0.25 |
| Buck | Precision / recall of buck clips | ≥ 95% / ≥ 85% |
| Deer class | Macro F1 buck/doe/fawn | report; target ≥ 0.80 |
| Direction | goingTo matches within one cardinal step (±45°) | ≥ 85% |
| Direction | Exact cardinal match | report |
| Notable buck | Precision@10 of goodBuck in ranked bucks | report |
| Automation | Share of clips auto-accepted at ≥ 95% precision | ≥ 90% (headline KPI) |
| Re-ID (once labeled) | Top-1 / top-3 accuracy on named individuals | report; target top-3 ≥ 85% |
| Throughput | Clips/s on RTX 3070 | ≥ 1 |

**16.3 Tests**

- Unit (`pytest`, no GPU, no DB) for all of `core/`:
  - folder-name parser (every real folder name from section 12 as a case)
  - timestamp resolver (sequence conflicts, clock reset, DST)
  - bearing math (wraparound at 0/360)
  - label transfer (single-class, mismatch, mixed)
  - event grouping
  - effort computation
  - stats wrappers (known synthetic Poisson data recovers known rate ratios)
- Model adapters use contract tests with a fake model, plus one GPU smoke test marked `@pytest.mark.gpu`.
- Pipeline integration on 10–20 tiny fixture clips (downscaled 2–3 s clips with known labels: empty, single buck, doe + fawns, night IR, foggy, turkey), checked into `tests/fixtures/` with Git LFS. The owner supplies them from the real data.
- API: integration tests with a Postgres test container.
- Web: vitest for components and hotkeys; Playwright for the review loop and add-folder flow.
- CI: lint (ruff, eslint), type-check (mypy, tsc), unit and integration tests, license check of `models/registry.yaml` and dependencies, and OpenAPI client regeneration diff check.

## 17. Milestones

The first iteration is milestones M0–M3: the owner can add folders, legacy labels import, empty clips disappear, and every remaining clip has counts, classes and directions to review. Each milestone ends with a demo on real data and all its checks passing.

**M0 — Foundations**

- [x] Monorepo per section 7; `docker compose up` brings up db (PostGIS + pgvector), api, worker, web
- [x] Alembic migration for all section 8 tables; `scripts/dev_seed.py`
- [x] Pydantic settings; structured logging; job queue with retry and progress
- [x] OpenAPI → TS client generation wired; CI running lint, types and tests
- [x] `CLAUDE.md`, `docs/DESIGN.md` (this doc), first ADRs (stack, DB, queue)

**M1 — Ingest and legacy import**

- [ ] Setup screen: property, map, sites with aliases, heading cone
- [ ] `core/folder_names.py` with tests covering every real folder name listed in section 12
- [ ] Add-folder flow with preview → confirm; scan, hash, probe, timestamps stages; effort
- [ ] Timestamp resolver with OCR, filename, container, EXIF and mtime candidates plus consistency flags
- [ ] TrailcamParser importer with dry-run report (counts per folder must match the section 12.4 table)
- [ ] Clips screen: browse with filters and a detail drawer

* Acceptance: all `Judy's` folders ingest with no duplicates (zips skipped); ≥ 99% of media get a time with confidence ≥ medium; the import report reproduces 513 positives / 119 buck clips / 518 direction tags.

**M2 — Detection, tracking, empty filter**

- [ ] Model registry + `scripts/get_models.py` (sha256 and license check)
- [ ] Detect (MegaDetector v6 permissive variant, ONNX), sample, track, quality stages
- [ ] Empty filter with grey-band review; snippets
- [ ] Label transfer (11.1); count and empty metrics in `evaluate.py`

* Acceptance: ≥ 98% animal-clip recall and ≥ 85% exact count on the golden test split; ≥ 1 clip/s on the RTX 3070.

**M3 — Classification, direction, review loop**

- [ ] SpeciesNet on crops; deer-class head v0 trained from legacy labels (`training/`), shipped as ONNX
- [ ] Direction stage + per-deployment heading fit from legacy direction labels
- [ ] Layer 2 memory; review queue with priority, hotkeys, undo, and automation-rate panel
- [ ] Calibrated auto-accept thresholds

* Acceptance: buck precision ≥ 95% and recall ≥ 85%; direction ±45° ≥ 85%; a correction visibly changes predictions on similar clips; automation rate is reported.

**M4 — Conditions and analytics**

- [ ] Open-Meteo history cache; sun, moon, calendar, rut-phase editor; events + event\_conditions
- [ ] Analytics: activity clock, wind rose, heatmap, rate-by-condition with CI, GLM effects
- [ ] Map: sites, heading cones, bearing roses

* Acceptance: the dawn/dusk buck peaks appear in the activity clock, with n and effort shown.

**M5 — Individuals and highlights**

- [ ] Embeddings, re-ID suggestions, clusters to name, merge/split; Individuals screen
- [ ] Notable-buck ranking; Highlights feed

**M6 — Movement, replay, forecast**

- [ ] Cross-camera links; Replay screen with sunset-relative scrubber and time-of-year slider
- [ ] Forecast screen

**M7 — Hardening and packaging**

- [ ] CPU fallback, error recovery, backups; Windows installer exploration (Tauri + Python sidecar)

## 18. Instructions for the coding session

Copy this section into the repo's `CLAUDE.md` on day one. It is written for a Claude coding agent building iteration 1 (M0–M3).

**Context**

- The owner is a capable developer on Windows with an RTX 3070. The property ("Judy's") is near South Lyon, Michigan, centered at 42.493, -83.665 (America/Detroit).
- Media lives at `C:\Users\pwall\Desktop\TrailCamera\Judy's\`. The legacy app is at `C:\Users\pwall\Desktop\Code\TrailcamParser\` (reference only: reuse its hotkey scheme and watermark-OCR idea, not its code).
- Create the new repo as a sibling folder, `C:\Users\pwall\Desktop\Code\trailcam\`, unless the owner says otherwise.

**Order of work**

1. Build M0 completely before any ML. Get the skeleton, schema, queue and CI green.
2. In M1, write `core/` functions test-first. The real folder names and legacy counts in section 12 are ready-made test cases.
3. Before M2, ask the owner for 10–20 short fixture clips covering: empty/wind, single buck day, single buck IR night, doe + fawns, foggy lens, turkey, person.
4. Do not start M4+ until the M2 and M3 gates in section 16 pass on the golden split.

**Guardrails (non-negotiable)**

- Never write, rename, move or delete anything inside media folders. Read-only. The legacy app renamed files; this one must not.
- Never treat an all-zero legacy entry as a negative label.
- Never overwrite a human label with a model output.
- Never compute analytics from raw clip counts. Use events / effort.
- Never let an AGPL or non-commercial model or dataset into the shipped path. Record the license in `models/registry.yaml` before first use.
- Never hand-edit `apps/web/src/api/` (generated).
- Keep `core/` free of I/O, DB, GPU and framework imports.

**Conventions**

- Python 3.12, `uv`, ruff (line length 100), mypy strict for `core/`, pytest. Type hints everywhere; dataclasses or Pydantic for domain types.
- TypeScript strict, React function components, TanStack Query for server state, feature folders.
- Each pipeline stage is a pure function over inputs plus a thin job wrapper. It must be idempotent and keyed by `(target, stage, model_version, config_hash)`.
- Requirement IDs (`FR-ING-3`) go in test names and commit messages.
- Small PR-sized commits; conventional commit messages.
- Record each significant decision as an ADR in `docs/adr/NNNN-title.md`.
- When unsure about domain behaviour (deer biology, hunting practice), make it configurable with a sensible default and note it in the ADR rather than hard-coding.

**Definition of done for any feature:** code + tests + types pass, the requirement ID is referenced, the docs are updated if behaviour changed, and a demo works on real `Judy's` data.

## 19. Risks, open questions and references

**Risks and mitigations**

| Risk | Mitigation |
| --- | --- |
| Buck vs doe is hard in shed season and at night | Antlerless-adult class, seasonal prior, quality gating; abstain to review |
| Re-ID of deer is unproven (no production deer model found) | Assistive top-3 only; spatio-temporal priors; recent-sighting matching for antler growth; never auto-merge on low margin |
| Only 34 big-buck examples | Treat as ranking, collect thumbs-up/down, retrain head each release, sort through more clips to manually find new examples |
| Two sites and \~500 labels risk overfitting | Deployment-wise splits, cross-site test, public data augmentation (license-checked) |
| Camera clock errors corrupt sun-relative analytics | Multi-source timestamps, consistency flags, setup-clip anchoring |
| Sparse data makes condition effects noisy | Show n and CI everywhere; grey thin bins; GLM with offsets; plain-language only when the CI excludes 1 |
| Weather API terms for commercial use | Abstract the provider behind `integrations/weather.py`; review terms before release |
| Model licenses change | Registry with license field + CI check; adapters make swaps cheap |
| Video decode throughput | Process pool, keyframe seeking, 2 fps sampling; NVDEC later |

**Open questions for the owner**

- [ ] Answered: southern Michigan, near South Lyon; property centroid 42.493, -83.665. Use this for weather, sun and moon until a boundary is drawn.
- [ ] Actual heading and lat/lon of East Edge, West Hub, and the other sites (SE, FP E, FP W, W).
- [ ] Is "Judy's" the only property, or should multi-property be in v1?
- [ ] Camera models in use (affects overlay OCR region and container metadata).
- [ ] Preferred repo location and name, if not `Code\trailcam`.

**References**

- [MegaDetector](https://github.com/microsoft/MegaDetector) and [model zoo](https://microsoft.github.io/MegaDetector/model_zoo/) (v6 variants with MIT/Apache options)
- [PytorchWildlife](https://github.com/microsoft/Pytorch-Wildlife)
- [SpeciesNet](https://github.com/google/cameratrapai) (Apache-2.0)
- [WildlifeDatasets / MegaDescriptor paper](https://arxiv.org/abs/2311.09118)
- [MiewID multispecies re-ID](https://arxiv.org/abs/2412.05602)
- [Open-Meteo](https://open-meteo.com/)
- [LILA BC camera-trap datasets](https://lila.science/)
- Competitive reference: Moultrie Buck List, Tactacam Reveal app (both tied to their own cameras)
- Project notes: `claude/design-ingest-and-legacy-labels.md` in this project
