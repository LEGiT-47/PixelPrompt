from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """Store private uploads without exposing a directly usable media URL."""

    def url(self, name):
        raise ValueError("Private files must be served through an authenticated view.")