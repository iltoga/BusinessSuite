# API Contract Examples

This document provides concrete examples of API contracts for the RevisBaliCRM application. These examples serve as reference for both backend implementation and frontend code generation.

## Table of Contents

1. [Authentication Endpoints](#authentication-endpoints)
2. [Customer Management](#customer-management)
3. [Application Management](#application-management)
4. [Invoice Management](#invoice-management)
5. [OCR Workflow](#ocr-workflow)
6. [Error Responses](#error-responses)

---

## Authentication Endpoints

### POST /api/token/

**Description:** Obtain authentication token

**Request:**

```json
{
  "username": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200 OK):**

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Doe"
  }
}
```

**Response (400 Bad Request):**

```json
{
  "code": "authentication_failed",
  "errors": {
    "nonFieldErrors": ["Unable to log in with provided credentials."]
  }
}
```

### POST /api/token/refresh/

**Description:** Refresh JWT access token

**Request:**

```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response (200 OK):**

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

---

## Customer Management

### OpenAPI Schema Snippet

```yaml
paths:
  /api/customers/:
    get:
      operationId: customers_list
      summary: List customers
      tags:
        - customers
      parameters:
        - name: search
          in: query
          description: Search in firstName, lastName, email
          schema:
            type: string
        - name: page
          in: query
          schema:
            type: integer
            default: 1
        - name: pageSize
          in: query
          schema:
            type: integer
            default: 10
        - name: ordering
          in: query
          description: Sort by field (prefix with - for descending)
          schema:
            type: string
            enum:
              [
                firstName,
                -firstName,
                lastName,
                -lastName,
                createdAt,
                -createdAt,
              ]
      responses:
        "200":
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  count:
                    type: integer
                    example: 150
                  next:
                    type: string
                    nullable: true
                    example: "http://api.example.com/api/customers/?page=2"
                  previous:
                    type: string
                    nullable: true
                  results:
                    type: array
                    items:
                      $ref: "#/components/schemas/Customer"

    post:
      operationId: customers_create
      summary: Create a customer
      tags:
        - customers
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateCustomer"
      responses:
        "201":
          description: Customer created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Customer"
        "400":
          description: Validation error
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ValidationError"

  /api/customers/{id}/:
    get:
      operationId: customers_retrieve
      summary: Get customer details
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Successful response
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/CustomerDetail"

    patch:
      operationId: customers_partial_update
      summary: Partially update customer
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UpdateCustomer"
      responses:
        "200":
          description: Customer updated
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Customer"

    delete:
      operationId: customers_destroy
      summary: Delete customer
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
      responses:
        "204":
          description: Customer deleted

components:
  schemas:
    Customer:
      type: object
      required:
        - firstName
        - lastName
        - email
      properties:
        id:
          type: integer
          readOnly: true
          example: 123
        firstName:
          type: string
          maxLength: 100
          example: "John"
        lastName:
          type: string
          maxLength: 100
          example: "Doe"
        email:
          type: string
          format: email
          example: "john.doe@example.com"
        phoneNumber:
          type: string
          nullable: true
          example: "+62812345678"
        customerType:
          type: string
          enum: [individual, company]
          example: "individual"
        country:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            code:
              type: string
        agent:
          type: object
          nullable: true
          properties:
            id:
              type: integer
            name:
              type: string
        createdAt:
          type: string
          format: date-time
          readOnly: true
          example: "2026-01-24T10:30:00Z"
        updatedAt:
          type: string
          format: date-time
          readOnly: true
          example: "2026-01-24T10:30:00Z"

    CreateCustomer:
      type: object
      required:
        - firstName
        - lastName
        - email
        - customerType
        - countryId
      properties:
        firstName:
          type: string
          maxLength: 100
        lastName:
          type: string
          maxLength: 100
        email:
          type: string
          format: email
        phoneNumber:
          type: string
          nullable: true
        customerType:
          type: string
          enum: [individual, company]
        countryId:
          type: integer
        agentId:
          type: integer
          nullable: true

    UpdateCustomer:
      type: object
      properties:
        firstName:
          type: string
          maxLength: 100
        lastName:
          type: string
          maxLength: 100
        email:
          type: string
          format: email
        phoneNumber:
          type: string
        agentId:
          type: integer
          nullable: true

    CustomerDetail:
      allOf:
        - $ref: "#/components/schemas/Customer"
        - type: object
          properties:
            applications:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  applicationNumber:
                    type: string
                  status:
                    type: string
                  createdAt:
                    type: string
                    format: date-time
```

### Example Requests and Responses

#### GET /api/customers/?search=john&page=1&pageSize=10

**Response (200 OK):**

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "firstName": "John",
      "lastName": "Doe",
      "email": "john.doe@example.com",
      "phoneNumber": "+62812345678",
      "customerType": "individual",
      "country": {
        "id": 100,
        "name": "Indonesia",
        "code": "ID"
      },
      "agent": {
        "id": 5,
        "name": "Jane Smith"
      },
      "createdAt": "2026-01-15T08:30:00Z",
      "updatedAt": "2026-01-24T10:15:00Z"
    },
    {
      "id": 25,
      "firstName": "Johnny",
      "lastName": "Walker",
      "email": "johnny.walker@example.com",
      "phoneNumber": null,
      "customerType": "company",
      "country": {
        "id": 100,
        "name": "Indonesia",
        "code": "ID"
      },
      "agent": null,
      "createdAt": "2026-01-20T14:45:00Z",
      "updatedAt": "2026-01-20T14:45:00Z"
    }
  ]
}
```

#### POST /api/customers/

**Request:**

```json
{
  "firstName": "Alice",
  "lastName": "Johnson",
  "email": "alice.j@example.com",
  "phoneNumber": "+62812987654",
  "customerType": "individual",
  "countryId": 100,
  "agentId": 5
}
```

**Response (201 Created):**

```json
{
  "id": 150,
  "firstName": "Alice",
  "lastName": "Johnson",
  "email": "alice.j@example.com",
  "phoneNumber": "+62812987654",
  "customerType": "individual",
  "country": {
    "id": 100,
    "name": "Indonesia",
    "code": "ID"
  },
  "agent": {
    "id": 5,
    "name": "Jane Smith"
  },
  "createdAt": "2026-01-24T11:00:00Z",
  "updatedAt": "2026-01-24T11:00:00Z"
}
```

**Response (400 Bad Request - Duplicate Email):**

```json
{
  "code": "validation_error",
  "errors": {
    "email": ["Customer with this email already exists."]
  }
}
```

---

## Application Management

### POST /api/applications/

**Request:**

```json
{
  "customerId": 150,
  "applicationType": "visa",
  "visaType": "tourist",
  "duration": 30,
  "purpose": "Tourism and leisure travel"
}
```

**Response (201 Created):**

```json
{
  "id": 501,
  "applicationNumber": "APP-2026-501",
  "customerId": 150,
  "applicationType": "visa",
  "visaType": "tourist",
  "duration": 30,
  "purpose": "Tourism and leisure travel",
  "status": "draft",
  "createdAt": "2026-01-24T11:05:00Z",
  "updatedAt": "2026-01-24T11:05:00Z"
}
```

### GET /api/applications/{id}/

**Response (200 OK):**

```json
{
  "id": 501,
  "applicationNumber": "APP-2026-501",
  "customer": {
    "id": 150,
    "firstName": "Alice",
    "lastName": "Johnson",
    "email": "alice.j@example.com"
  },
  "applicationType": "visa",
  "visaType": "tourist",
  "duration": 30,
  "purpose": "Tourism and leisure travel",
  "status": "draft",
  "documents": [
    {
      "id": 1001,
      "documentType": "passport",
      "fileName": "passport_scan.pdf",
      "uploadedAt": "2026-01-24T11:10:00Z",
      "ocrStatus": "pending",
      "ocrJobId": null
    }
  ],
  "createdAt": "2026-01-24T11:05:00Z",
  "updatedAt": "2026-01-24T11:10:00Z"
}
```

---

## Invoice Management

### POST /api/invoices/

**Request:**

```json
{
  "customerId": 150,
  "applicationId": 501,
  "lineItems": [
    {
      "description": "Visa Processing Fee",
      "quantity": 1,
      "price": "150.00"
    },
    {
      "description": "Document Translation",
      "quantity": 2,
      "price": "25.00"
    }
  ],
  "taxRate": "0.10"
}
```

**Response (201 Created):**

```json
{
  "id": 2001,
  "invoiceNumber": "INV-2026-2001",
  "customerId": 150,
  "applicationId": 501,
  "lineItems": [
    {
      "id": 3001,
      "description": "Visa Processing Fee",
      "quantity": 1,
      "price": "150.00",
      "total": "150.00"
    },
    {
      "id": 3002,
      "description": "Document Translation",
      "quantity": 2,
      "price": "25.00",
      "total": "50.00"
    }
  ],
  "subtotal": "200.00",
  "tax": "20.00",
  "total": "220.00",
  "amountPaid": "0.00",
  "balanceDue": "220.00",
  "status": "unpaid",
  "dueDate": "2026-02-07T00:00:00Z",
  "createdAt": "2026-01-24T11:20:00Z",
  "updatedAt": "2026-01-24T11:20:00Z"
}
```

### POST /api/invoices/{id}/calculate/

**Description:** Recalculate invoice totals (backend handles all calculations)

**Response (200 OK):**

```json
{
  "subtotal": "200.00",
  "tax": "20.00",
  "total": "220.00",
  "balanceDue": "220.00"
}
```

### POST /api/invoices/{id}/payments/

**Request:**

```json
{
  "amount": "100.00",
  "paymentDate": "2026-01-24",
  "paymentMethod": "bank_transfer",
  "reference": "TRX123456"
}
```

**Response (201 Created):**

```json
{
  "id": 4001,
  "invoiceId": 2001,
  "amount": "100.00",
  "paymentDate": "2026-01-24",
  "paymentMethod": "bank_transfer",
  "reference": "TRX123456",
  "createdAt": "2026-01-24T12:00:00Z"
}
```

**Updated Invoice Status Response:**

```json
{
  "id": 2001,
  "status": "partially_paid",
  "amountPaid": "100.00",
  "balanceDue": "120.00"
}
```

---

## OCR Workflow

### POST /api/documents/

**Description:** Upload document and trigger OCR processing

**Request (multipart/form-data):**

```
file: [Binary file data]
documentType: "passport"
applicationId: 501
```

**Response (202 Accepted):**

```json
{
  "id": 1001,
  "documentType": "passport",
  "fileName": "passport_scan.pdf",
  "fileUrl": "/media/documents/passport_scan_abc123.pdf",
  "uploadedAt": "2026-01-24T11:10:00Z",
  "ocrStatus": "processing",
  "ocrJobId": "ocr_job_xyz789"
}
```

### GET /api/ocr/status/{job_id}/

**Description:** Poll OCR job status

**Response (200 OK - Processing):**

```json
{
  "jobId": "ocr_job_xyz789",
  "status": "processing",
  "progress": 45,
  "message": "Extracting text from document...",
  "data": null,
  "error": null
}
```

**Response (200 OK - Complete):**

```json
{
  "jobId": "ocr_job_xyz789",
  "status": "complete",
  "progress": 100,
  "message": "OCR completed successfully",
  "data": {
    "firstName": "ALICE",
    "lastName": "JOHNSON",
    "passportNumber": "X1234567",
    "dateOfBirth": "1990-05-15",
    "expiryDate": "2030-05-14",
    "nationality": "USA",
    "gender": "F"
  },
  "error": null
}
```

**Response (200 OK - Failed):**

```json
{
  "jobId": "ocr_job_xyz789",
  "status": "failed",
  "progress": 0,
  "message": "OCR processing failed",
  "data": null,
  "error": "Unable to detect text in the uploaded image. Please ensure the document is clear and well-lit."
}
```

---

## Error Responses

### Validation Error (400)

```json
{
  "code": "validation_error",
  "errors": {
    "email": ["This field must be unique."],
    "phoneNumber": ["Invalid phone number format."],
    "countryId": ["This field is required."]
  }
}
```

### Unauthorized (401)

```json
{
  "code": "authentication_failed",
  "errors": {
    "detail": "Authentication credentials were not provided."
  }
}
```

### Forbidden (403)

```json
{
  "code": "permission_denied",
  "errors": {
    "detail": "You do not have permission to perform this action."
  }
}
```

### Not Found (404)

```json
{
  "code": "not_found",
  "errors": {
    "detail": "Customer with id 999 not found."
  }
}
```

### Server Error (500)

```json
{
  "code": "server_error",
  "errors": {
    "detail": "An unexpected error occurred. Please try again later."
  }
}
```

---

## Generated TypeScript Interfaces

Based on the above OpenAPI schema, the following TypeScript interfaces would be generated:

```typescript
// models/customer.ts
export interface Customer {
  id: number;
  firstName: string;
  lastName: string;
  email: string;
  phoneNumber?: string;
  customerType: "individual" | "company";
  country: {
    id: number;
    name: string;
    code: string;
  };
  agent?: {
    id: number;
    name: string;
  };
  createdAt: string;
  updatedAt: string;
}

export interface CreateCustomer {
  firstName: string;
  lastName: string;
  email: string;
  phoneNumber?: string;
  customerType: "individual" | "company";
  countryId: number;
  agentId?: number;
}

export interface UpdateCustomer {
  firstName?: string;
  lastName?: string;
  email?: string;
  phoneNumber?: string;
  agentId?: number;
}

export interface CustomerDetail extends Customer {
  applications: Array<{
    id: number;
    applicationNumber: string;
    status: string;
    createdAt: string;
  }>;
}

// models/invoice.ts
export interface Invoice {
  id: number;
  invoiceNumber: string;
  customerId: number;
  applicationId: number;
  lineItems: LineItem[];
  subtotal: string;
  tax: string;
  total: string;
  amountPaid: string;
  balanceDue: string;
  status: "unpaid" | "partially_paid" | "paid" | "overdue";
  dueDate: string;
  createdAt: string;
  updatedAt: string;
}

export interface LineItem {
  id: number;
  description: string;
  quantity: number;
  price: string;
  total: string;
}

// models/ocr.ts
export interface OcrStatus {
  jobId: string;
  status: "processing" | "complete" | "failed";
  progress: number;
  message: string;
  data?: Record<string, any>;
  error?: string;
}
```

---

## Usage Notes

1. **All dates** are in ISO 8601 format (UTC)
2. **All monetary values** are strings to maintain precision
3. **Snake_case to camelCase** transformation is automatic via `djangorestframework-camel-case`
4. **Error codes** are consistent across all endpoints
5. **Pagination** follows DRF standard: `{ count, next, previous, results }`
