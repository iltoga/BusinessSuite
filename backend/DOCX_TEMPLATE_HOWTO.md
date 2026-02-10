# DOCX template — how to add new mail-merge fields

This document explains how to add new merge fields to the Word invoice template used by the project (for example `invoice_template_with_footer_revisbali.docx`). The general flow is:

- Prepare a CSV that lists every merge field (column header = field name).
- In Microsoft Word, attach that CSV as the mail-merge data source (Mailings → Start Mail Merge → Select Recipients → Use Existing List).
- Insert fields from Word’s Mailings → Insert Merge Field.

Below are step-by-step instructions, tips and formatting notes.

## 1) Create the CSV file

1. Create a CSV file with a header row where each column name is a merge field name (e.g. `customer_name`, `invoice_number`, `invoice_date`, `total_amount`).
2. Put one (or many) rows of sample data below the header. It’s useful to keep at least one sample row for testing.
3. Save the file as CSV (UTF-8). In the repo we have an example named `mailmerge_fields_for_invoice.csv` — use it as a template.

Notes and best practices for the CSV:

- Use simple, consistent field names: prefer lowercase and underscores (e.g. `invoice_date`, not `Invoice Date`).
- Avoid spaces and special characters in the header. If you need a visual label in Word, use a display label in the document and map it to the field name.
- If your system locale uses semicolons as CSV separators, Excel may save with `;` — Word can usually open either, but ensure the chosen delimiter is consistent.
- Ensure the file encoding is UTF-8 if you have non-ASCII characters (names, addresses, accents).

Example CSV (first 2 rows):

customer_name,invoice_number,invoice_date,total_amount
"ACME Srl",INV-2025-001,2025-11-04,1234.50

## 2) Attach the CSV to the Word template

1. Open your Word template (e.g. `invoice_template_with_footer_revisbali.docx`).
2. Go to the Mailings tab.
3. Click `Start Mail Merge` and choose the type (e.g. `Letters` or `Directory` — `Letters` is usually fine for invoices).
4. Click `Select Recipients` → `Use an Existing List...` and choose the CSV you created.
5. Word will prompt to confirm the delimiter/encoding if necessary — confirm and finish.

After attaching the CSV, all column names from the header become available as merge fields.

## 3) Insert merge fields into the document

1. Place the cursor where you want a value to appear.
2. In Mailings → `Write & Insert Fields` → `Insert Merge Field`, choose the field name from the dropdown.
3. Repeat for each field you need in the template.

Word will insert fields that look like: { MERGEFIELD customer_name }

## 4) Formatting dates and numbers

Word supports field switches to format dates and numbers at display time. Common patterns:

- Date formatting example: { MERGEFIELD invoice_date \@ "dd MMM yyyy" }
  - To add a date format, insert the merge field, then press Alt+F9 to show field codes and add the `\@` switch.

- Number/currency formatting example: { MERGEFIELD total_amount \# "#,##0.00" }
  - Use `\#` to format numeric/currency patterns. Formatting depends on Word’s locale (decimal separator).

After editing field codes press F9 to update or Alt+F9 to toggle field code visibility.

## 5) Tips & troubleshooting

- Field names must match CSV headers exactly (case-insensitive, but best to match exact spelling). If Word doesn’t show a header, re-open the CSV in a text editor to verify the header row.
- If fields appear empty in a preview, ensure the CSV contains at least one data row and that you selected the correct row in Mailings → `Preview Results`.
- If Word mis-parses columns (e.g. everything in one column), check the delimiter and encoding — open the CSV with a text editor to confirm separators.
- If you add a new column to the CSV, re-attach the CSV in Word (or click `Select Recipients` → `Use an Existing List...` again) so Word refreshes available fields.
- Don’t use formulas or commas inside unquoted CSV cells. If you need commas inside values, quote the cell ("value, with comma").

## 6) Updating templates in the repo

1. Once your template contains all desired merge fields and formatting, save the `.docx` file.
2. Replace or add the template file in the repository (for example, commit `invoice_template_with_footer_revisbali.docx` or a new version with a clear name like `invoice_template_v2.docx`).
3. Add a short changelog/comment in the commit message listing newly added merge fields.

## 7) Advanced: using merge fields with programmatic generation

If your application programmatically merges data into the docx (e.g. using python-docx-mailmerge or other libraries), ensure the merge key names match the CSV/Word field names. Libraries often accept a dict mapping field names to values.

Field contract (minimal)

- Input: dictionary/CSV row with keys matching Word merge fields.
- Output: printed DOCX/PDF with fields replaced.
- Error mode: missing field → blank; prefer to validate presence of required keys before merging.

Edge cases to consider

- Missing/empty values — choose sensible defaults or hide sections conditionally in Word using IF fields.
- Date format mismatches — ensure the date value is either a Word-parsable date or formatted in CSV as ISO (YYYY-MM-DD) and then formatted in Word.
- Locale decimal separators for numeric formatting.

## 8) Quick checklist before finalizing template

- [ ] CSV header added for each new merge field.
- [ ] CSV saved in UTF-8 and with correct delimiter.
- [ ] CSV attached in Word and fields inserted.
- [ ] Field formatting (dates, currency) added where needed.
- [ ] Test preview in Word with sample CSV row(s).
- [ ] Save and commit the final `.docx` to the repo with a descriptive commit message.

If you want, I can add a small sample CSV into the `fixtures/` folder or add a short validation script that checks that your CSV headers match a configured list of expected fields. Tell me which you prefer and I’ll add it.

---
End of how-to.
