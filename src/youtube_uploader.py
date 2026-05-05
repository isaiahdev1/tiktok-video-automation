"""Upload a video to YouTube Shorts using the YouTube Data API v3."""

from __future__ import annotations
import os
import json
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), "..", "client_secrets.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "youtube_token.json")


def get_authenticated_service():
    """Return an authenticated YouTube API service, using cached token if available."""
    credentials = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        credentials = google.oauth2.credentials.Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=SCOPES,
        )

    if not credentials or not credentials.valid:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            raise FileNotFoundError(
                f"Missing {CLIENT_SECRETS_FILE}. "
                "Download your OAuth 2.0 client secrets from Google Cloud Console "
                "and save them as client_secrets.json in the project root."
            )
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, SCOPES
        )
        credentials = flow.run_local_server(port=0)

        # Cache token for future runs
        with open(TOKEN_FILE, "w") as f:
            json.dump(
                {
                    "token": credentials.token,
                    "refresh_token": credentials.refresh_token,
                    "token_uri": credentials.token_uri,
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                },
                f,
                indent=2,
            )

    return googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials
    )


def upload_short(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "22",  # 22 = People & Blogs
    privacy: str = "public",
    thumbnail_path: str | None = None,
) -> str:
    """
    Upload a video as a YouTube Short.

    Args:
        video_path: Path to the MP4 file.
        title: Video title (max 100 chars).
        description: Video description. Append #Shorts for the algorithm.
        tags: List of keyword tags.
        category_id: YouTube category ID string.
        privacy: "private", "unlisted", or "public".

    Returns:
        The YouTube video ID.
    """
    youtube = get_authenticated_service()

    # Ensure #Shorts tag is present for the algorithm
    if "#Shorts" not in description:
        description = description.rstrip() + "\n\n#Shorts"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = googleapiclient.http.MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,  # 1 MB chunks
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print(f"[youtube] Uploading '{title}'...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"[youtube] Upload progress: {pct}%")

    video_id = response["id"]
    print(f"[youtube] Done! https://www.youtube.com/shorts/{video_id}")

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=googleapiclient.http.MediaFileUpload(
                    thumbnail_path, mimetype="image/jpeg"
                ),
            ).execute()
            print("[youtube] Thumbnail set.")
        except Exception as e:
            print(f"[youtube] Thumbnail failed (non-fatal): {e}")

    return video_id
