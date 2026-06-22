import os

import google.oauth2.credentials
import googleapiclient.discovery
import requests
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

import config
from src.utils import setup_logging

logger = setup_logging("publisher")


def _truncate_text(value: str, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_json(response: requests.Response) -> dict | None:
    try:
        return response.json()
    except ValueError:
        return None


def _extract_api_error_message(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if not isinstance(error, dict):
        return None

    message = str(error.get("message", "")).strip()
    code = error.get("code")
    subcode = error.get("error_subcode")
    type_name = error.get("type")

    parts = []
    if type_name:
        parts.append(str(type_name))
    if code is not None:
        parts.append(f"code {code}")
    if subcode is not None:
        parts.append(f"subcode {subcode}")

    prefix = ", ".join(parts)
    if prefix and message:
        return f"{prefix}: {message}"
    if prefix:
        return prefix
    return message or None


def _build_failure_result(platform: str, error: str, phase: str | None = None) -> dict:
    return {
        "success": False,
        "platform": platform,
        "url": None,
        "error": error,
        "phase": phase,
    }


def get_youtube_client():
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    client_secrets = config.YOUTUBE_CLIENT_SECRETS
    token_path = config.YOUTUBE_TOKEN_PATH

    if not os.path.exists(client_secrets):
        logger.warning("YouTube client_secrets.json not found at %s. YouTube publishing disabled.", client_secrets)
        return None

    if os.path.exists(token_path):
        try:
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(token_path, scopes)
        except Exception as exc:
            logger.error("Failed to load cached YouTube token: %s", exc)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.error("Failed to refresh YouTube credentials: %s", exc)
                creds = None

        if not creds:
            logger.info("Initializing YouTube OAuth2 flow...")
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def publish_to_youtube_detailed(video_path: str, title: str, description: str, tags: list[str]) -> dict:
    if not os.path.exists(video_path):
        error = f"Video file not found: {video_path}"
        logger.error(error)
        return _build_failure_result("youtube", error)

    try:
        youtube = get_youtube_client()
        if not youtube:
            return _build_failure_result("youtube", "YouTube client is unavailable.")

        logger.info("Publishing video to YouTube: %s", video_path)
        body = {
            "snippet": {
                "title": str(title or "Dubbed Video")[:100],
                "description": str(description or "Auto-dubbed video")[:5000],
                "tags": list(tags or [])[:30],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "private",
            },
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("YouTube upload progress: %s%%", int(status.progress() * 100))

        video_id = response.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("YouTube video uploaded successfully! URL: %s", video_url)
        return {
            "success": True,
            "platform": "youtube",
            "url": video_url,
            "error": None,
            "phase": "complete",
        }
    except Exception as exc:
        error = _truncate_text(str(exc), limit=700)
        logger.error("YouTube publishing failed: %s", exc, exc_info=True)
        return _build_failure_result("youtube", error, phase="upload")


def publish_to_youtube(video_path: str, title: str, description: str, tags: list[str]) -> str | None:
    result = publish_to_youtube_detailed(video_path, title, description, tags)
    return result["url"] if result.get("success") else None


def _facebook_request(url: str, phase: str, **kwargs) -> requests.Response:
    response = requests.post(url, **kwargs)
    if response.status_code != 200:
        payload = _safe_json(response)
        detail = _extract_api_error_message(payload) or _truncate_text(response.text, limit=700)
        message = f"Facebook {phase} failed (status {response.status_code}): {detail}"
        logger.error(message)
        raise requests.HTTPError(message, response=response)
    return response


def publish_to_facebook_detailed(video_path: str, title: str, description: str) -> dict:
    page_id = config.FACEBOOK_PAGE_ID
    page_token = config.FACEBOOK_PAGE_TOKEN

    if not page_id or not page_token:
        error = "Facebook credentials (FACEBOOK_PAGE_ID / FACEBOOK_PAGE_ACCESS_TOKEN) are not set."
        logger.warning(error)
        return _build_failure_result("facebook", error)

    if not os.path.exists(video_path):
        error = f"Video file not found: {video_path}"
        logger.error(error)
        return _build_failure_result("facebook", error)

    file_size = os.path.getsize(video_path)
    url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"

    try:
        logger.info(
            "Publishing video to Facebook Page %s using Resumable Upload: %s (Size: %.2f MB)",
            page_id,
            video_path,
            file_size / (1024 * 1024),
        )

        start_payload = {
            "upload_phase": "start",
            "file_size": file_size,
            "access_token": page_token,
        }
        start_resp = _facebook_request(url, "Phase 1 START", data=start_payload, timeout=30)
        start_res = start_resp.json()

        upload_session_id = start_res.get("upload_session_id")
        video_id = start_res.get("video_id")
        if not upload_session_id:
            raise ValueError(f"Failed to initiate Facebook upload session: {start_res}")

        logger.info("Initiated upload session: %s", upload_session_id)

        chunk_size = 4 * 1024 * 1024
        start_offset = 0

        with open(video_path, "rb") as video_file:
            while start_offset < file_size:
                video_file.seek(start_offset)
                chunk_data = video_file.read(chunk_size)
                current_chunk_size = len(chunk_data)

                logger.info("Uploading chunk: offset %s (%s bytes)...", start_offset, current_chunk_size)

                transfer_payload = {
                    "upload_phase": "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset": start_offset,
                    "access_token": page_token,
                }
                files = {
                    "video_file_chunk": (os.path.basename(video_path), chunk_data, "application/octet-stream"),
                }

                transfer_resp = _facebook_request(
                    url,
                    "Phase 2 TRANSFER",
                    data=transfer_payload,
                    files=files,
                    timeout=120,
                )
                transfer_res = transfer_resp.json()

                next_offset_str = transfer_res.get("start_offset")
                if next_offset_str is None:
                    start_offset += current_chunk_size
                else:
                    start_offset = int(next_offset_str)

                pct = min(100, int((start_offset / file_size) * 100))
                logger.info("Facebook upload progress: %s%%", pct)

        logger.info("Finishing Facebook upload session...")
        finish_payload = {
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "title": title,
            "description": description,
            "video_state": "PUBLISHED",
            "access_token": page_token,
        }
        finish_resp = _facebook_request(url, "Phase 3 FINISH", data=finish_payload, timeout=60)
        finish_res = finish_resp.json()

        if not finish_res.get("success"):
            logger.warning("Facebook finish phase returned unexpected result: %s", finish_res)

        video_url = f"https://www.facebook.com/watch/?v={video_id}"
        logger.info("Facebook video uploaded successfully via Resumable API! URL: %s", video_url)
        return {
            "success": True,
            "platform": "facebook",
            "url": video_url,
            "error": None,
            "phase": "complete",
        }
    except requests.HTTPError as exc:
        response = exc.response
        payload = _safe_json(response) if response is not None else None
        detail = _extract_api_error_message(payload) or _truncate_text(str(exc), limit=700)
        logger.error("Facebook publishing failed: %s", detail, exc_info=True)
        phase = None
        if "Phase 1 START" in str(exc):
            phase = "start"
        elif "Phase 2 TRANSFER" in str(exc):
            phase = "transfer"
        elif "Phase 3 FINISH" in str(exc):
            phase = "finish"
        return _build_failure_result("facebook", detail, phase=phase)
    except Exception as exc:
        error = _truncate_text(str(exc), limit=700)
        logger.error("Facebook publishing failed: %s", exc, exc_info=True)
        return _build_failure_result("facebook", error)


def publish_to_facebook(video_path: str, title: str, description: str) -> str | None:
    result = publish_to_facebook_detailed(video_path, title, description)
    return result["url"] if result.get("success") else None
