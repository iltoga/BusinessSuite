# Customer List Component Styling Updates

## Overview

The customer list component has been updated to match the Django template design with a fully themeable color system.

## Changes Made

### 1. Button Variants

Added new themeable button variants:

- **warning** - Yellow/orange color for Edit buttons
- **success** - Green color for New Application buttons
- **destructive** - Red color for Delete buttons (existing)
- **default** - Primary brand color for View buttons (existing)
- **ghost** - Subtle style for Disable/Enable buttons (existing)

### 2. Theme System

Created a comprehensive theming system using CSS variables:

**Files Updated:**

- `/src/styles.css` - Added `--warning`, `--warning-foreground`, `--success`, `--success-foreground` CSS variables
- `/src/app/core/theme.config.ts` - New file with pre-made theme configurations
- `/THEME_CUSTOMIZATION.md` - Complete guide for customizing themes

### 3. Component Layout

Updated the customer list layout to match Django design:

- Improved spacing and padding
- Better header layout with "Customer List" title
- Cleaner search toolbar with "Hide Disabled" checkbox
- Enhanced table styling with better borders and hover effects
- Improved action buttons layout with proper spacing

### 4. Table Styling

Enhanced table appearance:

- Better header background color
- Proper row borders and hover states
- Consistent cell padding (0.75rem 1rem)
- Vertical middle alignment for table cells
- Smooth hover transitions

## Button Color Mapping

| Action          | Button Variant | Color         | CSS Variable    |
| --------------- | -------------- | ------------- | --------------- |
| View            | `default`      | Blue/Black    | `--primary`     |
| Edit            | `warning`      | Yellow/Orange | `--warning`     |
| Disable/Enable  | `ghost`        | Muted gray    | N/A             |
| Delete          | `destructive`  | Red           | `--destructive` |
| New Application | `success`      | Green         | `--success`     |

## How to Customize

### Quick Theme Change

Edit `/src/styles.css` and modify the color values:

```css
:root {
  --warning: oklch(0.754 0.149 83.317); /* Edit button */
  --success: oklch(0.596 0.163 155.825); /* New Application button */
  --destructive: oklch(0.577 0.245 27.325); /* Delete button */
  --primary: oklch(0.205 0 0); /* View button */
}
```

### Use Pre-made Themes

See `/src/app/core/theme.config.ts` for:

- Default theme (current)
- Blue theme
- Purple theme
- Green theme

### Complete Customization Guide

See `/THEME_CUSTOMIZATION.md` for detailed instructions on:

- Understanding OKLCH color format
- Creating custom themes
- Applying themes to the application
- Testing and troubleshooting

## Files Modified

### Component Files

- `customer-list.component.html` - Updated button markup and layout
- `customer-list.component.css` - Enhanced table styling
- `customer-list.component.ts` - No changes (already had necessary methods)

### Shared Components

- `button/button.variants.ts` - Added `warning` and `success` variants

### Global Styles

- `styles.css` - Added new CSS variables for theme colors

### Documentation

- `THEME_CUSTOMIZATION.md` - Complete theming guide (new)
- `theme.config.ts` - Theme configuration reference (new)
- `CUSTOMER_LIST_STYLING.md` - This file (new)

## Testing

1. Start the dev server: `bun run start`
2. Navigate to: `http://localhost:4200/customers`
3. Verify:
   - ✅ Buttons have correct colors
   - ✅ Table styling matches Django version
   - ✅ Hover effects work properly
   - ✅ All actions are functional

## Next Steps

To apply a different theme:

1. Choose a theme from `/src/app/core/theme.config.ts`
2. Copy the color values
3. Update `/src/styles.css` with new values
4. Refresh the browser to see changes

Or create your own custom theme using the OKLCH color format!
