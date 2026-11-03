import pymupdf4llm

md = pymupdf4llm.to_markdown("pdf/politicas_da_loja.pdf")
with open("data/politicas_da_loja.md", "w", encoding="utf-8") as f:
    f.write(md)