import requests
import sys
import csv
import aiofiles
from typing import Optional, List
from pydantic import BaseModel
from collections import OrderedDict
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")


class LabelRelease(BaseModel):
    label: str
    release: str


class Release(BaseModel):
    title: Optional[str]
    artist: Optional[str] = ""
    genres: Optional[List[str]]
    styles: Optional[List[str]]
    labels: Optional[List[LabelRelease]] = []
    sort_genre: str = ""
    sort_format: str = ""
    sort_format_save: str = ""
    sort_speed: str = ""


def fetch_collection(p_user, p_token):
    dc_collection = requests.get(
        "https://api.discogs.com/users/"
        + p_user
        + "/collection/folders/0/releases?per_page=1000000&token="
        + p_token
    )
    dc_releases = dc_collection.json()["releases"]

    dc_fields = requests.get(
        "https://api.discogs.com/users/"
        + p_user
        + "/collection/fields?per_page=1000000&token="
        + p_token
    )
    dc_sort_format = dc_sort_genre = dc_sort_speed = 0

    if "fields" in dc_fields.json():
        for field in dc_fields.json()["fields"]:
            if field["name"].upper() == "SORT_FORMAT":
                dc_sort_format = field["id"]
            elif field["name"].upper() == "SORT_GENRE":
                dc_sort_genre = field["id"]
            elif field["name"].upper() == "SORT_SPEED":
                dc_sort_speed = field["id"]

    releases = []
    for item in dc_releases:
        info = item["basic_information"]

        release = Release(
            title=info["title"], genres=info["genres"], styles=info["styles"],
        )

        for label in info["labels"]:
            labelRelease = LabelRelease(label=label["name"], release=label["catno"])
            release.labels.append(labelRelease)

        for line in info["artists"]:
            release.artist += " " + line["name"] + " " + line["join"]
            release.artist = release.artist.strip()

        try:
            for note in item["notes"]:
                if note["field_id"] == dc_sort_genre:
                    if note["value"]:
                        release.sort_genre = note["value"]
                if note["field_id"] == dc_sort_format:
                    if note["value"]:
                        release.sort_format = note["value"]
                        release.sort_format_save = note["value"].replace('"', "INCH")
                if note["field_id"] == dc_sort_speed:
                    if note["value"]:
                        release.sort_speed = note["value"]
        except:
            pass

        releases.append(release)

    return sorted(
        releases, key=lambda x: (x.sort_format, x.sort_genre, x.artist, x.title)
    )


def sort_by_format(p_releases: Release):
    releases_sorted = {}
    for release in p_releases:
        if release.sort_format_save not in releases_sorted:
            releases_sorted[release.sort_format_save] = []
        releases_sorted[release.sort_format_save].append(release)

    for sort_format, realeases in releases_sorted.items():
        releases_sorted[sort_format] = sorted(
            realeases, key=lambda x: (x.sort_genre, x.artist, x.title)
        )

    return releases_sorted


def write_csv(p_releases):
    csvfilename = "releases.csv"

    with open(csvfilename, "w", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(["size", "genre", "artist", "title", "speed"])
        for release in p_releases:
            csvwriter.writerow(
                [release.sort_format, release.sort_genre, release.artist, release.title, release.sort_speed]
            )

    return csvfilename


@app.get("/", include_in_schema=False)
async def get_html(
    request: Request, user: str = None, user_token: str = None, type: str = None
):
    releases = []
    releases_sorted = {}

    if type:
        if user and type == "HTML":
            releases = fetch_collection(user, user_token)
            releases_sorted = sort_by_format(releases)
        elif user and type == "CSV":
            releases = fetch_collection(user, user_token)
            return FileResponse(write_csv(releases), filename="releases.csv")
        elif user and type == "Discogs":
            return RedirectResponse(
                "https://www.discogs.com/user/" + user + "/collection"
            )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "user_token": user_token,
            "type": type,
            "releases": releases,
            "releases_sorted": releases_sorted,
            "len": len,
        },
    )


@app.get("/api/", include_in_schema=False)
async def get_api():
    return RedirectResponse("/redoc")


@app.get("/api/releases/{user}")
async def get_api_releases(
    user: str, user_token: str = None, csv: bool = False, bygenre: bool = False
):
    releases = fetch_collection(user, user_token)
    if csv:
        return FileResponse(write_csv(releases), filename="releases.csv")
    elif bygenre:
        return sort_by_format(releases)
    else:
        return releases
