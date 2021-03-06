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

class Release(BaseModel):
    title: Optional[str]
    artist: Optional[str] = ""
    size: str = ""
    size_safe: str = ""
    speed: str = ""
    type: str = ""
    sort_genre: str = ""


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

    dc_sort_genre = 0
    if "fields" in dc_fields.json():
        for field in dc_fields.json()["fields"]:
            if field["name"].upper() == "SORT_GENRE":
                dc_sort_genre = field["id"]

    releases = []
    for item in dc_releases:
        info = item["basic_information"]

        release = Release(
            title=info["title"], genres=info["genres"], styles=info["styles"],
        )

        for format in info["formats"]:
            if format["name"] == "CD":
                release.size = "CD"
                release.speed = "CD"
                if "descriptions" in format:
                    for description in format["descriptions"]:
                        if "EP" == description:
                            release.type = "EP"
                        elif "LP" == description:
                            release.type = "Album"
                        elif "Album" == description:
                            release.type = "Album"
                        elif "Maxi-Single" == description:
                            release.type = "Maxi-Single"
                        elif "Single" == description:
                            release.type = "Single"
                        elif "Compilation" == description:
                            release.type = "Album"
            else:
                if "descriptions" in format:
                    for description in format["descriptions"]:
                        if "\"" in description:
                            release.size = description
                        elif "RPM" in description:
                            speedstr = description.replace(" RPM", "").replace(" ⅓", "")
                            if release.speed == "":
                                release.speed = speedstr
                            elif release.speed != speedstr:
                                release.speed = release.speed + "/" + speedstr
                        elif "LP" == description:
                            release.size = "12\""
                            release.speed = "33"
                            release.type = "Album"
                        elif "EP" == description:
                            release.type = "EP"
                        elif "Album" == description:
                            release.type = "Album"
                        elif "Maxi-Single" == description:
                            release.type = "Maxi-Single"
                        elif "Single" == description:
                            release.type = "Single"
                        elif "Compilation" == description:
                            release.type = "Album"

        if release.type == "":
            if release.size == "12\"" or release.size == "10\"":
                if release.speed == "45":
                    release.type = "Maxi-Single"
                if release.speed == "33":
                    release.type = "Album"
                else:
                    release.type = "Maxi-Single"
            elif release.size == "7\"":
                release.type = "Single"
            elif release.size == "CD":
                release.type = "Album"

        if len(release.speed) > 0:
            release.speed = release.speed + " RPM"
        release.size_safe = release.size.replace("\"", "INCH")

        for line in info["artists"]:
            release.artist += " " + line["name"] + " " + line["join"]
            release.artist = release.artist.strip()

        try:
            for note in item["notes"]:
                if note["field_id"] == dc_sort_genre:
                    if note["value"]:
                        release.sort_genre = note["value"]
        except:
            pass

        releases.append(release)

    return sorted(
        releases, key=lambda x: (x.size, x.sort_genre, x.artist, x.title)
    )


def sort_by_format(p_releases: Release):
    releases_sorted = {}
    for release in p_releases:
        if release.size not in releases_sorted:
            releases_sorted[release.size] = []
        releases_sorted[release.size].append(release)

    for sort_format, realeases in releases_sorted.items():
        releases_sorted[sort_format] = sorted(
            realeases, key=lambda x: (x.sort_genre, x.artist, x.title)
        )

    return releases_sorted


def write_csv(p_releases):
    csvfilename = "releases.csv"

    with open(csvfilename, "w", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(["size", "type", "genre", "artist", "title", "speed"])
        for release in p_releases:
            csvwriter.writerow(
                [release.size, release.type, release.sort_genre, release.artist, release.title, release.speed]
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