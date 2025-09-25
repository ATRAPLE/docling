from token_count import TokenCount
import os
from docling.document_converter import DocumentConverter

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

converter = DocumentConverter()

# Definindo Pastas de Entrada e Saída
pdf_input_dir = "pdf_input"
md_output_dir = "md_output"

# Ensure output directory exists
os.makedirs(md_output_dir, exist_ok=True)

tc = TokenCount(model_name="gpt-3.5-turbo")

for filename in os.listdir(pdf_input_dir):
    if filename.lower().endswith(".pdf"):
        pdf_path = os.path.join(pdf_input_dir, filename)
        print(f"Converting: {pdf_path}")
        try:
            result = converter.convert(pdf_path)
            md_content = result.document.export_to_markdown()
            md_filename = os.path.splitext(filename)[0] + ".md"
            md_path = os.path.join(md_output_dir, md_filename)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"Saved markdown to: {md_path}")
            print(f"Token count: {tc.num_tokens_from_string(md_content)}")
        except Exception as e:
            print(f"Error converting {pdf_path}: {e}")