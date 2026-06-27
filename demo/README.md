# `demo/` — Demonstration & example files

This folder holds everything used to **show the software off**, kept separate from
the application code in `app/`.

> 这个文件夹集中存放**用于演示软件的实例/展示文件**,与 `app/` 里的程序代码分开,便于区分。

```
demo/
├── showcase/
│   └── AI_SOFTWARE_SHOWCASE_FILE.md   # the guided-demo document the platform ingests
└── examples/
    ├── company_policy.txt             # sample HR policy (TXT)
    ├── product_faq.md                 # sample support FAQ (Markdown)
    └── employees.csv                  # sample employee roster (CSV)
```

## How these are used

- **`showcase/AI_SOFTWARE_SHOWCASE_FILE.md`** is the main demonstration document.
  Running the showcase (the dashboard's **Run showcase demo** button, or
  `python run_demo.py`) ingests this file plus the example corpus and asks a
  guided set of questions so every feature is exercised.
- **`examples/`** is a small multi-format corpus. `scripts/seed_examples.py` and
  `scripts/smoke_test.py` ingest it, and the showcase uses it alongside the
  showcase document.

You can also upload any of these files manually from the dashboard to try things
out. Add your own `.txt`, `.md`, `.csv`, or `.pdf` files here to extend the demo.
