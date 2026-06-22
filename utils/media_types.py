import os


CHANNEL_RESOURCE_EXTENSIONS = {
    ".cfg",
    ".json",
    ".m3u",
    ".m3u8",
    ".txt",
}

LOCAL_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".ts",
    ".m2ts",
    ".mts",
    ".mpg",
    ".mpeg",
    ".m4v",
    ".3gp",
    ".ogv",
}

LOCAL_AUDIO_EXTENSIONS = {
    ".mp3",
    ".aac",
    ".flac",
    ".wav",
    ".m4a",
    ".ogg",
    ".wma",
    ".opus",
}

LOCAL_GIF_EXTENSIONS = {
    ".gif",
}

LOCAL_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}

LOCAL_VISUAL_EXTENSIONS = LOCAL_GIF_EXTENSIONS | LOCAL_IMAGE_EXTENSIONS
LOCAL_MEDIA_EXTENSIONS = LOCAL_VIDEO_EXTENSIONS | LOCAL_AUDIO_EXTENSIONS | LOCAL_VISUAL_EXTENSIONS
RESOURCE_EXTENSIONS = CHANNEL_RESOURCE_EXTENSIONS | LOCAL_MEDIA_EXTENSIONS


def file_extension(path):
    return os.path.splitext(str(path or ""))[1].lower()


def is_channel_resource(path):
    return file_extension(path) in CHANNEL_RESOURCE_EXTENSIONS


def is_local_media(path):
    return file_extension(path) in LOCAL_MEDIA_EXTENSIONS


def is_local_video(path):
    return file_extension(path) in LOCAL_VIDEO_EXTENSIONS


def is_local_audio(path):
    return file_extension(path) in LOCAL_AUDIO_EXTENSIONS


def is_local_gif(path):
    return file_extension(path) in LOCAL_GIF_EXTENSIONS


def is_local_image(path):
    return file_extension(path) in LOCAL_IMAGE_EXTENSIONS


def is_visual_media(path):
    return file_extension(path) in LOCAL_VISUAL_EXTENSIONS


def is_resource_file(path):
    return is_channel_resource(path) or is_local_media(path)


def resource_type_key(path):
    if is_channel_resource(path):
        return "channel_resource"
    if is_local_video(path):
        return "video"
    if is_local_audio(path):
        return "audio"
    if is_local_gif(path):
        return "gif"
    if is_local_image(path):
        return "image"
    return "unknown"


def resource_type_label(path_or_type):
    value = str(path_or_type or "")
    type_key = value if value in {
        "channel_resource",
        "video",
        "audio",
        "gif",
        "image",
        "unknown",
    } else resource_type_key(value)
    labels = {
        "channel_resource": "频道",
        "video": "视频",
        "audio": "音频",
        "gif": "GIF",
        "image": "图片",
        "unknown": "资源",
    }
    return labels.get(type_key, "资源")


def resource_label(path):
    prefix = resource_type_label(path)
    return f"[{prefix}] {os.path.basename(path)}"


def is_local_media_channel(channel):
    if not channel:
        return False
    manifest_type = str(channel.get("ManifestType") or "").strip().lower()
    manifest = str(channel.get("Manifest") or "").strip()
    if channel.get("_IsLocalMedia") or manifest_type == "local":
        return True
    return bool(manifest and is_local_media(manifest) and os.path.isfile(manifest))
