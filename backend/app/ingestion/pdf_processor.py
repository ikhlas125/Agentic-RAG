import os
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
import pymupdf4llm
import json
from backend.app.helper.helper import make_json_serializable
from pathlib import Path
import fitz

def pdf_parser(input_path :str):

    text = pymupdf4llm.to_markdown(
        input_path,
        header=False,
        footer=False,
        page_chunks=True,
        use_ocr=False,
    )

    text = make_json_serializable(text)
    name = Path(input_path).stem

    output_dir = f"backend/storage/Artifacts/{name}"
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(text, f, ensure_ascii=False, indent=2)

    parts = [page["text"] for page in text]

    markdown = "\n\n".join(parts)

    with open(os.path.join(output_dir, f"{name}.md"), "w", encoding="utf-8") as file:
        file.write(markdown)

def replace_tables_with_docling( doc_json, doc_docling_json, doc_docling_md, out_md):

    pages = json.load(open(doc_json, encoding="utf-8"))
    docling = json.load(open(doc_docling_json, encoding="utf-8"))

    blocks, current = [], []
    for line in open(doc_docling_md, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("|"):
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))

    if len(blocks) != len(docling["tables"]):
        raise ValueError(
            f"{len(blocks)} table blocks in {doc_docling_md} vs "
            f"{len(docling['tables'])} table entries in {doc_docling_json}"
        )

    docling_pages = {}
    for block, table in zip(blocks, docling["tables"]):
        page_no = table["prov"][0]["page_no"]
        docling_pages.setdefault(page_no, []).append(block)

    table_pages = sorted(
        page["metadata"]["page_number"]
        for page in pages
        if any(box.get("class") == "table" for box in page.get("page_boxes", []))
    )
    page_rank = {page_number: i + 1 for i, page_number in enumerate(table_pages)}

    mismatches = []
    for page in pages:
        rank = page_rank.get(page["metadata"]["page_number"])
        if rank is None:
            continue

        table_boxes = sorted(
            (box for box in page["page_boxes"] if box.get("class") == "table"),
            key=lambda box: box["pos"][0],
        )
        replacements = docling_pages.get(rank, [])

        if len(table_boxes) != len(replacements):
            mismatches.append(
                (page["metadata"]["page_number"], len(table_boxes), len(replacements))
            )

        pairs = list(zip(table_boxes, replacements))
        extra = replacements[len(table_boxes):]
        unmatched_boxes = table_boxes[len(replacements):]

        text = page["text"]

        for box in reversed(unmatched_boxes):
            start, stop = box["pos"]
            wrapped = f"<!-- table start -->\n{text[start:stop]}\n<!-- table end -->\n"
            text = text[:start] + wrapped + text[stop:]

        for i in range(len(pairs) - 1, -1, -1):
            box, block = pairs[i]
            table_blocks = [block, *extra] if i == len(pairs) - 1 and extra else [block]
            wrapped = "\n\n".join(
                f"<!-- table start -->\n{table_block}\n<!-- table end -->\n"
                for table_block in table_blocks
            )
            start, stop = box["pos"]
            text = text[:start] + wrapped + text[stop:]
        page["text"] = text

    for page in pages:
        page["text"] = f"<!-- page:{page['metadata']['page_number']} -->\n{page['text']}"

    cleaned_markdown = "\n\n".join(page["text"] for page in pages)
    with open(out_md, "w", encoding="utf-8") as file:
        file.write(cleaned_markdown)

    if mismatches:
        print(f"{len(mismatches)} page(s) with mismatched table counts (page, simple, docling):")
        for mismatch in mismatches:
            print(" ", mismatch)

    return mismatches


def table_pages_pdf(doc_json, pdf_in):
    doc_pages = json.load(open(doc_json))
    pages = sorted(
        page["metadata"]["page_number"]
        for page in doc_pages
        if any(box.get("class") == "table" for box in page.get("page_boxes", []))
    )

    if not pages:
        print(f"No table pages detected in {doc_json}; skipping table_pages_pdf.")
        return

    name = Path(pdf_in).stem

    pdf_out = f"backend/storage/Artifacts/{name}/{name}_table_pages.pdf"

    doc = fitz.open(pdf_in)
    doc.select([p - 1 for p in pages])
    doc.save(pdf_out)
    doc.close()


def docling_parser(input_path: str):

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    result = converter.convert(input_path)

    name = Path(input_path).parent.name
    
    output_dir = f"backend/storage/Artifacts/{name}"
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, f"{name}_docling.md"), "w") as f:
        f.write(result.document.export_to_markdown())

    with open(os.path.join(output_dir, f"{name}_docling.json"), "w") as f:
        f.write(result.document.model_dump_json(indent=2))


pdf_parser("backend/storage/documents/doc.pdf")
table_pages_pdf("backend/storage/Artifacts/doc/doc.json","backend/storage/documents/doc.pdf")
docling_parser("backend/storage/Artifacts/doc/doc_table_pages.pdf")
replace_tables_with_docling("backend/storage/Artifacts/doc/doc.json","backend/storage/Artifacts/doc/doc_docling.json","backend/storage/Artifacts/doc/doc_docling.md","backend/storage/Artifacts/doc/doc_fixed.md")