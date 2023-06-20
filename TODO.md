# TODO list for RevisBaliCRM

## BUGS

### 2023-06-17

## RESOLVED ✓

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
- create product: parent model is not included in a transaction together with its children


## TODO:

### 2023-06-19
- after doc application is closed, add a button to upload the processed_document (eg. the visa stamp on the passport). this is a special document type which is not required and cannot be chosen by the user as a required document. it is only available after the application is closed.

### 2023-06-09
- add exit_date to customer application: optional field telling us if and when the customer wants to go out of the country. This should trigger a notification in case the customer’s application is still on process and he has to leave the country.
- add a view to see details of a document workflow.
- add ajax call to update the workflow due_date when user updates the start_date

## DONE:

### 2023-06-20
- add print preview for documents (maybe add the template to the document_type model)

### 2023-06-18
- new customer application: add the first step of the process (document collection) automatically when creating the application. when all documents are collected, the first step will be completed automatically
- add icon to workflows that have notes
### 2023-06-18
- required document update: if the document is address, copy the address (in Bali) from the Customer model

- update customers applications:
  - due date must be calculated taking into account weekends and holidays