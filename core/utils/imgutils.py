import base64
from io import BytesIO

from pdf2image.pdf2image import convert_from_bytes, convert_from_path
from PIL import Image


def convert_and_resize_image(file, file_type, return_encoded=True, resize=False, base_width=400):
    """
    Convert the file to an image and resize it
    :param file: the file to convert
    :param file_type: the file type
    :param resize: whether to resize the image or not
    :param base_width: the base width to resize the image to
    :return: the image and the base64 encoded image string
    """
    if file_type not in ["image/jpeg", "image/png", "application/pdf"]:
        raise ValueError("File format not supported. Only images (jpeg and png) and pdf are accepted!")

    if file_type == "application/pdf":
        img = None
        try:
            file.seek(0)  # Ensure cursor is at start of file
            images = convert_from_bytes(file.read())
        except Exception as e:
            images = convert_from_path(file)

        if len(images) == 0:
            raise ValueError("Could not convert the pdf to an image!")
        # Assuming you want the first page
        img = images[0]
    else:
        img = Image.open(file)

    if resize:
        w_percent = base_width / float(img.size[0])
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((base_width, h_size), Image.ANTIALIAS)

    # Encode the image to base64
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    if return_encoded:
        img_str = base64.b64encode(buffered.getvalue())
    else:
        img_str = ""

    return img, img_str
