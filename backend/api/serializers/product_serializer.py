from api.serializers.document_type_serializer import DocumentTypeSerializer
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from products.models import Product, ProductCategory
from products.models.document_type import DocumentType
from products.models.task import Task
from rest_framework import serializers


def _ordered_document_names(document_ids):
    if document_ids is None:
        return None
    if not document_ids:
        return ""
    documents = DocumentType.objects.filter(pk__in=document_ids)
    documents_by_id = {doc.pk: doc.name for doc in documents}
    missing_ids = [doc_id for doc_id in document_ids if doc_id not in documents_by_id]
    if missing_ids:
        raise serializers.ValidationError(f"Invalid document type ids: {', '.join(str(item) for item in missing_ids)}")
    return ",".join(documents_by_id[doc_id] for doc_id in document_ids)


def _validate_not_deprecated_document_ids(document_ids, field_name: str):
    if not document_ids:
        return
    deprecated_docs = DocumentType.objects.filter(pk__in=document_ids, deprecated=True)
    if deprecated_docs.exists():
        names = ", ".join(sorted(deprecated_docs.values_list("name", flat=True)))
        raise serializers.ValidationError({field_name: [f"Deprecated document types are not allowed: {names}"]})


def ordered_document_types(names):
    if not names:
        return []
    name_list = [name.strip() for name in names.split(",") if name.strip()]
    if not name_list:
        return []
    documents = list(DocumentType.objects.filter(name__in=name_list))
    documents.sort(key=lambda doc: name_list.index(doc.name) if doc.name in name_list else 999)
    return documents


def _raise_serializer_validation_error(exc: DjangoValidationError) -> None:
    if getattr(exc, "message_dict", None):
        raise serializers.ValidationError(exc.message_dict)
    messages = getattr(exc, "messages", None) or [str(exc)]
    raise serializers.ValidationError({"__all__": messages})


class TaskNestedSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "step",
            "name",
            "description",
            "cost",
            "duration",
            "duration_is_business_days",
            "notify_days_before",
            "notify_customer",
            "add_task_to_calendar",
            "last_step",
        ]


class ProductSerializer(serializers.ModelSerializer):
    created_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    updated_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    product_category = serializers.PrimaryKeyRelatedField(read_only=True)
    product_category_name = serializers.CharField(source="product_category.name", read_only=True)
    product_type = serializers.CharField(source="product_category.product_type", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "description",
            "immigration_id",
            "base_price",
            "retail_price",
            "currency",
            "product_category",
            "product_category_name",
            "product_type",
            "validity",
            "required_documents",
            "optional_documents",
            "documents_min_validity",
            "application_window_days",
            "validation_prompt",
            "deprecated",
            "uses_customer_app_workflow",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    tasks = TaskNestedSerializer(many=True, read_only=True)
    required_document_types = serializers.SerializerMethodField()
    optional_document_types = serializers.SerializerMethodField()
    created_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    updated_by = serializers.SlugRelatedField(read_only=True, slug_field="username")
    product_category = serializers.PrimaryKeyRelatedField(read_only=True)
    product_category_name = serializers.CharField(source="product_category.name", read_only=True)
    product_type = serializers.CharField(source="product_category.product_type", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "description",
            "immigration_id",
            "base_price",
            "retail_price",
            "currency",
            "product_category",
            "product_category_name",
            "product_type",
            "validity",
            "required_documents",
            "optional_documents",
            "documents_min_validity",
            "application_window_days",
            "validation_prompt",
            "deprecated",
            "uses_customer_app_workflow",
            "tasks",
            "required_document_types",
            "optional_document_types",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    @extend_schema_field(DocumentTypeSerializer(many=True))
    def get_required_document_types(self, instance):
        documents = ordered_document_types(instance.required_documents)
        return DocumentTypeSerializer(documents, many=True).data

    @extend_schema_field(DocumentTypeSerializer(many=True))
    def get_optional_document_types(self, instance):
        documents = ordered_document_types(instance.optional_documents)
        return DocumentTypeSerializer(documents, many=True).data


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    tasks = TaskNestedSerializer(many=True, required=False)
    required_document_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    optional_document_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)
    product_category = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    product_type = serializers.ChoiceField(
        choices=ProductCategory.PRODUCT_TYPE_CHOICES,
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "description",
            "immigration_id",
            "base_price",
            "retail_price",
            "currency",
            "product_category",
            "product_type",
            "validity",
            "documents_min_validity",
            "application_window_days",
            "validation_prompt",
            "deprecated",
            "tasks",
            "required_document_ids",
            "optional_document_ids",
        ]

    def _apply_product_category(self, attrs):
        if "product_category" in attrs:
            if attrs["product_category"] is None:
                raise serializers.ValidationError({"product_category": "Product category is required."})
            attrs.pop("product_type", None)
            return

        product_type = attrs.pop("product_type", None)
        if product_type:
            attrs["product_category"] = ProductCategory.get_default_for_type(product_type)
            return

        if self.instance is None:
            attrs["product_category"] = ProductCategory.get_default_for_type("other")

    def validate_currency(self, value):
        if value is None:
            return value
        return str(value).strip().upper()

    def validate(self, attrs):
        self._apply_product_category(attrs)

        base_price = attrs.get("base_price")
        if base_price is None and self.instance is not None:
            base_price = self.instance.base_price

        retail_price = attrs.get("retail_price")
        if retail_price is None:
            if "base_price" in attrs:
                retail_price = base_price
            elif self.instance is not None:
                retail_price = self.instance.retail_price
            else:
                retail_price = base_price

        if base_price is not None and retail_price is not None and retail_price < base_price:
            raise serializers.ValidationError(
                {"retail_price": "Retail price must be greater than or equal to base price."}
            )

        if retail_price is not None:
            attrs["retail_price"] = retail_price

        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product_type"] = instance.product_category.product_type if instance.product_category else None
        return representation

    def validate_tasks(self, value):
        if len(value) > 10:
            raise serializers.ValidationError("A product can have at most 10 tasks.")
        steps = [task.get("step") for task in value if task.get("step") is not None]
        if len(steps) != len(set(steps)):
            raise serializers.ValidationError("Each step within a product must be unique.")
        last_step_count = sum(1 for task in value if task.get("last_step"))
        if last_step_count > 1:
            raise serializers.ValidationError("Each product can only have one last step.")
        for task in value:
            duration = task.get("duration") or 0
            notify = task.get("notify_days_before") or 0
            if notify > duration:
                raise serializers.ValidationError("notify_days_before cannot be greater than duration.")
            if task.get("notify_customer") and not task.get("add_task_to_calendar"):
                raise serializers.ValidationError("notify_customer requires add_task_to_calendar to be enabled.")
        return value

    def create(self, validated_data):
        tasks_data = validated_data.pop("tasks", [])
        required_ids = validated_data.pop("required_document_ids", [])
        optional_ids = validated_data.pop("optional_document_ids", [])

        _validate_not_deprecated_document_ids(required_ids, "required_document_ids")
        _validate_not_deprecated_document_ids(optional_ids, "optional_document_ids")

        required_documents = _ordered_document_names(required_ids)
        optional_documents = _ordered_document_names(optional_ids)

        validated_data["required_documents"] = required_documents
        validated_data["optional_documents"] = optional_documents

        with transaction.atomic():
            product = Product.objects.create(**validated_data)
            for task_data in tasks_data:
                task_data.pop("id", None)  # Remove potentially null ID for new tasks
                task = Task(product=product, **task_data)
                try:
                    task.full_clean()
                except DjangoValidationError as exc:
                    _raise_serializer_validation_error(exc)
                task.save()
            return product

    def update(self, instance, validated_data):
        tasks_data = validated_data.pop("tasks", None)
        required_ids = validated_data.pop("required_document_ids", None)
        optional_ids = validated_data.pop("optional_document_ids", None)

        with transaction.atomic():
            if required_ids is not None:
                _validate_not_deprecated_document_ids(required_ids, "required_document_ids")
                instance.required_documents = _ordered_document_names(required_ids)
            if optional_ids is not None:
                _validate_not_deprecated_document_ids(optional_ids, "optional_document_ids")
                instance.optional_documents = _ordered_document_names(optional_ids)

            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if tasks_data is not None:
                existing_tasks = {task.id: task for task in instance.tasks.all()}
                updated_ids = set()

                for task_data in tasks_data:
                    task_id = task_data.pop("id", None)
                    if task_id and task_id in existing_tasks:
                        task = existing_tasks[task_id]
                        # If incoming task sets last_step to True, clear last_step on other tasks first
                        if task_data.get("last_step"):
                            Task.objects.filter(product=instance).exclude(id=task_id).update(last_step=False)
                        for attr, value in task_data.items():
                            setattr(task, attr, value)
                        try:
                            task.full_clean()
                        except DjangoValidationError as exc:
                            _raise_serializer_validation_error(exc)
                        task.save()
                        updated_ids.add(task_id)
                    else:
                        # If creating a new last_step, clear other last steps first
                        if task_data.get("last_step"):
                            Task.objects.filter(product=instance).update(last_step=False)
                        task = Task(product=instance, **task_data)
                        try:
                            task.full_clean()
                        except DjangoValidationError as exc:
                            _raise_serializer_validation_error(exc)
                        task.save()
                        updated_ids.add(task.id)

                tasks_to_delete = [task_id for task_id in existing_tasks.keys() if task_id not in updated_ids]
                if tasks_to_delete:
                    Task.objects.filter(id__in=tasks_to_delete, product=instance).delete()

            return instance


class ProductImportStartSerializer(serializers.Serializer):
    file = serializers.FileField()


class ProductImportStartResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    progress = serializers.IntegerField()
    queued = serializers.BooleanField()
    deduplicated = serializers.BooleanField()


class ProductCategoryFilterOptionSerializer(serializers.Serializer):
    value = serializers.CharField(source="name")
    label = serializers.CharField(source="name")
