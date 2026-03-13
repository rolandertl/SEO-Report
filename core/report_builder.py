from core.context import ReportContext

from metrics.visibility import build_visibility_block
from metrics.top_urls import build_top_urls_block
from metrics.keyword_profile import build_keyword_profile_block
from metrics.interesting_rankings import build_interesting_rankings_block
from metrics.ranking_changes import build_newcomers_block, build_winners_block, build_losers_block

from metrics.backlinks import build_backlinks_block
from metrics.ai_overview import build_ai_overview_block
from metrics.local_seo_fdm import build_local_seo_fdm_blocks


def build_report(
    ctx: ReportContext,
    sistrix_api_key: str,
    openai_api_key: str,
    uberall_input: dict | None = None,
    uberall_api_key: str = "",
    google_places_api_key: str = "",
    insites_api_key: str = "",
) -> list[dict]:
    blocks: list[dict] = []

    blocks.append(build_visibility_block(ctx, sistrix_api_key, openai_api_key))
    blocks.append(build_top_urls_block(ctx, sistrix_api_key, openai_api_key))
    blocks.append(build_keyword_profile_block(ctx, sistrix_api_key, openai_api_key))
    blocks.append(build_interesting_rankings_block(ctx, sistrix_api_key, openai_api_key))

    blocks.append(build_newcomers_block(ctx, sistrix_api_key, openai_api_key))
    blocks.append(build_winners_block(ctx, sistrix_api_key, openai_api_key))
    blocks.append(build_losers_block(ctx, sistrix_api_key, openai_api_key))

    # Local SEO (Firmendaten Manager + Google)
    blocks.extend(
        build_local_seo_fdm_blocks(
            ctx,
            uberall_input or {},
            uberall_api_key=uberall_api_key,
            google_places_api_key=google_places_api_key,
            insites_api_key=insites_api_key,
        )
    )
    blocks.append(build_ai_overview_block(ctx, openai_api_key))

    # SISTRIX Backlinks (vorerst Fake-Daten)
    blocks.append(build_backlinks_block(ctx, sistrix_api_key, openai_api_key))

    return blocks
