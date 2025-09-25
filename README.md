# Docling PDF to Markdown Converter

Automated workflow that converts every PDF in `pdf_input/` into Markdown using the [docling](https://github.com/DS4SD/docling) pipeline and reports token counts for the converted text. The generated `.md` files are saved in `md_output/`, making it easy to inspect or post-process the extracted content.

## Project layout

```
.
├── docling_test.py        # Batch converter script (PDF → Markdown + token counting)
├── pdf_input/             # Drop your source PDFs here
├── md_output/             # Markdown output files are written here
├── requirements.txt       # Python dependencies
└── Rodar_ambiente.txt     # Quick reference for setting up the virtual environment
```

## Prerequisites

- Python 3.10+ (tested with Python 3.13)
- Git (for publishing the project)
- A Hugging Face account is **not** required, but the first run downloads models from the Hugging Face Hub.

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs:

- `docling` – document conversion pipeline
- `safetensors`, `requests`, `certifi` – helper dependencies for docling
- `token_count` – counts tokens using the GPT-3.5 tokenization rules

## Usage

1. Place one or more PDF files into `pdf_input/`.
2. (Optional) Clear out old Markdown files from `md_output/` if you want a clean run.
3. Execute the converter:

   ```powershell
   python docling_test.py
   ```

The script will:

- Iterate over every `.pdf` it finds in `pdf_input/`.
- Convert each PDF to Markdown via `DocumentConverter`.
- Write the Markdown file to `md_output/` using the same base filename.
- Print the total token count for the Markdown content.

## Environment tweaks

- **Silencing Hugging Face symlink warnings**: the script sets `HF_HUB_DISABLE_SYMLINKS_WARNING=1` to avoid noisy logs on Windows systems that do not support symlinks.
- **SSL certificate issues**: if you encounter TLS errors while models are downloaded, point Requests to the certifi bundle:

  ```powershell
  $env:REQUESTS_CA_BUNDLE = (python -m certifi)
  ```

- **Re-running downloads**: cached models are stored under `%USERPROFILE%\.cache\huggingface`. Deleting that folder forces a fresh download.

## Token counting

`TokenCount` uses the `gpt-3.5-turbo` tokenizer to estimate how many tokens each Markdown document contains—useful for budgeting when sending the text to OpenAI or compatible APIs.

## Publishing to GitHub

Once you are satisfied with the output, initialise the repository (replace the remote URL if necessary):

```powershell
git init
git remote add origin https://github.com/ATRAPLE/docling.git
git add .
git commit -m "chore: initial import"
git push -u origin main
```

> **Tip:** remove the `.venv/` folder or add it to `.gitignore` before committing. You can generate a minimal `.gitignore` with:
>
> ```powershell
> echo .venv/ > .gitignore
> echo __pycache__/ >> .gitignore
> ```

## Troubleshooting

- **Model download retries**: the first run may take a few minutes while docling pulls models (layout detection, OCR). Subsequent runs use the cache.
- **Incomplete OCR**: ensure the PDFs are not password protected and contain selectable text. For image-heavy PDFs, docling automatically falls back to OCR engines (EasyOCR, Tesseract, etc.).
- **Missing dependencies**: re-run `pip install -r requirements.txt` inside the activated virtual environment.

## Next steps

- Automate execution with a small CLI wrapper or schedule tasks.
- Extend the script to export additional formats (JSON, DOCX) from the docling document object.
- Add automated tests to validate conversions for representative documents.
