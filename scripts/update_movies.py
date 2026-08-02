from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse
import random
import re

from bs4 import BeautifulSoup
from curl_cffi import requests

# URL1 = "https://letterboxd.com/its_navi/reviews/by/added/"
URL = "https://letterboxd.com/its_navi/films/"
PROFILE_REVIEWS_URL = "https://letterboxd.com/its_navi/reviews/by/added/"
HTML_PATH = Path("letterboxd_debug.html")
OUTPUT_PATH = Path("src/movies.md")


def fetch_or_load_html() -> str:

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


def normalize_poster_candidate(candidate: str | None) -> str | None:
    if not candidate:
        return None

    candidate = candidate.strip()
    if not candidate:
        return None

    lowered = candidate.lower()
    if "default-share" in lowered or "empty-poster" in lowered:
        return None

    if candidate.startswith("/"):
        return urljoin("https://letterboxd.com", candidate)

    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate

    return None


def get_reviews(html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    movies: list[dict[str, str | None]] = []

    for item in soup.select("li.griditem"):
        react_component = item.select_one("div.react-component")
        if not react_component:
            continue

        title = (
            react_component.get("data-item-name")
            or react_component.get("data-item-full-display-name")
            or ""
        ).strip()

        film_url = react_component.get("data-target-link") or react_component.get("data-item-link") or ""
        movie_url = urljoin("https://letterboxd.com", film_url) if film_url else None

        review_url = None
        if movie_url:
            parsed = urlparse(movie_url)
            slug = parsed.path.rstrip("/").split("/")[-1]
            if slug:
                review_url = f"https://letterboxd.com/its_navi/film/{slug}/"

        rating = None
        rating_tag = item.select_one("span.rating")
        if rating_tag:
            rating = rating_tag.get_text(" ", strip=True)

        poster = None
        poster_candidate = react_component.get("data-poster-url")
        if poster_candidate:
            poster = normalize_poster_candidate(poster_candidate)

        if title and movie_url:
            movies.append(
                {
                    "title": title,
                    "url": movie_url,
                    "review_url": review_url,
                    "poster": poster,
                    "review": None,
                    "year": None,
                    "rating": rating,
                }
            )

    if movies:
        return movies

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
                    "review_url": None,
                    "poster": None,
                    "review": review_text,
                    "year": year,
                    "rating": rating,
                }
            )

    return movies


def extract_review_from_profile_listing(html: str, movie_url: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if not movie_url:
        return ""

    parsed = urlparse(movie_url)
    film_slug = parsed.path.rstrip("/").split("/")[-1]
    if not film_slug:
        return ""

    for article in soup.select("article.production-viewing"):
        title_link = article.select_one("h2.primaryname.prettify a")
        if not title_link:
            continue

        href = title_link.get("href", "")
        if not href:
            continue

        href_slug = href.rstrip("/").split("/")[-1]
        if href_slug != film_slug:
            continue

        review_block = article.select_one("div.js-review div.body-text, div.js-review .body-text")
        if review_block:
            text = review_block.get_text(" ", strip=True)
            if text:
                return text

    return ""


def fetch_film_genres(movie_url: str, headers: dict[str, str] | None = None) -> str | None:
    if not headers:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }

    parsed = urlparse(movie_url)
    film_slug = parsed.path.rstrip("/").split("/")[-1]
    if not film_slug:
        return None

    genre_url = f"https://letterboxd.com/film/{film_slug}/genres/"
    try:
        response = requests.get(genre_url, headers=headers, impersonate="chrome")
        response.raise_for_status()
    except Exception:
        return None

    genre_soup = BeautifulSoup(response.text, "html.parser")
    genres: list[str] = []
    for genre_link in genre_soup.select("a[href*='/genre/']"):
        label = genre_link.get_text(" ", strip=True)
        if label:
            genres.append(label)

    unique_genres = list(dict.fromkeys(genres))
    return ", ".join(unique_genres) if unique_genres else None


def extract_poster_url_from_html(html: str, movie_url: str | None = None) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidate_urls: list[str] = []

    meta_tag = soup.select_one('meta[property="og:image"]') or soup.select_one(
        'meta[name="twitter:image"]'
    )
    if meta_tag and meta_tag.get("content"):
        candidate_urls.append(meta_tag.get("content", ""))

    for selector in [
        'img[data-testid="poster"]',
        'img.poster',
        'img[class*="poster"]',
        'img[alt*="poster"]',
        'img[data-tmdb-id]',
    ]:
        poster_tag = soup.select_one(selector)
        if poster_tag:
            src = poster_tag.get("src") or poster_tag.get("data-src") or poster_tag.get("data-original")
            if src:
                candidate_urls.append(src)

    for candidate in soup.select("img"):
        src = candidate.get("src") or candidate.get("data-src") or candidate.get("data-original")
        if not src:
            continue
        candidate_urls.append(src)

    for element in soup.select("[data-poster-url]"):
        candidate_urls.append(element.get("data-poster-url", ""))

    for tag in soup.select('script[type="application/ld+json"]'):
        script_text = tag.get_text(" ", strip=True)
        if "image" in script_text.lower():
            image_match = re.search(r'"image"\s*:\s*"([^"]+)"', script_text)
            if image_match:
                candidate_urls.append(image_match.group(1))

    for candidate in candidate_urls:
        normalized = normalize_poster_candidate(candidate)
        if normalized:
            return normalized

    return None


def fetch_film_details(movie_url: str, review_url: str | None = None) -> dict[str, str | None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    poster = None
    review_text = ""
    genre_text = fetch_film_genres(movie_url, headers)

    try:
        profile_response = requests.get(
            PROFILE_REVIEWS_URL,
            headers=headers,
            impersonate="chrome",
        )
        profile_response.raise_for_status()
        profile_reviews_html = profile_response.text
    except Exception:
        profile_reviews_html = None

    if not review_text and profile_reviews_html:
        review_text = extract_review_from_profile_listing(profile_reviews_html, movie_url)

    candidate_urls = []
    if review_url:
        candidate_urls.append(review_url)
        if review_url.endswith("/"):
            base = review_url.rstrip("/")
            candidate_urls.extend(
                [
                    f"{base}/reviews/",
                    f"{base}/reviews/by/added/",
                ]
            )

    if movie_url:
        candidate_urls.insert(0, movie_url)

    if not candidate_urls:
        return {"poster": None, "review": None, "year": None, "genres": None}

    for target_url in candidate_urls:
        try:
            response = requests.get(target_url, headers=headers, impersonate="chrome")
            response.raise_for_status()
            film_html = response.text
        except Exception:
            continue

        film_soup = BeautifulSoup(film_html, "html.parser")

        if not genre_text:
            genre_text = fetch_film_genres(movie_url, headers)

        if not poster:
            poster = extract_poster_url_from_html(film_html, movie_url)

        if not genre_text:
            genres: list[str] = []
            for genre_link in film_soup.select("a[href*='/genre/']"):
                label = genre_link.get_text(" ", strip=True)
                if label:
                    genres.append(label)

            if not genres:
                for candidate in film_soup.select("a, span, div"):
                    text = candidate.get_text(" ", strip=True)
                    if not text:
                        continue
                    if re.search(r"\b(Drama|Comedy|Thriller|Horror|Action|Adventure|Crime|Romance|Fantasy|Science Fiction|Sci-Fi|Mystery|Animation|Family|Documentary|War|Western|History|Music|TV Movie)\b", text):
                        genres.append(text)

            unique_genres = list(dict.fromkeys(genres))
            genre_text = ", ".join(unique_genres) if unique_genres else None

        if review_url and target_url.startswith(review_url.rstrip("/")):
            if not review_text and profile_reviews_html:
                review_text = extract_review_from_profile_listing(profile_reviews_html, movie_url)
            if review_text:
                review_text = review_text.strip()
            else:
                review_selectors = [
                    "div.body-text.js-review-body",
                    "div.body-text.-prose.-reset.js-review-body.js-collapsible-text",
                    "div.review",
                    ".review",
                    "div.body-text",
                    "div.prose",
                ]
                for selector in review_selectors:
                    review_block = film_soup.select_one(selector)
                    if review_block:
                        review_text = review_block.get_text(" ", strip=True)
                        if review_text:
                            break

                if not review_text:
                    paragraphs = [
                        paragraph.get_text(" ", strip=True)
                        for paragraph in film_soup.select("div.body-text p, .review p, .js-review-body p")
                    ]
                    review_text = " ".join(part for part in paragraphs if part).strip()

        if review_url and review_text:
            break

        if genre_text and (poster or not review_url):
            break

    return {"poster": poster, "review": review_text, "year": None, "genres": genre_text}


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


def rating_to_moons(rating: str) -> str:
    """Convert Letterboxd-style ratings into emoji moons."""
    if rating == "No rating":
        return "No rating"

    if re.fullmatch(r"[★☆½\s]+", rating):
        full = rating.count("★")
        half = "½" in rating
        empty = rating.count("☆")
        result = "🌕" * full
        if half:
            result += "🌗"
        result += "🌑" * empty
        return result

    try:
        value = float(rating)
    except ValueError:
        return rating

    full = int(value)
    half = value - full >= 0.5
    empty = 5 - full - (1 if half else 0)

    result = "🌕" * full
    if half:
        result += "🌗"
    result += "🌑" * empty
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

film_details = fetch_film_details(
    str(movie.get("url") or ""),
    str(movie.get("review_url") or "") or None,
)
movie["poster"] = film_details.get("poster") or movie.get("poster")
movie["review"] = film_details.get("review")

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
movie_genre = str(film_details.get("genres") or "")
rating = extract_rating(review_text, str(movie.get("rating") or ""))
stars = rating_to_moons(rating)

markdown = f"""---
title: Movie Recommendation
movie-title: {yaml_quote(movie_title)}
movie-poster: {yaml_quote(movie_poster)}
movie-link: {yaml_quote(movie_link)}
movie-rating: {yaml_quote(stars)}
movie-genre: {yaml_quote(movie_genre)}
---

## Review

{review_text}
"""

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(markdown, encoding="utf-8")