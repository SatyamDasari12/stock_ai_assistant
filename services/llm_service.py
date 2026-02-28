from __future__ import annotations

from typing import Any, Sequence

from groq import Groq

from models.types import StockScorecard, WeeklyPredictionResult
from utils.config import get_app_config
from utils.logging import logger


def _build_messages(
    symbol: str,
    scorecard: StockScorecard | None,
    prediction: WeeklyPredictionResult,
    news_summaries: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    news_block = ""
    if news_summaries:
        joined = "\n".join(f"- {n}" for n in news_summaries)
        news_block = f"\nRelevant news/headlines:\n{joined}\n"

    tech_block = ""
    if scorecard is not None:
        tech_block = (
            f"Trend score: {scorecard.trend_score}/3\n"
            f"Momentum score: {scorecard.momentum_score}/3\n"
            f"Volume score: {scorecard.volume_score}/2\n"
            f"Volatility score: {scorecard.volatility_score}/2\n"
            f"Total technical score (0-10): {scorecard.total_score}\n"
            f"Interpretation: {scorecard.interpretation}\n"
        )

    user_content = (
        "You are an equity analyst for Indian markets (NSE/BSE).\n"
        f"Stock: {symbol}\n"
        f"One-week statistical outlook: trend={prediction.trend}, "
        f"probability={prediction.probability:.0%}, "
        f"expected range={prediction.expected_low:.2f}–{prediction.expected_high:.2f}.\n"
        f"{tech_block}"
        f"{news_block}"
        "Give a concise 3–5 sentence explanation of the outlook, mentioning trend, "
        "risk factors, and what a short-term trader should watch. "
        "Do NOT give trade calls, targets, or position sizing advice."
    )

    return [
        {
            "role": "system",
            "content": (
                "You are an experienced Indian stock market analyst. "
                "You strictly avoid giving direct investment advice. "
                "You only explain setups, risks, and scenarios."
            ),
        },
        {"role": "user", "content": user_content},
    ]


def explain_weekly_outlook(
    symbol: str,
    scorecard: StockScorecard | None,
    prediction: WeeklyPredictionResult,
    news_summaries: Sequence[str] | None = None,
) -> str:
    cfg = get_app_config().groq
    if not cfg.api_key:
        logger.info("GROQ_API_KEY not set; falling back to rule-based explanation.")
        return _fallback_explanation(scorecard, prediction)

    try:
        client = Groq(api_key=cfg.api_key)
        messages = _build_messages(symbol, scorecard, prediction, news_summaries)
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            temperature=cfg.temperature,
            max_tokens=320,
        )
        return resp.choices[0].message.content or _fallback_explanation(
            scorecard, prediction
        )
    except Exception as exc:
        logger.exception(f"Groq explanation failed: {exc}")
        return _fallback_explanation(scorecard, prediction)


def _fallback_explanation(
    scorecard: StockScorecard | None,
    prediction: WeeklyPredictionResult,
) -> str:
    base = (
        f"Model expects a {prediction.trend.lower()} bias for the coming week "
        f"with an indicative range between {prediction.expected_low:.2f} and "
        f"{prediction.expected_high:.2f}."
    )
    if not scorecard:
        return (
            base
            + " Technical scorecard is unavailable, so treat this as a rough, "
            "volatility-based projection."
        )

    if scorecard.total_score >= 7:
        extra = (
            " Technical structure is supportive with healthy trend and momentum "
            "scores, but price can still whipsaw near resistance levels."
        )
    elif scorecard.total_score >= 5:
        extra = (
            " Technicals are mixed; follow-through will depend on how price reacts "
            "to key moving averages and recent swing highs."
        )
    else:
        extra = (
            " Technical backdrop is weak or choppy, so breakouts may fail and "
            "risk management is important."
        )
    return base + extra

