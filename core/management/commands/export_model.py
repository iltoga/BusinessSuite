from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exports a Django model to a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("app_name", type=str)
        parser.add_argument("model_name", type=str)
        parser.add_argument("output_file", type=str)

    def handle(self, *args, **options):
        app_name = options["app_name"]
        model_name = options["model_name"]
        output_file = options["output_file"]

        model = apps.get_model(app_name, model_name)

        data = serializers.serialize("json", model.objects.all())

        with open(output_file, "w") as f:
            f.write(data)

        self.stdout.write(self.style.SUCCESS('Successfully exported data to "%s"' % output_file))
