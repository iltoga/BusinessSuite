from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand

from cache.namespace import namespace_manager

User = get_user_model()


class Command(BaseCommand):
    help = "Clear cache (global or per-user)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            help="User ID for per-user cache clearing",
        )
        parser.add_argument(
            "--all-users",
            action="store_true",
            help="Clear cache for all users (increments all user versions)",
        )

    def handle(self, *args, **options):
        user_id = options.get("user")
        all_users = options.get("all_users")
        
        if user_id:
            # Per-user cache clearing
            try:
                user = User.objects.get(id=user_id)
                old_version = namespace_manager.get_user_version(user_id)
                new_version = namespace_manager.increment_user_version(user_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Cache cleared for user {user.username} (ID: {user_id}): "
                        f"version {old_version} -> {new_version}"
                    )
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with ID {user_id} does not exist")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error clearing cache for user {user_id}: {e}")
                )
        
        elif all_users:
            # Clear cache for all users
            users = User.objects.all()
            cleared_count = 0
            error_count = 0
            
            for user in users:
                try:
                    old_version = namespace_manager.get_user_version(user.id)
                    new_version = namespace_manager.increment_user_version(user.id)
                    self.stdout.write(
                        f"Cleared cache for {user.username} (ID: {user.id}): "
                        f"v{old_version} -> v{new_version}"
                    )
                    cleared_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Error clearing cache for {user.username} (ID: {user.id}): {e}"
                        )
                    )
                    error_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nCleared cache for {cleared_count} users "
                    f"({error_count} errors)"
                )
            )
        
        else:
            # Global cache clear (default behavior - backward compatible)
            cache.clear()
            self.stdout.write(self.style.SUCCESS("Global cache has been cleared!"))
