from langchain_text_splitters import ExperimentalMarkdownSyntaxTextSplitter
from transformers import AutoTokenizer

_TOKENIZER = AutoTokenizer.from_pretrained("BAAI/bge-base-en-v1.5")

def split_document(path: str):

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
        ("#####", "Header 5"),
        ("######", "Header 6"),
    ]

    with open(path, "r", encoding="utf-8") as file:
        markdown_text = file.read()

    splitter = ExperimentalMarkdownSyntaxTextSplitter(headers_to_split_on=headers_to_split_on)
    docs = splitter.split_text(markdown_text)

    return docs, markdown_text

# def enrichMetadata(markdown_text :str):


docs, markdown_text = split_document(
    "backend/storage/Artifacts/doc/doc_fixed.md"
)

with open("backend/storage/documents/chunks.md", "w", encoding="utf-8") as f:

    for i, chunk in enumerate(docs, 1):

        token_count = len(
            _TOKENIZER.encode(
                chunk.page_content,
                add_special_tokens=False
            )
        )

        chunk.metadata["token_count"] = token_count

        f.write(f"# Chunk {i}\n\n")

        f.write("## Metadata\n\n")
        for key, value in chunk.metadata.items():
            f.write(f"- **{key}:** {value}\n")

        f.write("\n## Content\n\n")
        f.write(chunk.page_content)
        f.write("\n\n---\n\n")
