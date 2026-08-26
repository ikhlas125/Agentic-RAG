from langchain_text_splitters import ExperimentalMarkdownSyntaxTextSplitter
import tiktoken
import re
import uuid
import json
import os
from pathlib import Path

_TOKENIZER = tiktoken.encoding_for_model("text-embedding-3-small")

_TABLE_REF_PATTERN = re.compile(r"\[TABLE_REF:([0-9a-f-]{36})\]")
_PAGE_MARKER_PATTERN = re.compile(r"<!-- page:(\d+) -->\n?")

_HEADER_KEYS = ("Header 1", "Header 2", "Header 3", "Header 4", "Header 5", "Header 6")

MIN_CHUNK_TOKENS = 50


def split_document(markdown_text: str):

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
        ("#####", "Header 5"),
        ("######", "Header 6"),
    ]

    splitter = ExperimentalMarkdownSyntaxTextSplitter(headers_to_split_on=headers_to_split_on)
    return splitter.split_text(markdown_text)


def extract_tables(path):

    with open(path, "r", encoding="utf-8") as file:
        markdown_text = file.read()

    tables = {}

    def _replace_table(match):
        table_id = str(uuid.uuid4())
        tables[table_id] = match.group(1).strip()
        return f"[TABLE_REF:{table_id}]"

    markdown_text = re.sub(
        r"<!-- table start -->(.*?)<!-- table end -->",
        _replace_table,
        markdown_text,
        flags=re.DOTALL,
    )

    return markdown_text, tables


def breadcrumb_for(metadata, keys=_HEADER_KEYS):
    parts = [str(metadata[key]).strip("* ") for key in keys if metadata.get(key)]
    return " > ".join(parts)


def build_embedding_text(page_content, metadata, captions=None, prefix_keys=None):

    captions = captions or {}
    breadcrumb = breadcrumb_for(metadata)
    fallback = f"{breadcrumb} — table" if breadcrumb else "table"

    def _describe(match):
        return captions.get(match.group(1), fallback)

    text = _TABLE_REF_PATTERN.sub(_describe, page_content).strip()
    text = text or fallback

    prefix = breadcrumb_for(metadata, keys=prefix_keys if prefix_keys is not None else _HEADER_KEYS)
    return f"{prefix}\n{text}" if prefix else text


def resolve_tables(page_content, tables):

    def _resolve(match):
        return tables.get(match.group(1), match.group(0))

    return _TABLE_REF_PATTERN.sub(_resolve, page_content)


def _copy_chunk(chunk):
    return dict(chunk, metadata=dict(chunk["metadata"]))


def _add_section(metadata, breadcrumb, prepend=False):
    if not breadcrumb:
        return
    sections = metadata.setdefault("sections", [breadcrumb_for(metadata)])
    if breadcrumb not in sections:
        if prepend:
            sections.insert(0, breadcrumb)
        else:
            sections.append(breadcrumb)


def merge_small_chunks(chunks, min_tokens=MIN_CHUNK_TOKENS):

    if not chunks:
        return chunks

    merged = [_copy_chunk(chunks[0])]
    for chunk in chunks[1:]:
        if chunk["token_count"] < min_tokens:
            prev = merged[-1]
            breadcrumb = breadcrumb_for(chunk["metadata"])
            if breadcrumb and breadcrumb != breadcrumb_for(prev["metadata"]):
                _add_section(prev["metadata"], breadcrumb)
            prev["content"] = f"{prev['content']}\n\n{chunk['content']}".strip()
            prev["embedding_text"] = f"{prev['embedding_text']}\n\n{chunk['embedding_text']}".strip()
            prev["metadata"]["page_end"] = chunk["metadata"].get("page_end", prev["metadata"].get("page_end"))
            prev["token_count"] = len(_TOKENIZER.encode(prev["content"]))
        else:
            merged.append(_copy_chunk(chunk))

    if len(merged) > 1 and merged[0]["token_count"] < min_tokens:
        first = merged.pop(0)
        nxt = merged[0]
        first_breadcrumb = breadcrumb_for(first["metadata"])
        if first_breadcrumb and first_breadcrumb != breadcrumb_for(nxt["metadata"]):
            _add_section(nxt["metadata"], first_breadcrumb, prepend=True)
        nxt["content"] = f"{first['content']}\n\n{nxt['content']}".strip()
        nxt["embedding_text"] = f"{first['embedding_text']}\n\n{nxt['embedding_text']}".strip()
        nxt["metadata"]["page_start"] = first["metadata"].get("page_start", nxt["metadata"].get("page_start"))
        nxt["token_count"] = len(_TOKENIZER.encode(nxt["content"]))

    for idx, chunk in enumerate(merged, 1):
        chunk["id"] = idx

    return merged


def page_content_boxes(doc_json_path):
    with open(doc_json_path, encoding="utf-8") as f:
        pages = json.load(f)

    boxes = {}
    for page in pages:
        content_boxes = [b["bbox"] for b in page["page_boxes"] if b["class"] not in ("page-header", "page-footer")]
        if content_boxes:
            boxes[page["metadata"]["page_number"]] = [
                min(b[0] for b in content_boxes),
                min(b[1] for b in content_boxes),
                max(b[2] for b in content_boxes),
                max(b[3] for b in content_boxes),
            ]

    return pages[0]["metadata"]["file_path"], boxes


def process_document(fixed_md_path, out_dir, domain):

    os.makedirs(out_dir, exist_ok=True)

    markdown_text, tables = extract_tables(fixed_md_path)

    with open(os.path.join(out_dir, "tables.json"), "w", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False, indent=2)

    docs = split_document(markdown_text)

    header_values = {key: set() for key in _HEADER_KEYS}
    for doc in docs:
        for key in _HEADER_KEYS:
            if doc.metadata.get(key):
                header_values[key].add(doc.metadata[key])
    varying_header_keys = [key for key in _HEADER_KEYS if len(header_values[key]) > 1]

    chunks = []
    current_page = None
    for i, doc in enumerate(docs, 1):
        page_numbers = [int(n) for n in _PAGE_MARKER_PATTERN.findall(doc.page_content)]
        if page_numbers:
            current_page = page_numbers[-1]
        doc.metadata["page_start"] = page_numbers[0] if page_numbers else current_page
        doc.metadata["page_end"] = current_page
        doc.metadata["domain"] = domain
        doc.page_content = _PAGE_MARKER_PATTERN.sub("", doc.page_content)

        table_refs = _TABLE_REF_PATTERN.findall(doc.page_content)
        if not table_refs:
            content_type = "text"
        elif _TABLE_REF_PATTERN.sub("", doc.page_content).strip():
            content_type = "mixed"
        else:
            content_type = "table"
        doc.metadata["content_type"] = content_type

        content = resolve_tables(doc.page_content, tables)
        embedding_text = build_embedding_text(doc.page_content, doc.metadata, prefix_keys=varying_header_keys)
        token_count = len(_TOKENIZER.encode(content))

        chunks.append({
            "id": i,
            "metadata": doc.metadata,
            "token_count": token_count,
            "embedding_text": embedding_text,
            "content": content,
        })

    chunks = merge_small_chunks(chunks)

    doc_json_path = os.path.join(out_dir, f"{Path(fixed_md_path).stem.removesuffix('_fixed')}.json")
    pdf_path, page_boxes = page_content_boxes(doc_json_path)

    for chunk in chunks:
        page_start = chunk["metadata"].get("page_start") or 0
        page_end = chunk["metadata"].get("page_end") or 0
        chunk["metadata"]["pdf_path"] = pdf_path
        chunk["metadata"]["bbox"] = [
            {"page": page, "bbox": page_boxes[page]}
            for page in range(page_start, page_end + 1) if page in page_boxes
        ]

    with open(os.path.join(out_dir, "chunks_.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "chunks.md"), "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(f"# Chunk {chunk['id']}\n\n")

            f.write("## Metadata\n\n")
            for key, value in chunk["metadata"].items():
                f.write(f"- **{key}:** {value}\n")
            f.write(f"- **token_count:** {chunk['token_count']}\n")

            f.write("\n## Embedding Text\n\n")
            f.write(chunk["embedding_text"])

            f.write("\n\n## Content\n\n")
            f.write(chunk["content"])
            f.write("\n\n---\n\n")

    return chunks


if __name__ == "__main__":
    name = "doc"
    fixed_md = f"backend/storage/Artifacts/{name}/{name}_fixed.md"
    out_dir = Path(f"backend/storage/Artifacts/{name}/")
    process_document(fixed_md, out_dir, domain="finance")
