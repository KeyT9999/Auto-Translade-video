import os
import requests
import google.oauth2.credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload
import config
from src.utils import setup_logging

logger = setup_logging("publisher")


def get_youtube_client():
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    client_secrets = config.YOUTUBE_CLIENT_SECRETS
    token_path = config.YOUTUBE_TOKEN_PATH

    if not os.path.exists(client_secrets):
        logger.warning(f"YouTube client_secrets.json not found at {client_secrets}. YouTube publishing disabled.")
        return None

    if os.path.exists(token_path):
        try:
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(token_path, scopes)
        except Exception as e:
            logger.error(f"Failed to load cached YouTube token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Failed to refresh YouTube credentials: {e}")
                creds = None

        if not creds:
            logger.info("Initializing YouTube OAuth2 flow...")
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def publish_to_youtube(video_path: str, title: str, description: str, tags: list[str]) -> str | None:
    try:
        youtube = get_youtube_client()
        if not youtube:
            return None

        logger.info(f"Publishing video to YouTube: {video_path}")
        body = {
            "snippet": {
                "title": title[:100],  # Title character limit is 100
                "description": description[:5000],  # Description character limit is 5000
                "tags": tags[:30],
                "categoryId": "22"  # People & Blogs category
            },
            "status": {
                "privacyStatus": "private"  # Upload as private for review first
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"YouTube upload progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"YouTube video uploaded successfully! URL: {video_url}")
        return video_url
    except Exception as e:
        logger.error(f"YouTube publishing failed: {e}", exc_info=True)
        return None


def publish_to_facebook(video_path: str, title: str, description: str) -> str | None:
    page_id = config.FACEBOOK_PAGE_ID
    page_token = config.FACEBOOK_PAGE_TOKEN

    if not page_id or not page_token:
        logger.warning("Facebook credentials (FACEBOOK_PAGE_ID/TOKEN) not set. Skipping Facebook publishing.")
        return None

    try:
        logger.info(f"Publishing video to Facebook Page {page_id}: {video_path}")
        url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"
        payload = {
            "title": title,
            "description": description,
            "access_token": page_token
        }

        with open(video_path, "rb") as video_file:
            files = {
                "source": (os.path.basename(video_path), video_file, "video/mp4")
            }
            resp = requests.post(url, data=payload, files=files, timeout=300)

        resp.raise_for_status()
        res = resp.json()
        video_id = res.get("id")
        video_url = f"https://www.facebook.com/watch/?v={video_id}"
        logger.info(f"Facebook video uploaded successfully! URL: {video_url}")
        return video_url
    except Exception as e:
        logger.error(f"Facebook publishing failed: {e}", exc_info=True)
        return None
