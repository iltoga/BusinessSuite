# TODO list for business_suite

## BUGS

---

## RESOLVED ✓

---

## TODO

### Backend

### Frontend

---

## DONE

- Backend/Infra: updated admin-domain security config for `crmadmin.revisbali.com`, made cookie scoping safe for sibling admin domains, and allowed Cloudflare Web Analytics in CSP.
- Frontend: fixed dashboard stat cards by unwrapping API success envelopes and added regression tests.
- Frontend: preserved authenticated sessions on reload by restoring from the secure refresh-cookie flow before redirecting to login.
- Frontend: showed a visible passport-image skeleton placeholder while customer detail media is loading.
- Frontend: updated list page sizes to customers 10, applications 11, invoices 11, products 10.
- Frontend: clamped document type descriptions to two lines in the admin list.
