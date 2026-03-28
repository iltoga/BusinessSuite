# Dynamic Role-Based Access Control (RBAC) System

This document outlines the architecture, rules, and best practices for interacting with the BusinessSuite dynamic Role-Based Access Control (RBAC) system. It serves primarily to help both human developers and coding AIs maintain consistency across the Django backend and the Angular frontend.

## System Overview

The RBAC system has shifted from rigid, hardcoded user roles (e.g., checking `is_staff` or specific `group` names inside UI components) to a **dynamic, database-driven permissions matrix**. The matrix controls two main domains:
1. **Menu Visibility**: Determines which navigation menus and corresponding views a user is allowed to access.
2. **Field-Level Visibility/Editing (Masking)**: Determines whether a user can read or write specific fields on a specific data model (e.g., hiding a `base_price` for non-managers).

### Priority Logic
Rules are configured in the Django Admin pane (`RbacMenuRule` and `RbacFieldRule`) and evaluated per user on the backend.
- **Superuser (`is_superuser`)**: Always has `True` for all access rules.
- **Group/Role Overrides**: Specific rules assigned to a user's Group (e.g., `manager`, `controller`) or Role (e.g., `is_staff`). If multiple groups have conflicting rules for the same field/menu, an **OR** logic is applied (if any group grants access, the user has access).
- **Global Fallback (`group__isnull=True`)**: If a user does not match any specific group/role rules, the global default rule applies.

## 1. Backend Integration (Django)

The backend is responsible for compiling the evaluated permission matrix and intercepting restricted data *before* it gets serialized.

### The Unified Claims Endpoint
The frontend retrieves the complete dictionary of evaluated permissions at application startup via the unified claims endpoint (`/api/auth/me/`). This endpoint calls the `get_user_rbac_claims` service which returns a dictionary in the format:
```json
{
  "menus": {
    "admin_dashboard": true,
    "products_menu": false
  },
  "fields": {
    "product.base_price": { "can_read": false, "can_write": false }
  }
}
```
*Note: This matrix uses `snake_case` exactly as it's modeled in the database (e.g. `product.base_price`). Do not rely on automatic `camelCase` transformation in this payload structure.*

### Serializer Masking
To prevent hidden data from leaking over the network, serializers must inherit from `RbacFieldFilterMixin`.

```python
from api.serializers.rbac_mixin import RbacFieldFilterMixin

class ProductSerializer(RbacFieldFilterMixin, serializers.ModelSerializer):
    # This identifier MUST match the 'model_name' explicitly configured in the database rule!
    rbac_model_name = "product"  

    class Meta:
        model = Product
        fields = ['id', 'name', 'base_price', 'retail_price']
```

The `RbacFieldFilterMixin` intercepts the DRF `get_fields()` hook. It cross-references the requested fields with the compiled RBAC claims. If `can_read` is false, it uses `fields.pop(field_name, None)` to permanently remove the data from the outgoing JSON response.

## 2. Frontend Integration (Angular)

The Angular application must strictly enforce the RBAC matrix locally for optimal UX / UI structure without forcing unnecessary API trips.

### State Management (`RBAC_RULES` Token)
The `AppConfig` initializes the system by grabbing the claims from the unified endpoint payload. The state is then securely pinned into an Angular Signal injection token: `RBAC_RULES`.

```typescript
import { RBAC_RULES } from '@/core/tokens/rbac.token';
const rbacRulesSignal = inject(RBAC_RULES);
```

### Form Masking (`BaseFormComponent`)
The UI is built on a **Visual Masking** philosophy: we do not break horizontal grid layouts by ripping out DOM elements with structural directives (like `*ngIf`). Instead, we degrade the component gracefully. 

When extending `BaseFormComponent`:
```typescript
export class ProductFormComponent extends BaseFormComponent<...> {
  constructor() {
    super({ rbacModel: 'product' }); // Must provide the DB model_name identifier
  }
}
```
**Mechanism:** 
On `ngOnInit()`, `BaseFormComponent` recursively checks each reactive form control's name against the RBAC dictionary (automatically handling `camelCase` to `snake_case` conversion internally). 
If a control evaluates to `canRead: false`, the Base Component:
1. Calls `control.disable()`
2. Calls `control.setValue(null)` (Ensuring default numeric values like `0` aren't mistakenly presented)

**Handling `<input type="number">` Quirks:**
If you have a strict number input, standard HTML5 refuses to display text placeholders like `"Hidden"`. In these explicit edge cases, edit the template to dynamically flip the `[type]` property, avoiding compilation breaks:
```html
<input
  z-input
  formControlName="basePrice"
  [type]="isFieldReadable('basePrice') ? 'number' : 'text'"
  [placeholder]="isFieldReadable('basePrice') ? '' : 'Hidden for your role'"
/>
```

### Table Column Masking (`DataTableComponent`)
List views also use the gracefully-masked fallback logic via the `visibleColumns()` signal algorithm inside `DataTableComponent`.
If you declare an `rbacModelName` input on `<app-data-table>`, the grid automatically filters out restricted columns out of reality so they do not even render as table headers.
```html
<app-data-table [data]="items()" [rbacModelName]="'product'" ... />
```

### Menu Routing (`RbacMenuGuard` & `MenuService`)
For navigation routing access, routes should utilize the `RbacMenuGuard` guard alongside tracking exact menu identifiers inside the `Route.data` objects. `MenuService` globally observes the `RBAC_RULES` map to dynamically compose the available Sidebar navigation UI.

```typescript
// Route Configuration
{
  path: 'products',
  canActivate: [RbacMenuGuard],
  data: { menuId: 'menu_products_list' }
}
```

## AI Consistency Directives (Rules For Coding Assistants)

When generating new views, forms, or APIs for the application, strictly adhere to these paradigms:

1. **Never Hardcode Roles:** Do not use `authService.isAdmin()` or explicit string checks like `user.groups.contains('manager')` inside forms, UI tables, or custom structural directives.
2. **Inherit `BaseFormComponent`:** When building ANY reactive form, inherit `BaseFormComponent` and pass down a precise `rbacModel` string mapping.
3. **Never Rip Out DOM Using Structural Bindings:** Never write structural overrides like `*ngIf="canRead('product.base_price')"` in forms. Rely fundamentally on the class-level `applyRbacRules()` masking behavior inherited from `BaseFormComponent` to ensure the grid aligns consistently. Use the `type` changing trick for number inputs if required.
4. **Use Snake Case For Rule Identifiers**: The rule `model_name` and `field_name` saved into the DB should always strictly use `snake_case`. Let internal helper pipelines (like inside `BaseFormComponent.ts` and `RbacFieldFilterMixin.py`) handle normalization automatically.
5. **Always Bind Mixins To Serializers:** When crafting DRF Serializers, consistently append `RbacFieldFilterMixin` to automatically prevent serialization layer leaks. Provide `rbac_model_name = "xxx"`.
