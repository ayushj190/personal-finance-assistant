# 0004. Spending & Budgeting Streamline (Rationale)

## Context

The spending page is one of the most frequently visited areas in the application. In its current form, two primary issues undermine the user experience:

First, calculation inaccuracies distort expense and budget totals. In the current query pipeline, uncategorized transactions coalesce into discretionary spending because category kind defaults to discretionary whenever a transaction lacks an assigned category. As a result, discretionary metrics artificially inflate while uncategorized expenses are counted twice in total outflow calculations. In addition, the category budget tracker sums parent category limits alongside child category limits, creating double counted budget targets and misleading variance figures.

Second, the visual interface is heavily cluttered by dense inline forms and bulky visualizations. The page embeds large expandable forms for setting monthly budgets and linking transactions to mortgage schedules directly within the main canvas. Furthermore, a complex cash flow Sankey diagram occupies massive vertical space above category drilldowns, pushing critical breakdowns below the fold.

Eliminating these defects requires repairing calculation formulas in the service and presentation layers, moving dense forms into focused modal dialogs (`@st.dialog`), and organizing the page layout into clean, scannable sections.

## Options considered

### Option 1: Streamlined spending view with modal dialog extraction, branch rollup budgeting, and exact ledger classification

Extract the category budget editor and mortgage assignment workflow into `@st.dialog` popups in `ui/dialogs.py`, triggered by clear header buttons. Correct SQL aggregation logic and pandas transformations so uncategorized expenses remain completely separate from discretionary spend. Implement non overlapping budget branch rollups in `services/budget_service.py` to prevent double counting parent and child limits. Place the cash flow Sankey diagram in a collapsible container below the primary category donut chart.

**Pros**:
- Guarantees mathematical accuracy across all KPI totals and budget variances.
- Cleans the primary canvas by moving complex forms into dedicated popups.
- Preserves access to macro cash flow visualization without forcing constant vertical scrolling.
- Prevents rerun flicker by isolating chart interactions in Streamlit fragments.

**Cons**:
- Opening a modal dialog requires an explicit click on an action button rather than having form fields immediately visible on the page.

### Option 2: Inline form expanders without modal dialogs

Retain the existing forms directly on the spending page canvas, but wrap them in collapsed `st.expander` containers. Patch the SQL queries to fix uncategorized double counting.

**Pros**:
- Keeps all editing controls on the same page canvas without routing through modal dialogs.

**Cons**:
- Expander containers still clutter the DOM and increase vertical scrolling.
- Submitting an expander form causes full page redraws and can reset expander toggle states.
- Leaves form state intertwined with page rendering logic.

### Option 3: Move category budgeting exclusively to the Settings page

Remove category budget editing and mortgage assignment tools from the spending page entirely, placing them in `ui/pages/settings.py` alongside category creation.

**Pros**:
- Makes the spending page strictly read only and very simple.

**Cons**:
- Disconnects budget limit adjustments from live monthly expense tracking, forcing users to switch tabs whenever they want to adjust a budget based on observed variance.
- Degrades workflow speed for quick adjustments.

## Rationale

Option 1 is selected because it balances immediate workflow access with a clean visual hierarchy. Placing the budget editor and mortgage assignment tool in modal dialogs keeps the primary spending canvas focused on review and analysis while keeping configuration actions accessible in one click. Correcting the category coalesce logic restores ledger trust by guaranteeing that `Total Expenses = Fixed + Discretionary + Uncategorized`. Computing branch rollup limits in `services/budget_service.py` ensures that users who budget both broad categories (such as Food & Groceries) and specific subcategories (such as Dining Out) see truthful targets rather than inflated sums.
