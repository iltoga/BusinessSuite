# TODO list for business_suite

## BUGS

## RESOLVED ✓



## TODO:

### 2023-06-09
- add exit_date to customer application: optional field telling us if and when the customer wants to go out of the country. This should trigger a notification in case the customer’s application is still on process and he has to leave the country.
- add a view to see details of a document workflow.
- add ajax call to update the workflow due_date when user updates the start_date

## DONE:

### 2023-07-25
- add a second template for partial payments when generating the invoice (download): if the invoice already has payments, use the partial payments template
### 2023-07-20
- remove quantity and unit price from the invoice template (docx)
- Customer nationality: transform from string to foreign key with CountryCode (note that the ocr already check the country code from passport against the CountryCode table, in `check_country_by_code` function)

### 2023-07-14
- in invoice application, when selecting the customer application, the price will be taken from the product base price
### 2023-07-13
- remove price from customer application

### 2023-06-18
- list document application: not sorting correctly by task due date. not filtering by 'closed' status
- update required documents: showing meta field in form even if it is not required. showing ocr_check even if it is not required
- update required documents: files are uploaed to the wrong folder

### 2023-06-12
- customer application: not saving (pk error)
- update product: required documents not showing in form
- update product: after inserting new ones, required documents not updating
### 2023-06-09
- edit workflow form: general data not showing in form
### 2023-06-08
- edit product task: can change the product in dropdown
- create product: parent model is not included in a payment together with its children
### 2023-06-20
- add print preview for documents (maybe add the template to the document_type model)
- add optional documents to customer application. These documents are not required but can be uploaded by the customer if he wants to.

### 2023-06-18
- new customer application: add the first step of the process (document collection) automatically when creating the application. when all documents are collected, the first step will be completed automatically
- add icon to workflows that have notes
### 2023-06-18
- required document update: if the document is address, copy the address (in Bali) from the Customer model

- update customers applications:
  - due date must be calculated taking into account weekends and holidays