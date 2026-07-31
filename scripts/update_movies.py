from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin
import random
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://letterboxd.com/its_navi/reviews/by/added/"
HTML_PATH = Path("letterboxd_debug.html")
OUTPUT_PATH = Path("src/movies.md")


def fetch_or_load_html() -> str:
    if HTML_PATH.exists():
        return HTML_PATH.read_text(encoding="utf-8")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(URL, headers=headers, impersonate="chrome")
        response.raise_for_status()
        html = response.text
    except Exception:
        if HTML_PATH.exists():
            return HTML_PATH.read_text(encoding="utf-8")
        raise

    HTML_PATH.write_text(html, encoding="utf-8")
    return html


def get_reviews(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    movies: list[dict[str, str | None]] = []

    for review in soup.select("article.production-viewing.js-production-viewing"):
        title_tag = review.select_one("h2.primaryname.prettify a")
        title = None
        movie_url = None

        if title_tag:
            title = title_tag.get_text(" ", strip=True)
            href = title_tag.get("href", "")
            movie_url = urljoin("https://letterboxd.com", href)
            if movie_url.startswith("https://letterboxd.com/its_navi"):
                movie_url = movie_url.replace("/its_navi", "", 1)
        else:
            title_elem = review.select_one("h2.primaryname.prettify")
            if title_elem:
                title = title_elem.get_text(" ", strip=True)

        body = review.select_one("div.body")
        review_text = body.get_text(" ", strip=True) if body else ""

        year = None
        year_tag = review.select_one("span.releasedate a")
        if year_tag:
            year = year_tag.get_text(" ", strip=True)

        rating = None
        rating_tag = review.select_one("span.inline-rating")
        if rating_tag:
            rating = rating_tag.get_text(" ", strip=True)
        elif review.select_one("svg.glyph.-rating"):
            rating = "★"

        if title and movie_url:
            movies.append(
                {
                    "title": title,
                    "url": movie_url,
                    "poster": None,
                    "review": review_text,
                    "year": year,
                    "rating": rating,
                }
            )

    return movies


def fetch_film_details(movie_url: str) -> dict[str, str | None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(movie_url, headers=headers, impersonate="chrome")
        response.raise_for_status()
        film_html = response.text
    except Exception:
        return {"poster": None, "review": None, "year": None}

    film_soup = BeautifulSoup(film_html, "html.parser")

    poster = None
    meta_tag = film_soup.select_one('meta[property="og:image"]') or film_soup.select_one(
        'meta[name="twitter:image"]'
    )
    if meta_tag and meta_tag.get("content"):
        poster = meta_tag.get("content")

    if not poster:
        poster_tag = film_soup.select_one('img[data-testid="poster"]')
        if poster_tag:
            poster = poster_tag.get("src") or poster_tag.get("data-src") or poster_tag.get("data-original")

    if not poster:
        for candidate in film_soup.select("img"):
            src = candidate.get("src") or candidate.get("data-src") or candidate.get("data-original")
            if not src:
                continue
            if "poster" in src.lower() or "film" in src.lower():
                poster = src
                break

    review_text = ""
    for selector in [
        "div.body-text.js-review-body",
        "div.body-text.-prose.-reset.js-review-body.js-collapsible-text",
        "div.review",
        ".review",
    ]:
        review_block = film_soup.select_one(selector)
        if review_block:
            review_text = review_block.get_text(" ", strip=True)
            if review_text:
                break

    year = None
    if review_text:
        match = re.search(r"\b(19|20)\d{2}\b", review_text)
        if match:
            year = match.group(0)

    genres: list[str] = []
    for genre_link in film_soup.select("a[href*='/genre/']"):
        label = genre_link.get_text(" ", strip=True)
        if label:
            genres.append(label)

    unique_genres = list(dict.fromkeys(genres))
    genre_text = ", ".join(unique_genres) if unique_genres else None

    return {"poster": poster, "review": review_text, "year": year, "genres": genre_text}


def extract_rating(review_text: str, raw_rating: str | None = None) -> str:
    if raw_rating:
        text = raw_rating.strip()
        if text and any(symbol in text for symbol in "★☆"):
            return text

        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if match:
            return match.group(1)

    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[/]?5", review_text)
    if match:
        return match.group(1)

    match = re.search(r"★+", review_text)
    if match:
        return match.group(0)

    return "No rating"


def rating_to_stars(rating: str) -> str:
    """Convert Letterboxd-style ratings into emoji stars."""
    if not rating or rating == "No rating":
        return "No rating"

    if re.fullmatch(r"[★☆\s]+", rating):
        full = rating.count("★")
        empty = rating.count("☆")
        return "⭐" * full + "☆" * empty

    try:
        value = float(rating)
    except ValueError:
        return rating

    full = int(value)
    half = value - full >= 0.5
    empty = 5 - full - (1 if half else 0)

    result = "⭐" * full
    if half:
        result += "⭐"
    result += "☆" * empty
    return result


def select_movie(movies: list[dict[str, str | None]]) -> dict[str, str | None]:
    state_path = Path(".last_selected_movie")
    previous_url = None
    if state_path.exists():
        previous_url = state_path.read_text(encoding="utf-8").strip()

    current_title = None
    if OUTPUT_PATH.exists():
        existing_text = OUTPUT_PATH.read_text(encoding="utf-8")
        match = re.search(r'^movie-title:\s*"?(.*?)"?\s*$', existing_text, flags=re.MULTILINE)
        if match:
            current_title = match.group(1).strip()

    excluded_urls = set()
    if previous_url:
        excluded_urls.add(previous_url)
    if current_title:
        for movie in movies:
            if str(movie.get("title") or "").strip() == current_title:
                excluded_urls.add(str(movie.get("url") or "").strip())

    candidates = [movie for movie in movies if str(movie.get("url") or "").strip() not in excluded_urls]
    if not candidates:
        candidates = movies

    selected = random.choice(candidates)
    state_path.write_text(str(selected.get("url") or ""), encoding="utf-8")
    return selected


html = fetch_or_load_html()
movies = get_reviews(html)

if not movies:
    raise RuntimeError("No reviews found in the Letterboxd HTML snapshot")


movie = select_movie(movies)

film_details = fetch_film_details(str(movie.get("url") or ""))
movie["poster"] = film_details.get("poster")

if not movie.get("title"):
    raise RuntimeError("Selected movie is missing a title")

def yaml_quote(value: str) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{text}"'

review_text = str(
    movie.get("review")
    or film_details.get("review")
    or "No review written."
).strip()

cleanup_patterns = [
    (r"^.*?review published on Letterboxd:\s*", re.IGNORECASE),
    (r"\s+Translate\s+Translated from\s+by\s*$", re.IGNORECASE),
    (r"^.*?\b(?:Watched|Liked|Disliked|Reviewed|Added)\b", re.IGNORECASE),
    (r"^\s*\d{4}\s*", 0),  # Year only
    (r"^\s*(?:★|☆|[0-9.]+\s*/?\s*5)\s*", 0),  # Rating
    (r"^\s*(?:Watched|Liked|Disliked|Added)\s*", re.IGNORECASE),
    (r"^\s*\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s*", 0),  # 12 Apr 2025
    (r"^\s*[A-Za-z]{3,9}\s+\d{4}\s*", 0),  # Apr 2025
]

for pattern, flags in cleanup_patterns:
    review_text = re.sub(pattern, "", review_text, flags=flags)

movie_title = str(movie.get("title") or "Movie Recommendation").replace("\n", " ").strip()
movie_poster = str(movie.get("poster") or "")
movie_link = str(movie.get("url") or "")
review_text = re.sub(r"\s+", " ", review_text).strip(" -—:")
movie_year = str(movie.get("year") or film_details.get("year") or "")
movie_genre = str(film_details.get("genres") or "")
rating = extract_rating(review_text, str(movie.get("rating") or ""))
stars = rating_to_stars(rating)

markdown = f"""---
title: Movie Recommendation
movie-title: {yaml_quote(movie_title)}
movie-poster: {yaml_quote(movie_poster)}
movie-link: {yaml_quote(movie_link)}
movie-rating: {yaml_quote(stars)}
movie-year: {yaml_quote(movie_year)}
movie-genre: {yaml_quote(movie_genre)}
---

## Review

{review_text}
"""

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(markdown, encoding="utf-8")