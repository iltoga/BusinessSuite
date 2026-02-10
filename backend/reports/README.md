# Reports Module Documentation

## Overview

The Reports module provides comprehensive business analytics and reporting capabilities for BusinessSuite. It includes 9 different report types covering financial, customer, product, and operational metrics.

## Installation

The reports app is already configured in `settings/base.py` and URL patterns are registered in the main `urls.py`.

## Available Reports

### 1. **KPI Dashboard** (Executive Overview)

- **URL**: `/reports/kpi-dashboard/`
- **Purpose**: High-level executive dashboard with key performance indicators
- **Features**:
  - Revenue MTD (Month to Date) with trend
  - Revenue YTD (Year to Date)
  - Outstanding invoices amount
  - Active applications count
  - 6-month revenue trend chart
  - Top 5 customers by revenue
  - Recent payments (last 7 days)

### 2. **Monthly/Yearly Revenue Report**

- **URL**: `/reports/revenue/`
- **Purpose**: Track total revenues from invoices and payments over time
- **Features**:
  - Date range filtering (from/to)
  - Total invoiced vs. collected amounts
  - Outstanding receivables
  - Collection rate percentage
  - Monthly comparison chart (invoiced vs. collected)
  - Year-over-year comparison (when applicable)
  - Detailed monthly breakdown table

### 3. **Invoice Status Dashboard**

- **URL**: `/reports/invoice-status/`
- **Purpose**: Monitor invoice collection efficiency and aging
- **Features**:
  - Invoice count and amount by status
  - Aging analysis (0-30, 31-60, 61-90, 90+ days)
  - Average days to payment
  - Collection rate percentage
  - Status distribution donut chart
  - Aging breakdown bar chart

### 4. **Monthly Invoice Details Report** ⭐ NEW

- **URL**: `/reports/monthly-invoices/`
- **Purpose**: Detailed invoice listing with Excel export capability
- **Features**:
  - Month and year filter dropdowns
  - Complete invoice list for selected month
  - Customer information
  - Invoice status with color-coded badges
  - Amount, Paid, and Due columns
  - Summary totals (count, amount, paid, due)
  - **Excel Export**: Download complete invoice details as `.xlsx` file
- **Excel Export Format**:
  - Formatted headers with colored background
  - Customer names and invoice details
  - Currency formatting (IDR)
  - Total row with bold formatting
  - Auto-adjusted column widths
  - Professional spreadsheet layout

### 5. **Customer Lifetime Value Report**

- **URL**: `/reports/customer-ltv/`
- **Purpose**: Identify most valuable customers
- **Features**:
  - Top 10 customers by revenue chart
  - Total revenue per customer
  - Number of invoices and applications per customer
  - Average invoice value
  - Customer tenure (days since first purchase)
  - Customer segmentation (high/medium/low value)
  - Complete customer details table

### 6. **Product Revenue Analysis**

- **URL**: `/reports/product-revenue/`
- **Purpose**: Understand product performance and revenue
- **Features**:
  - Revenue by product type comparison
  - Applications count per product
  - Average price per product
  - Product type distribution
  - Detailed product performance table

### 7. **Cash Flow Analysis**

- **URL**: `/reports/cash-flow/`
- **Purpose**: Track actual cash movements and payment types
- **Features**:
  - Date range filtering
  - Total cash flow and average monthly
  - Payment type breakdown (cash, card, wire transfer, crypto, PayPal)
  - Monthly cash flow trend chart
  - Payment type pie chart
  - Transaction count

### 8. **Application Pipeline Report**

- **URL**: `/reports/application-pipeline/`
- **Purpose**: Track application processing efficiency
- **Features**:
  - Applications by status distribution
  - Document collection completion rate
  - Average processing time by product
  - Workflow task performance
  - Overdue workflow identification
  - Task completion rates

### 8. **Product Demand Forecast**

- **URL**: `/reports/product-demand/`
- **Purpose**: Predict future demand based on historical data
- **Features**:
  - 12-month historical demand trends
  - Month-over-month growth rates
  - 3-month demand forecast
  - Seasonal patterns (quarterly averages)
  - Top 5 products tracking

## Technical Details

### Architecture

```
reports/
├── __init__.py
├── apps.py
├── urls.py
├── views/
│   ├── __init__.py
│   ├── reports_index_view.py
│   ├── kpi_dashboard_view.py
│   ├── revenue_report_view.py
│   ├── invoice_status_dashboard_view.py
│   ├── customer_ltv_view.py
│   ├── product_revenue_analysis_view.py
│   ├── cash_flow_analysis_view.py
│   ├── application_pipeline_view.py
│   └── product_demand_forecast_view.py
├── utils/
│   ├── __init__.py
│   ├── date_utils.py
│   └── report_helpers.py
├── templatetags/
│   ├── __init__.py
│   └── report_filters.py
└── templates/reports/
    ├── base_report.html
    ├── index.html
    ├── kpi_dashboard.html
    ├── revenue_report.html
    ├── invoice_status_dashboard.html
    ├── customer_ltv.html
    ├── product_revenue_analysis.html
    ├── cash_flow_analysis.html
    ├── application_pipeline.html
    └── product_demand_forecast.html
```

### Key Components

**Views**: All views use Django's `TemplateView` with `LoginRequiredMixin` for authentication. Data is aggregated using Django ORM with annotations, aggregations, and complex queries.

**Template Tags**: Custom `to_json` filter for safely serializing Python data to JSON for Chart.js.

**Utilities**:

- `date_utils.py`: Date range filtering and month list generation
- `report_helpers.py`: Currency formatting and trend indicators

**Charts**: Uses Chart.js 4.4.0 for interactive, responsive charts (line, bar, pie, doughnut).

**Print Support**: All reports include print-optimized CSS for professional PDF generation via browser print function.

## Usage

### Accessing Reports

1. Navigate to `/reports/` to see the reports index page
2. Click on any report card to view the specific report
3. Use the navigation menu (sidebar or top navbar) to access reports directly

### Navigation Menu

Reports are accessible from:

- **Top Navbar**: Dropdown menu with all reports
- **Sidebar**: Collapsible "Reports" section with all reports
- **Reports Index**: Card-based layout grouped by category

### Filtering

Reports that support filtering (Revenue, Cash Flow):

1. Use the date picker inputs to select date range
2. Click "Filter" button to apply filters
3. Click "Reset" to return to default view (current year)

### Printing

1. Click the "Print Report" button on any report
2. Use browser's print dialog to:
   - Save as PDF
   - Print to physical printer
   - Adjust page settings

The print stylesheet automatically:

- Hides navigation elements
- Optimizes chart sizes
- Ensures proper page breaks

## Permissions

All reports require authentication (`LoginRequiredMixin`). Future enhancement could add granular permissions per report type.

## Performance Considerations

- Complex aggregation queries may be slow with large datasets
- Consider adding database indexes on frequently queried fields
- Cache report data for frequently accessed reports
- Use pagination for large result sets in tables

## Future Enhancements

1. **Export Options**: CSV, Excel, PDF downloads
2. **Email Reports**: Scheduled email delivery
3. **Custom Date Ranges**: Presets (last week, last quarter, etc.)
4. **Report Scheduling**: Automated report generation
5. **Data Caching**: Redis caching for expensive queries
6. **Comparison Views**: Side-by-side period comparisons
7. **Drill-down**: Click charts to view detailed data
8. **Permissions**: Role-based report access control
9. **Favorites**: Save frequently used report configurations
10. **Annotations**: Add notes and comments to reports

## Maintenance

### Adding New Reports

1. Create a new view class in `reports/views/`
2. Add URL pattern in `reports/urls.py`
3. Create template in `reports/templates/reports/`
4. Update navigation menus in `base_template.html`
5. Add report card to `reports_index_view.py`

### Modifying Existing Reports

1. Update view logic in respective view file
2. Modify template for UI changes
3. Update chart configurations as needed
4. Test with various data scenarios

## Troubleshooting

**Charts not displaying**: Check browser console for JavaScript errors. Ensure Chart.js is loading correctly.

**No data showing**: Verify database has records. Check date range filters.

**Slow performance**: Add database indexes. Consider caching. Optimize queries.

**Print layout issues**: Adjust CSS in `base_report.html` print media queries.

## Support

For issues or questions, refer to:

- Django documentation: <https://docs.djangoproject.com/>
- Chart.js documentation: <https://www.chartjs.org/docs/>
- Bootstrap documentation: <https://getbootstrap.com/docs/>
