from __future__ import annotations

import argparse
import math
from pathlib import Path

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A3, landscape

import config as cfg
from core.excel_parser import parse
from rendering.overview_renderer import draw_overview_pages
from rendering.tree_renderer import draw_tree_pages


def _plan_pages(groups: list) -> tuple[list[int], dict[str, int], int]:
    """
    Assign page numbers to all pages in the PDF.

    Returns:
        overview_page_nums  : list of page numbers for overview pages
        f1_first_pages      : maps group.code → first F1 tree page number
        total_pages         : total page count
    """
    n_groups = len(groups)
    n_ov_pages = math.ceil(n_groups / cfg.CARDS_PER_PAGE)

    # Overview pages: 1..n_ov_pages
    overview_page_nums = list(range(1, n_ov_pages + 1))

    # F1 tree pages: assigned sequentially after overview
    f1_first_pages: dict[str, int] = {}
    cursor = n_ov_pages + 1

    for group in groups:
        f1_first_pages[group.code] = cursor
        n_chunks = _count_chunks(group)
        cursor += n_chunks

    total_pages = cursor - 1
    return overview_page_nums, f1_first_pages, total_pages


def _count_chunks(group) -> int:
    """How many F1 tree pages does this group need."""
    from rendering.tree_renderer import _chunk_sections

    chunks = _chunk_sections(group.f1_sections, cfg.MAX_COLS_PER_PAGE)
    return len(chunks)


def _overview_page_for(group_index: int) -> int:
    return (group_index // cfg.CARDS_PER_PAGE) + 1


def render(
    excel_path: str,
    output_path: str,
    title: str = cfg.DEFAULT_TITLE,
    subtitle: str = cfg.DEFAULT_SUBTITLE,
) -> None:
    """
    Full pipeline: Excel → PDF.

    1. Parse Excel into F0Group objects
    2. Plan page numbers
    3. Draw overview pages
    4. Draw F1 tree pages
    """
    print(f"[1/3] Parsing {excel_path} ...")
    groups, col_labels = parse(excel_path)
    print(f"      {len(groups)} F0 groups found:")
    for g in groups:
        n_sec = len(g.f1_sections)
        n_leaves = sum(len(s.leaves) for s in g.f1_sections)
        print(
            f"      {g.code}  ({g.count} instances, "
            f"{n_sec} F1 sections, {n_leaves} leaves)"
        )

    print(f"[2/3] Planning pages ...")
    ov_page_nums, f1_first_pages, total_pages = _plan_pages(groups)
    print(f"      {len(ov_page_nums)} overview page(s)")
    print(f"      {total_pages - len(ov_page_nums)} F1 tree page(s)")
    print(f"      {total_pages} total")

    print(f"[3/3] Rendering {output_path} ...")
    c = rl_canvas.Canvas(output_path, pagesize=landscape(A3))
    c.setTitle(title)

    # Overview pages
    draw_overview_pages(
        c,
        groups=groups,
        page_nums=ov_page_nums,
        f1_first_pages=f1_first_pages,
        total_pages=total_pages,
    )

    # F1 tree pages — one group at a time
    for i, group in enumerate(groups):
        c.showPage()
        ov_pg = _overview_page_for(i)
        draw_tree_pages(
            c,
            group=group,
            first_page=f1_first_pages[group.code],
            overview_page=ov_pg,
            total_pages=total_pages,
            col_labels=col_labels,
        )

    c.save()
    size_kb = Path(output_path).stat().st_size // 1024
    print(f"      Done — {size_kb} KB")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rds-pp",
        description="Generate A3 PDF from Excel file",
    )
    ap.add_argument("excel", help="Path to input Excel file")
    ap.add_argument("output", help="Path to output PDF file")
    ap.add_argument(
        "--title",
        default=cfg.DEFAULT_TITLE,
        help=f"Overview page title (default: '{cfg.DEFAULT_TITLE}')",
    )
    ap.add_argument(
        "--subtitle",
        default=cfg.DEFAULT_SUBTITLE,
        help="Optional subtitle under the title",
    )

    return ap


def main() -> None:
    args = _build_parser().parse_args()
    render(
        excel_path=args.excel,
        output_path=args.output,
        title=args.title,
        subtitle=args.subtitle,
    )


if __name__ == "__main__":
    main()
