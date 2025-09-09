from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Jugador

@receiver(post_save, sender=User)
def crear_perfil_jugador(sender, instance: User, created, **kwargs):
    if created:
        Jugador.objects.create(user=instance)
