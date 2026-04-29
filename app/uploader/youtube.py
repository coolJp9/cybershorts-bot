"""YouTube Data API v3 uploader with OAuth2, quota tracking, and token refresh."""

import json
import logging
from datetime import datetime, timedelta

from app.config.settings import CREDENTIALS_FILE, QUOTA_STATE_FILE, TOKEN_FILE

log = logging.getLogger("CyberBot.uploader")

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ── Quota cooldown ─────────────────────────────────────────────────────────────


def check_quota_cooldown() -> tuple[bool, datetime | None]:
    """Return (can_upload, cooldown_ends_at). Clears expired cooldown files."""
    if not QUOTA_STATE_FILE.exists():
        return True, None
    try:
        state = json.loads(QUOTA_STATE_FILE.read_text())
        cooldown_until = datetime.fromisoformat(state.get("cooldown_until", ""))
        if datetime.now() < cooldown_until:
            return False, cooldown_until
        QUOTA_STATE_FILE.unlink(missing_ok=True)
        return True, None
    except Exception as exc:
        log.warning("Could not read quota state: %s", exc)
        return True, None


def set_quota_cooldown(hours: int = 24) -> None:
    """Persist a cooldown period after hitting a YouTube quota limit."""
    cooldown_until = datetime.now() + timedelta(hours=hours)
    state = {
        "cooldown_until": cooldown_until.isoformat(),
        "reason": "uploadLimitExceeded",
        "set_at": datetime.now().isoformat(),
    }
    try:
        QUOTA_STATE_FILE.write_text(json.dumps(state, indent=2))
        log.info("YouTube quota cooldown set until %s", cooldown_until.strftime("%Y-%m-%d %H:%M"))
    except Exception as exc:
        log.error("Could not write quota state: %s", exc)


# ── OAuth2 credential management ───────────────────────────────────────────────


def get_youtube_credentials():
    """Load, refresh, or obtain fresh YouTube OAuth2 credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), _SCOPES)
            log.info("Loaded existing credentials from token.json")
        except Exception as exc:
            log.warning("Could not load token.json: %s", exc)
            creds = None

    if creds and creds.valid:
        log.info("Credentials are valid")
        return creds

    if creds and creds.expired and creds.refresh_token:
        log.info("Access token expired — refreshing...")
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            log.info("Token refreshed successfully")
            return creds
        except Exception as exc:
            err = str(exc).lower()
            if "token has been expired or revoked" in err or "invalid_grant" in err:
                log.warning("Refresh token expired — need re-authentication")
                TOKEN_FILE.unlink(missing_ok=True)
                creds = None
            else:
                log.error("Token refresh failed: %s", exc)
                return None

    if not creds:
        if not CREDENTIALS_FILE.exists():
            log.error("credentials.json not found — cannot authenticate")
            return None
        log.info("Starting OAuth flow for YouTube authentication...")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                _SCOPES,
                redirect_uri="urn:ietf:wg:oauth:2.0:oob",
            )
            try:
                creds = flow.run_local_server(
                    port=0,
                    authorization_prompt_message="Please visit this URL: {url}",
                    success_message="Authorization complete! You may close this window.",
                    open_browser=True,
                )
            except Exception:
                log.info("Local server failed — using console flow...")
                creds = flow.run_console()
            TOKEN_FILE.write_text(creds.to_json())
            log.info("New credentials saved to token.json")
            return creds
        except Exception as exc:
            log.error("OAuth flow failed: %s", exc)
            return None

    return creds


def check_token_expiry() -> dict:
    """Return a status dictionary about the current token file."""
    info: dict = {
        "exists": TOKEN_FILE.exists(),
        "valid": False,
        "expires_at": None,
        "refresh_token_present": False,
        "needs_reauth": False,
    }
    if not TOKEN_FILE.exists():
        info["needs_reauth"] = True
        return info
    try:
        token_data = json.loads(TOKEN_FILE.read_text())
        info["refresh_token_present"] = bool(token_data.get("refresh_token"))
        expiry = token_data.get("expiry")
        if expiry:
            expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            info["expires_at"] = expiry_dt.isoformat()
            info["valid"] = datetime.now(expiry_dt.tzinfo) < expiry_dt
        if not info["refresh_token_present"] and not info["valid"]:
            info["needs_reauth"] = True
    except Exception as exc:
        log.warning("Could not parse token.json: %s", exc)
        info["needs_reauth"] = True
    return info


# ── Upload ─────────────────────────────────────────────────────────────────────


def upload_youtube_scheduled(
    video_path: str,
    title: str,
    description: str,
    publish_time: datetime,
) -> tuple[bool, bool]:
    """Upload a video to YouTube with a scheduled publish time.

    Returns:
        (True, False)  — upload succeeded
        (False, True)  — quota exceeded; caller should stop uploading
        (False, False) — other error; caller may retry
    """
    log.info("Uploading to YouTube (scheduled %s IST)...", publish_time.strftime("%H:%M"))

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning("Quota cooldown active until %s", cooldown_until.strftime("%Y-%m-%d %H:%M"))
        return False, True

    if not CREDENTIALS_FILE.exists():
        log.warning("credentials.json not found — skipping upload")
        return False, False

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = get_youtube_credentials()
        if not creds:
            log.error("Could not obtain valid YouTube credentials")
            return False, False

        yt = build("youtube", "v3", credentials=creds)

        # IST is UTC+5:30
        publish_utc = publish_time - timedelta(hours=5, minutes=30)
        publish_rfc = publish_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        body = {
            "snippet": {
                "title": f"🔒 {title[:90]}",
                "description": f"{description}\n\n#cybersecurity #shorts #hackernews #infosec",
                "categoryId": "28",
                "tags": ["cybersecurity", "hacking", "shorts", "infosec"],
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_rfc,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path, mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True
        )
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log.info("Upload progress: %d%%", int(status.progress() * 100))

        vid_id = response.get("id", "unknown")
        log.info(
            "Scheduled → https://youtu.be/%s (live %s IST)",
            vid_id,
            publish_time.strftime("%Y-%m-%d %H:%M"),
        )
        return True, False

    except Exception as exc:  # catches HttpError too
        exc_str = str(exc)
        error_reason = ""
        try:
            from googleapiclient.errors import HttpError as _HttpError

            if isinstance(exc, _HttpError):
                error_details = json.loads(exc.content.decode())
                error_reason = (
                    error_details.get("error", {}).get("errors", [{}])[0].get("reason", "")
                )
        except Exception:
            error_reason = exc_str

        if "uploadLimitExceeded" in exc_str or error_reason == "uploadLimitExceeded":
            log.error("YouTube upload quota exceeded — setting 24h cooldown")
            set_quota_cooldown(hours=24)
            return False, True

        if "quotaExceeded" in exc_str or error_reason == "quotaExceeded":
            log.error("YouTube API quota exceeded — setting 24h cooldown")
            set_quota_cooldown(hours=24)
            return False, True

        if "forbidden" in exc_str.lower() or error_reason in ("forbidden", "accessNotConfigured"):
            log.error("YouTube API access forbidden: %s", exc)
            log.info("Ensure YouTube Data API v3 is enabled in Google Cloud Console.")
            return False, False

        log.error("YouTube upload failed: %s", exc)
        return False, False
