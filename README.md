# RevisBaliCRM
CRM for RevisBali

## Ideas

### Telegram bot
[tgbot on github](https://github.com/Ali-Toosi/django-tgbot)


### Openai GPT-3 and GPT-4 integration
[example project](https://github.com/Kouidersif/openai-API/tree/sif/openapp)

A bot to get (and possibly insert) data from/to the CRM.

### Parse uploaded documents

Scan documents for MRZ (machine readable zones) and extract info such as name, number, expiration date.

[PassportEye](https://pypi.org/project/PassportEye/)
The package provides tools for recognizing machine readable zones (MRZ) from scanned identification documents. The documents may be located rather arbitrarily on the page - the code tries to find anything resembling a MRZ and parse it from there.


## Links

### Django Reactive

Unicorn
[Unicorn - and competitors](https://www.django-unicorn.com/docs/)

### OCR

Document-ai
[Accelerating Document AI](https://huggingface.co/blog/document-ai)

[Improove OCR](https://pyimagesearch.com/2021/11/22/improving-ocr-results-with-basic-image-processing/)

## HOWTO

### Export and import data

#### Export model to json

```bash
python manage.py export_model products DocumentType fixtures/document_types.json --settings=RevisBaliCRM.settings.dev
```

#### Import model from json

```bash
python manage.py import_model fixtures/document_types.json --settings=RevisBaliCRM.settings.dev
```