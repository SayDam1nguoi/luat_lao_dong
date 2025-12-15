# data_processing/context_builder.py

def build_context_from_hits(hits, max_chars: int = 6000) -> str:
    ctx = []
    total = 0

    for h in hits:
        source = h.metadata.get("source", "unknown")
        page = h.metadata.get("page", "?")
        seg = f"[Nguồn: {source}, Trang: {page}]\n{h.page_content.strip()}"

        if total + len(seg) > max_chars:
            break

        ctx.append(seg)
        total += len(seg)

    return "\n\n".join(ctx)
