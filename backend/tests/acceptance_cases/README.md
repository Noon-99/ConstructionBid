# Acceptance Harness

This directory contains the acceptance regression harness that exercises the full pipeline
against representative construction project PDFs. The goal is to ensure we do not regress on
critical trades and that evidence, quantities, and costing outputs stay anchored to the drawings.
At the moment, the repository packages a single **roofing** acceptance case; additional trades can
be layered in as soon as vetted sample PDFs are available.

## Getting Started

1. **Place sample PDFs**
   - Drop the curated PDF for each configured case beneath this directory. Today only
     `roof/input.pdf` is referenced.
   - The PDFs are not committed to source control. Each subdirectory has a `.gitignore` entry to
     keep large artifacts out of the repo.

2. **Review case definitions**
   - `case_definitions.json` enumerates each acceptance case, expected trade, coverage thresholds,
     anchor quantity requirements, and heuristic guard-rails.
   - To add a new trade later:
     1. Create a new folder (for example `windows/`) and place the vetted PDF as `input.pdf`.
     2. Append a new case definition describing expectations for that trade.
     3. Re-run the suite and confirm the new case passes before relying on it.

3. **Run the suite**

```bash
cd backend
python -m tests.acceptance_cases.run_acceptance_suite --output-dir ./tests/acceptance_cases/out
```

The runner will:
- Execute the full pipeline for each configured case.
- Emit per-case summaries containing primary trade detection, coverage score, anchor quantity
  checks, heuristic cost share, stage page selections, and total cost.
- Fail the suite if any case violates the thresholds defined in `case_definitions.json`.

## Adding Future Trades

Design the harness so that future trades (masonry, interiors, MEP, civil utilities, etc.) can be
added by introducing a new folder and updating `case_definitions.json`. Each definition supports
keyword-driven anchor checks for scope, quantities, and optional specialized assertions. Until a
trade has a reliable sample PDF, leave it out of the suite so that acceptance runs stay deterministic.
