from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_delete
from django.dispatch import receiver

class Chat(models.Model):
    title = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title

class Image(models.Model):
    chat = models.ForeignKey(Chat, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='chat_images/')
    prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    input_image = models.ImageField(upload_to='', blank=True, null=True)
    strength = models.FloatField(default=0.75)

    def __str__(self):
        return f"Image for Chat {self.chat.title}"


@receiver(post_delete, sender=Image)
def delete_image_files(sender, instance, **kwargs):
    """Remove the image files from disk when an Image row is deleted
    (directly, via 'clear chat', or via cascade when a chat is deleted)."""
    for field_file in (instance.image, instance.input_image):
        if field_file:
            field_file.delete(save=False)
