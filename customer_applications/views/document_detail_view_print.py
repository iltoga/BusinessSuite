import base64
from io import BytesIO

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import DetailView
from pdf2image.pdf2image import convert_from_path

from customer_applications.models import Document


class DocumentDetailViewPrint(PermissionRequiredMixin, DetailView):
    permission_required = ("customer_applications.view_document",)
    model = Document
    template_name = "customer_applications/document_detail_print.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # if required document has a file and it is not empty (it has a name and a url), then:
        #  - if the file is a pdf, convert it to an in-memory image and pass the image url to the template
        file = context["object"].file
        if file and file.name and file.url and file.name.endswith(".pdf"):
            images = convert_from_path(file.path)
            if images:
                # Size of A4 paper in pixels at 300 dpi
                a4_paper_size = (2480, 3508)
                # Reduce the size by 50%
                half_a4_size = (a4_paper_size[0] // 4, a4_paper_size[1] // 4)

                # Resize the image while maintaining aspect ratio
                image = images[0]
                image.thumbnail(half_a4_size)

                # Convert the PIL image to a data URL
                image_io = BytesIO()
                image.save(image_io, format="PNG")
                image_data = base64.b64encode(image_io.getvalue()).decode("utf-8")
                context["file_url"] = f"data:image/png;base64,{image_data}"
        return context
